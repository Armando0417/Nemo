from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import ipaddress
import os
import socket
import struct
import threading
import time
from typing import Any


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class DnsSettings:
    enabled: bool
    bind_host: str
    bind_port: int
    upstream: str
    hostname: str
    resolve_ip: str
    timeout_seconds: float
    ttl_seconds: int


@dataclass
class DnsStatus:
    enabled: bool
    running: bool
    bind_host: str
    bind_port: int
    hostname: str
    resolve_ip: str
    upstream: str
    started_at: float | None
    requests: int
    local_answers: int
    forwarded: int
    failures: int
    last_error: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["startedAt"] = self.started_at
        return payload


def _load_settings() -> DnsSettings:
    return DnsSettings(
        enabled=_env_flag("NEMO_DNS_ENABLED", True),
        bind_host=os.getenv("NEMO_DNS_BIND", "0.0.0.0").strip() or "0.0.0.0",
        bind_port=_env_int("NEMO_DNS_PORT", 53),
        upstream=os.getenv("NEMO_DNS_UPSTREAM", "1.1.1.1").strip() or "1.1.1.1",
        hostname=_normalize_hostname(os.getenv("NEMO_DNS_HOSTNAME", "chaldeas.home")),
        resolve_ip=os.getenv("NEMO_DNS_RESOLVE_IP", "127.0.0.1").strip() or "127.0.0.1",
        timeout_seconds=float(os.getenv("NEMO_DNS_TIMEOUT_SECONDS", "3.0")),
        ttl_seconds=_env_int("NEMO_DNS_TTL_SECONDS", 60),
    )


class NemoDnsResolver:
    def __init__(self, settings: DnsSettings | None = None):
        self.settings = settings or _load_settings()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._requests = 0
        self._local_answers = 0
        self._forwarded = 0
        self._failures = 0
        self._last_error: str | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self.settings.enabled:
                return self.status()
            if self._thread is not None and self._thread.is_alive():
                return self.status()

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._serve,
                name="Nemo-DNS",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            sock = self._socket
            self._socket = None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        return self.status()

    def status(self) -> dict[str, Any]:
        thread = self._thread
        return DnsStatus(
            enabled=self.settings.enabled,
            running=thread is not None and thread.is_alive() and self._last_error is None,
            bind_host=self.settings.bind_host,
            bind_port=self.settings.bind_port,
            hostname=self.settings.hostname,
            resolve_ip=self.settings.resolve_ip,
            upstream=self.settings.upstream,
            started_at=self._started_at,
            requests=self._requests,
            local_answers=self._local_answers,
            forwarded=self._forwarded,
            failures=self._failures,
            last_error=self._last_error,
        ).to_dict()

    def _serve(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            sock.bind((self.settings.bind_host, self.settings.bind_port))
            self._socket = sock
            self._started_at = time.time()
            self._last_error = None
        except OSError as exc:
            self._failures += 1
            self._last_error = (
                f"Unable to bind DNS on {self.settings.bind_host}:{self.settings.bind_port}: {exc}. "
                "On Windows, UDP port 53 usually requires Administrator or a free port."
            )
            return

        while not self._stop_event.is_set():
            try:
                data, address = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            self._requests += 1
            try:
                response, handled_locally = self._resolve_packet(data)
                if response is None:
                    response = self._forward_packet(data)
                    self._forwarded += 1
                elif handled_locally:
                    self._local_answers += 1
                sock.sendto(response, address)
            except Exception as exc:  # noqa: BLE001
                self._failures += 1
                self._last_error = str(exc)

    def _resolve_packet(self, data: bytes) -> tuple[bytes | None, bool]:
        if len(data) < 12:
            return None, False
        question, qname, qtype, qclass = _parse_question(data)
        if qname != self.settings.hostname:
            return None, False
        if qclass != 1:
            return _build_empty_response(data, question), True
        if qtype != 1:
            return _build_empty_response(data, question), True
        return _build_a_response(data, question, self.settings.resolve_ip, self.settings.ttl_seconds), True

    def _forward_packet(self, data: bytes) -> bytes:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream_socket:
            upstream_socket.settimeout(self.settings.timeout_seconds)
            upstream_socket.sendto(data, (self.settings.upstream, 53))
            response, _address = upstream_socket.recvfrom(4096)
            return response


def _normalize_hostname(hostname: str) -> str:
    return hostname.strip().strip(".").lower() or "chaldeas.home"


def _parse_question(data: bytes) -> tuple[bytes, str, int, int]:
    offset = 12
    labels: list[str] = []
    while True:
        if offset >= len(data):
            raise ValueError("Malformed DNS question.")
        length = data[offset]
        offset += 1
        if length == 0:
            break
        if length & 0xC0:
            raise ValueError("Compressed DNS names are not supported in questions.")
        label = data[offset : offset + length]
        labels.append(label.decode("ascii", errors="ignore").lower())
        offset += length
    if offset + 4 > len(data):
        raise ValueError("Malformed DNS question footer.")
    qtype, qclass = struct.unpack("!HH", data[offset : offset + 4])
    question = data[12 : offset + 4]
    return question, ".".join(labels), qtype, qclass


def _response_header(request: bytes, answer_count: int, rcode: int = 0) -> bytes:
    request_id = request[:2]
    flags = struct.unpack("!H", request[2:4])[0]
    recursion_desired = flags & 0x0100
    response_flags = 0x8000 | recursion_desired | 0x0080 | rcode
    qdcount = request[4:6]
    return request_id + struct.pack("!H", response_flags) + qdcount + struct.pack("!HHH", answer_count, 0, 0)


def _build_empty_response(request: bytes, question: bytes) -> bytes:
    return _response_header(request, 0) + question


def _build_a_response(request: bytes, question: bytes, ip: str, ttl: int) -> bytes:
    packed_ip = ipaddress.IPv4Address(ip).packed
    answer = (
        b"\xc0\x0c"
        + struct.pack("!HHIH", 1, 1, ttl, len(packed_ip))
        + packed_ip
    )
    return _response_header(request, 1) + question + answer


@lru_cache(maxsize=1)
def get_dns_resolver() -> NemoDnsResolver:
    return NemoDnsResolver()
