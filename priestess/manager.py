from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
import json
import queue
import threading
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from priestess.config import PriestessSettings, get_settings


@dataclass
class AlertEvent:
    kind: str
    title: str
    message: str
    fields: dict[str, Any]
    created_at: str
    color: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PriestessManager:
    def __init__(self, settings: PriestessSettings):
        self.settings = settings
        self._queue: queue.Queue[AlertEvent | None] = queue.Queue(maxsize=settings.queue_max_size)
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started = False
        self._sent_count = 0
        self._failed_count = 0
        self._dropped_count = 0
        self._last_error: str | None = None
        self._last_event: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._started:
                return self.status()
            self._started = True
            self._worker = threading.Thread(
                target=self._run,
                name=f"{self.settings.service_name}-alert-worker",
                daemon=True,
            )
            self._worker.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._started:
                return self.status()
            self._started = False
            self._queue.put(None)
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "serviceName": self.settings.service_name,
            "enabled": self.settings.enabled,
            "configured": bool(self.settings.discord_webhook_url),
            "relayAlertsEnabled": self.settings.relay_alerts_enabled,
            "running": self._started and self._worker is not None and self._worker.is_alive(),
            "queueSize": self._queue.qsize(),
            "sent": self._sent_count,
            "failed": self._failed_count,
            "dropped": self._dropped_count,
            "lastError": self._last_error,
            "lastEvent": self._last_event,
            "envFile": str(self.settings.env_file),
        }

    def notify_relay_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.enabled or not self.settings.relay_alerts_enabled:
            return {"queued": False, "reason": "disabled"}
        uploaded = int(payload.get("uploaded") or 0)
        if uploaded <= 0:
            return {"queued": False, "reason": "no_uploaded_files"}

        target_label = str(payload.get("targetLabel") or payload.get("targetDeviceName") or payload.get("targetDeviceId") or "unknown device")
        source_label = str(payload.get("sourceDeviceName") or payload.get("sourceDeviceId") or "unknown source")
        payload_name = str(payload.get("payloadName") or "payload")
        item_label = "item" if uploaded == 1 else "items"
        failures = payload.get("failed") or []

        message = (
            f"Relay received `{payload_name}` for **{target_label}** "
            f"from **{source_label}** with {uploaded} {item_label}."
        )
        if failures:
            message += f" {len(failures)} upload failure(s) were reported."

        return self.enqueue(
            AlertEvent(
                kind="relay.payload.received",
                title="Relay payload received",
                message=message,
                fields={
                    "payload": payload_name,
                    "source": source_label,
                    "target": target_label,
                    "uploaded": uploaded,
                    "failures": len(failures),
                    "targetInboxPath": payload.get("targetInboxPath"),
                },
                created_at=_now_iso(),
                color=0x3BA55D,
            )
        )

    def notify_relay_archive(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.enabled or not self.settings.relay_alerts_enabled:
            return {"queued": False, "reason": "disabled"}

        entry_name = str(payload.get("downloadEntryName") or payload.get("entryName") or "payload")
        source_label = str(payload.get("sourceDeviceName") or payload.get("sourceDeviceId") or "unknown source")
        archive_label = str(
            payload.get("archiveDeviceLabel")
            or payload.get("archiveDeviceName")
            or payload.get("archiveDeviceId")
            or "Relay Hub"
        )
        item_kind = str(payload.get("kind") or "item")
        destination = payload.get("destinationPath")

        message = (
            f"Relay moved `{entry_name}` from **{source_label}** "
            f"into **{archive_label}** handoff storage."
        )

        return self.enqueue(
            AlertEvent(
                kind="relay.payload.archived",
                title="Relay payload archived",
                message=message,
                fields={
                    "item": entry_name,
                    "type": item_kind,
                    "source": source_label,
                    "destination": archive_label,
                    "destinationPath": destination,
                },
                created_at=_now_iso(),
                color=0xF0B232,
            )
        )

    def send_test_alert(self) -> dict[str, Any]:
        return self.enqueue(
            AlertEvent(
                kind="test",
                title=f"{self.settings.service_name} test alert",
                message=f"{self.settings.service_name} is connected to Discord.",
                fields={},
                created_at=_now_iso(),
                color=0x5865F2,
            )
        )

    def enqueue(self, event: AlertEvent) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"queued": False, "reason": "disabled"}
        if not self.settings.discord_webhook_url:
            self._last_error = "Discord webhook URL is not configured."
            return {"queued": False, "reason": "not_configured"}
        if not self._started:
            self.start()
        try:
            self._queue.put_nowait(event)
            return {"queued": True, "kind": event.kind}
        except queue.Full:
            self._dropped_count += 1
            self._last_error = "Alert queue is full."
            return {"queued": False, "reason": "queue_full"}

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            try:
                self._send_discord(event)
                self._sent_count += 1
                self._last_error = None
                self._last_event = event.to_dict()
            except Exception as exc:  # noqa: BLE001
                self._failed_count += 1
                self._last_error = str(exc)
            finally:
                self._queue.task_done()

    def _send_discord(self, event: AlertEvent) -> None:
        content = event.title
        allowed_mentions = {"parse": []}
        role_id = _extract_role_id(self.settings.discord_mention)
        if role_id:
            content = f"{self.settings.discord_mention} {event.title}"
            allowed_mentions["roles"] = [role_id]

        payload = {
            "username": self.settings.discord_username,
            "content": content,
            "allowed_mentions": allowed_mentions,
            "embeds": [
                {
                    "title": event.title,
                    "description": event.message,
                    "color": event.color,
                    "timestamp": event.created_at,
                    "fields": [
                        {"name": _format_field_name(str(key)), "value": _format_field_value(value), "inline": True}
                        for key, value in event.fields.items()
                        if value is not None and value != ""
                    ],
                    "footer": {"text": self.settings.service_name},
                }
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            self.settings.discord_webhook_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"Nemo-{self.settings.service_name}",
            },
        )
        try:
            with urllib_request.urlopen(request, timeout=15) as response:
                if response.status not in (HTTPStatus.OK, HTTPStatus.NO_CONTENT):
                    raise RuntimeError(f"Discord returned HTTP {response.status}.")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Discord returned HTTP {exc.code}: {detail}") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_role_id(mention: str) -> str | None:
    value = str(mention or "").strip()
    if value.startswith("<@&") and value.endswith(">"):
        role_id = value[3:-1]
        return role_id if role_id.isdigit() else None
    return value if value.isdigit() else None


def _format_field_name(name: str) -> str:
    words = []
    current = ""
    for char in name:
        if char in {"_", "-"}:
            if current:
                words.append(current)
                current = ""
            continue
        if char.isupper() and current:
            words.append(current)
            current = char
            continue
        current += char
    if current:
        words.append(current)
    return " ".join(word.capitalize() for word in words) or name


def _format_field_value(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text:
        return "-"
    if len(text) > 900:
        text = f"{text[:897]}..."
    return f"`{text}`"


_MANAGER: PriestessManager | None = None


def get_priestess_manager() -> PriestessManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PriestessManager(get_settings())
    return _MANAGER
