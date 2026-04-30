from __future__ import annotations

from dataclasses import asdict, dataclass
from http import HTTPStatus
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
import webbrowser

from gates.config import GateConfig, get_gate_map


@dataclass
class GateStatus:
    slug: str
    name: str
    subtitle: str
    state: str
    ready: bool
    running: bool
    managed: bool
    exe_exists: bool
    port: int
    url: str
    pid: int | None
    managed_pid: int | None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GateManager:
    STATUS_CACHE_TTL_SECONDS = 5.0

    def __init__(self):
        self._gates = get_gate_map()
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._status_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def list_statuses(self) -> list[dict[str, Any]]:
        now = time.time()
        statuses_by_slug: dict[str, dict[str, Any]] = {}
        uncached_slugs: list[str] = []
        uncached_ports: set[int] = set()

        for slug, gate in self._gates.items():
            cached = self._status_cache.get(slug)
            if cached is not None:
                cached_at, cached_status = cached
                if (now - cached_at) < self.STATUS_CACHE_TTL_SECONDS:
                    statuses_by_slug[slug] = dict(cached_status)
                    continue

            uncached_slugs.append(slug)
            uncached_ports.add(gate.port)

        listening_pids = self._find_listening_pids(uncached_ports) if uncached_ports else {}
        for slug in uncached_slugs:
            gate = self._require_gate(slug)
            statuses_by_slug[slug] = self._check_gate_fresh(
                slug,
                port_pid=listening_pids.get(gate.port),
            )

        return [statuses_by_slug[slug] for slug in self._gates]

    def check_gate(self, slug: str, use_cache: bool = True) -> dict[str, Any]:
        gate = self._require_gate(slug)
        if use_cache:
            cached = self._status_cache.get(gate.slug)
            if cached is not None:
                cached_at, cached_status = cached
                if (time.time() - cached_at) < self.STATUS_CACHE_TTL_SECONDS:
                    return dict(cached_status)

        return self._check_gate_fresh(slug)

    def _check_gate_fresh(self, slug: str, port_pid: int | None = None) -> dict[str, Any]:
        gate = self._require_gate(slug)
        managed_process = self._get_live_process(slug)
        resolved_port_pid = port_pid if port_pid is not None else self._find_listening_pid(gate.port)
        health_state, detail = self._probe_health(gate)

        pid = resolved_port_pid or (managed_process.pid if managed_process else None)
        managed_pid = managed_process.pid if managed_process else None
        running = pid is not None or health_state in {"starting_up", "ready"}
        ready = health_state == "ready"
        state = health_state
        if not gate.jellyfin_exe.exists():
            state = "missing_executable"
            detail = f"Jellyfin executable not found: {gate.jellyfin_exe}"
        elif managed_process is not None and managed_process.poll() is not None and not running:
            state = "stopped"
            detail = f"Managed process exited with code {managed_process.returncode}."
        elif not running and health_state == "stopped":
            state = "stopped"

        status = GateStatus(
            slug=gate.slug,
            name=gate.name,
            subtitle=gate.subtitle,
            state=state,
            ready=ready,
            running=running,
            managed=managed_process is not None,
            exe_exists=gate.jellyfin_exe.exists(),
            port=gate.port,
            url=gate.url,
            pid=pid,
            managed_pid=managed_pid,
            detail=detail,
        ).to_dict()
        self._status_cache[gate.slug] = (time.time(), dict(status))
        return status

    def start_gate(self, slug: str, wait_for_ready: bool = True, timeout: float = 20.0) -> dict[str, Any]:
        gate = self._require_gate(slug)
        if not gate.jellyfin_exe.exists():
            raise FileNotFoundError(f"Jellyfin executable not found: {gate.jellyfin_exe}")

        existing = self.check_gate(slug)
        if existing["state"] in {"starting_up", "ready"}:
            existing["action"] = "already_running"
            return existing

        gate.data_dir.mkdir(parents=True, exist_ok=True)
        gate.cache_dir.mkdir(parents=True, exist_ok=True)
        gate.log_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            existing_process = self._get_live_process(slug)
            if existing_process is None:
                process = self._spawn_gate(gate)
                self._processes[slug] = process
                self._invalidate_status(gate.slug)

        if wait_for_ready:
            self._wait_for_gate(gate, timeout=timeout)

        status = self.check_gate(slug, use_cache=False)
        status["action"] = "started"
        return status

    def stop_gate(self, slug: str, wait_timeout: float = 10.0) -> dict[str, Any]:
        gate = self._require_gate(slug)
        stopped_pids: list[int] = []

        managed_process = self._get_live_process(slug)
        if managed_process is not None:
            self._kill_pid(managed_process.pid)
            stopped_pids.append(managed_process.pid)
            self._processes.pop(slug, None)
            self._invalidate_status(gate.slug)

        port_pid = self._find_listening_pid(gate.port)
        if port_pid is not None and port_pid not in stopped_pids:
            self._kill_pid(port_pid)
            stopped_pids.append(port_pid)
            self._invalidate_status(gate.slug)

        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            if self._find_listening_pid(gate.port) is None:
                break
            time.sleep(0.3)

        status = self.check_gate(slug, use_cache=False)
        status["action"] = "stopped" if stopped_pids else "not_running"
        status["stopped_pids"] = stopped_pids
        return status

    def open_gate(
        self,
        slug: str,
        ensure_started: bool = True,
        launch_browser: bool = True,
        wait_for_ready: bool = False,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        if ensure_started:
            status = self.start_gate(slug, wait_for_ready=wait_for_ready, timeout=timeout)
        else:
            status = self.check_gate(slug)

        opened = False
        if launch_browser:
            opened = webbrowser.open(status["url"])
        status["action"] = "opened" if opened else "open_url_ready"
        status["browser_opened"] = opened
        return status

    def shutdown_managed(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for slug in list(self._processes.keys()):
            try:
                results.append(self.stop_gate(slug))
            except Exception as exc:  # noqa: BLE001
                gate = self._gates.get(slug)
                results.append(
                    {
                        "slug": slug,
                        "name": gate.name if gate else slug,
                        "action": "shutdown_error",
                        "detail": str(exc),
                    }
                )
        return results

    def _require_gate(self, slug: str) -> GateConfig:
        normalized = slug.strip().lower()
        gate = self._gates.get(normalized)
        if gate is None:
            supported = ", ".join(sorted(self._gates))
            raise KeyError(f"Unknown gate '{slug}'. Supported gates: {supported}.")
        return gate

    def _get_live_process(self, slug: str) -> subprocess.Popen | None:
        process = self._processes.get(slug)
        if process is None:
            return None
        if process.poll() is not None:
            self._processes.pop(slug, None)
            self._invalidate_status(slug)
            return None
        return process

    def _invalidate_status(self, slug: str) -> None:
        self._status_cache.pop(slug, None)

    def _spawn_gate(self, gate: GateConfig) -> subprocess.Popen:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        args = [
            str(gate.jellyfin_exe),
            "--datadir",
            str(gate.data_dir),
            "--cachedir",
            str(gate.cache_dir),
            "--logdir",
            str(gate.log_dir),
        ]

        return subprocess.Popen(
            args,
            cwd=str(gate.jellyfin_exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

    def _probe_health(self, gate: GateConfig) -> tuple[str, str | None]:
        try:
            with urllib_request.urlopen(f"{gate.url}/health", timeout=3.0) as response:
                body = response.read().decode("utf-8", errors="ignore")
                if "Healthy" in body:
                    return "ready", None
                if "Degraded" in body:
                    return "starting_up", "Jellyfin reports a degraded startup state."
                if response.status == HTTPStatus.OK:
                    return "ready", None
                return "error", f"Unexpected health response HTTP {response.status}."
        except urllib_error.HTTPError as exc:
            return "error", f"Health endpoint returned HTTP {exc.code}."
        except urllib_error.URLError:
            return "stopped", None
        except TimeoutError:
            return "starting_up", "Timed out while probing the health endpoint."

    def _wait_for_gate(self, gate: GateConfig, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            state, _detail = self._probe_health(gate)
            if state in {"starting_up", "ready"}:
                return
            managed_process = self._get_live_process(gate.slug)
            if managed_process is not None and managed_process.poll() is not None:
                raise RuntimeError(f"{gate.name} exited with code {managed_process.returncode}.")
            time.sleep(0.5)

    def _find_listening_pid(self, port: int) -> int | None:
        return self._find_listening_pids({port}).get(port)

    def _find_listening_pids(self, ports: set[int]) -> dict[int, int]:
        if not ports:
            return {}

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        suffixes = {f":{port}": port for port in ports}
        matches: dict[int, int] = {}
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line.startswith("TCP"):
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            local_address = parts[1]
            state = parts[3].upper()
            pid_text = parts[4]

            if state != "LISTENING":
                continue

            matched_port = next(
                (port for suffix, port in suffixes.items() if local_address.endswith(suffix)),
                None,
            )
            if matched_port is None:
                continue

            try:
                matches[matched_port] = int(pid_text)
            except ValueError:
                continue
        return matches

    def _kill_pid(self, pid: int) -> None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )


_MANAGER: GateManager | None = None


def get_gate_manager() -> GateManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = GateManager()
    return _MANAGER
