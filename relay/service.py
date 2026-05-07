from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json
import logging
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from relay.config import RelaySettings

CHUNK_SIZE = 1024 * 256
RELAY_ROUTE_PREFIX = "/relay"
logger = logging.getLogger("nemo.relay")


def normalize_cp_path(path: str) -> str:
    value = str(path or "").replace("\\", "/")
    segments: list[str] = []
    for raw_piece in value.split("/"):
        piece = raw_piece.strip()
        if not piece or piece == ".":
            continue
        if piece == "..":
            if segments:
                segments.pop()
            continue
        segments.append(piece)
    return "/" + "/".join(segments) if segments else "/"


def quote_cp_path(path: str) -> str:
    normalized = normalize_cp_path(path)
    quoted_segments = [
        urllib_parse.quote(segment, safe="")
        for segment in normalized.split("/")
        if segment
    ]
    return "/" + "/".join(quoted_segments)


def join_cp_paths(base: str, child: str) -> str:
    return normalize_cp_path(f"{base}/{child}")


def strip_leaked_upload_root(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    if normalized.lower().startswith(("tree/", "document/")):
        match = normalized.split("/", 2)
        if len(match) >= 2:
            head = match[1]
            tail = match[2] if len(match) > 2 else ""
            colon_index = head.find(":")
            head = head if colon_index == -1 else head[colon_index + 1 :]
            normalized = head + (f"/{tail}" if tail else "")
    for prefix in ("primary:", "raw:", "home:", "download:", "downloads:", "msf:"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    trimmed = normalized.lstrip("/")
    for prefix in ("storage/emulated/0/", "sdcard/"):
        if trimmed.lower().startswith(prefix):
            return trimmed[len(prefix) :]
    return normalized


def normalize_relative_path(path: str) -> str:
    return normalize_cp_path(strip_leaked_upload_root(path)).lstrip("/")


SHARED_ANDROID_ROOT_SEGMENTS = {
    "alarms",
    "audiobooks",
    "bluetooth",
    "dcim",
    "documents",
    "download",
    "downloads",
    "movies",
    "music",
    "notifications",
    "pictures",
    "podcasts",
    "recordings",
    "ringtones",
}


def strip_shared_android_root_segment(relative_paths: list[str]) -> list[str]:
    if not relative_paths:
        return relative_paths

    segmented = [normalize_relative_path(path).split("/") for path in relative_paths]
    if any(len(parts) < 2 for parts in segmented):
        return relative_paths

    shared_root = segmented[0][0].lower()
    if shared_root not in SHARED_ANDROID_ROOT_SEGMENTS:
        return relative_paths
    if any(parts[0].lower() != shared_root for parts in segmented):
        return relative_paths
    return ["/".join(parts[1:]) for parts in segmented]


def split_relative_path(path: str) -> tuple[str, str]:
    normalized = normalize_relative_path(path)
    parts = [piece for piece in normalized.split("/") if piece]
    file_name = parts[-1] if parts else "file.bin"
    return ("/".join(parts[:-1]), file_name)


def slugify(value: str) -> str:
    buffer: list[str] = []
    last_dash = False
    for char in str(value or "").lower():
        if char.isalnum():
            buffer.append(char)
            last_dash = False
            continue
        if not last_dash:
            buffer.append("-")
            last_dash = True
    result = "".join(buffer).strip("-")
    return result or "device"


def split_file_name(name: str) -> tuple[str, str]:
    dot_index = name.rfind(".")
    if dot_index <= 0 or dot_index >= len(name) - 1:
        return name, ""
    return name[:dot_index], name[dot_index:]


def append_name_suffix(name: str, suffix: str) -> str:
    stem, ext = split_file_name(name)
    return f"{stem}-{suffix}{ext}" if ext else f"{stem}-{suffix}"


def leaf_name(path: str) -> str:
    return normalize_cp_path(path).rstrip("/").split("/")[-1]


def create_payload_name(device_id: str, item_count: int) -> str:
    from datetime import datetime, timezone

    timestamp = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
        .replace(":", "-")
        .replace("T", "_")
    )
    item_label = f"{item_count}-item" if item_count == 1 else f"{item_count}-items"
    return f"from-{slugify(device_id)}-{timestamp}-{item_label}-{secrets.token_hex(2)}"


def guess_content_type(name: str, fallback: str = "application/octet-stream") -> str:
    mime, _encoding = mimetypes.guess_type(name)
    return mime or fallback


@dataclass
class CopypartyResponse:
    status: int
    reason: str
    headers: dict[str, str]
    body: bytes


@dataclass
class DownloadHandle:
    stream: Any
    content_type: str
    file_name: str


class CopypartyClient:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.password = password.strip()

    def build_url(self, cp_path: str, extra_query: dict[str, Any] | None = None) -> str:
        split = urllib_parse.urlsplit(self.base_url)
        path = normalize_cp_path(cp_path)
        joined_path = quote_cp_path(join_cp_paths(split.path or "/", path))
        query_pairs = urllib_parse.parse_qsl(split.query, keep_blank_values=True)
        if self.password and not any(key == "pw" for key, _value in query_pairs):
            query_pairs.append(("pw", self.password))
        if extra_query:
            for key, value in extra_query.items():
                if isinstance(value, list):
                    for item in value:
                        query_pairs.append((key, str(item)))
                else:
                    query_pairs.append((key, "" if value is None else str(value)))
        query = urllib_parse.urlencode(query_pairs, doseq=True)
        return urllib_parse.urlunsplit((split.scheme, split.netloc, joined_path, query, ""))

    def destination_url(self, cp_path: str) -> str:
        return self.build_url(cp_path)

    def request(
        self,
        method: str,
        cp_path: str,
        extra_query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 120,
    ) -> CopypartyResponse:
        url = self.build_url(cp_path, extra_query)
        request = urllib_request.Request(url=url, method=method, headers=headers or {}, data=body)
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                return CopypartyResponse(
                    status=response.status,
                    reason=response.reason,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib_error.HTTPError as error:
            return CopypartyResponse(
                status=error.code,
                reason=error.reason,
                headers=dict(error.headers.items()),
                body=error.read(),
            )

    def probe(self, timeout: float = 3.0) -> tuple[bool, str | None, int | None]:
        try:
            response = self.request("GET", "/", timeout=timeout)
            if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                return (
                    False,
                    f"Copyparty rejected the configured credentials (HTTP {response.status}).",
                    response.status,
                )
            return True, None, response.status
        except urllib_error.URLError as error:
            reason = getattr(error, "reason", None) or error
            return False, f"Copyparty request failed: {reason}", None

    def ensure_folder(self, cp_path: str) -> None:
        segments = [piece for piece in normalize_cp_path(cp_path).split("/") if piece]
        cursor = "/"
        for segment in segments:
            cursor = join_cp_paths(cursor, segment)
            response = self.request("MKCOL", cursor)
            if response.status in (
                HTTPStatus.OK,
                HTTPStatus.CREATED,
                HTTPStatus.NO_CONTENT,
                HTTPStatus.METHOD_NOT_ALLOWED,
                HTTPStatus.CONFLICT,
            ):
                continue
            raise RuntimeError(f"Unable to create {cursor} (HTTP {response.status}).")

    def move(self, source_path: str, destination_path: str) -> CopypartyResponse:
        return self.request(
            "MOVE",
            source_path,
            headers={
                "Destination": self.destination_url(destination_path),
                "Overwrite": "T",
            },
        )

    def delete(self, cp_path: str) -> CopypartyResponse:
        return self.request("DELETE", cp_path)

    def upload_stream(
        self,
        cp_path: str,
        stream: Any,
        file_name: str,
        content_type: str | None = None,
    ) -> CopypartyResponse:
        url = self.build_url(cp_path, {"j": ""})
        split = urllib_parse.urlsplit(url)
        request_path = urllib_parse.urlunsplit(("", "", split.path, split.query, ""))
        boundary = f"relay-{secrets.token_hex(12)}"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="f"; filename="{file_name}"\r\n'
            f"Content-Type: {content_type or guess_content_type(file_name)}\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        stream.seek(0, os.SEEK_SET)
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0, os.SEEK_SET)
        content_length = len(prefix) + size + len(suffix)

        import http.client

        connection_cls = http.client.HTTPSConnection if split.scheme == "https" else http.client.HTTPConnection
        connection = connection_cls(split.hostname, split.port, timeout=600)
        try:
            connection.putrequest("POST", request_path)
            connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            connection.putheader("Content-Length", str(content_length))
            connection.putheader("Host", split.netloc)
            connection.endheaders()
            connection.send(prefix)
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                connection.send(chunk)
            connection.send(suffix)
            response = connection.getresponse()
            return CopypartyResponse(
                status=response.status,
                reason=response.reason,
                headers={key: value for key, value in response.getheaders()},
                body=response.read(),
            )
        finally:
            connection.close()

    def open_download(self, cp_path: str, kind: str):
        extra_query = {"zip": ""} if kind == "payload" else None
        return urllib_request.urlopen(self.build_url(cp_path, extra_query), timeout=600)


class RelayConfig:
    def __init__(self, raw: dict[str, Any], settings: RelaySettings):
        self.project_name = settings.project_name
        self.base_url = settings.copyparty_base_url.rstrip("/")
        self.password = settings.copyparty_password
        self.inbox_root = normalize_cp_path(settings.inbox_root)
        self.dump_root = normalize_cp_path(settings.dump_root)
        self.local_storage_root = settings.legacy_root / "device-handoff"

        raw_devices = raw.get("devices")
        if not isinstance(raw_devices, list) or not raw_devices:
            raise ValueError("Config must include at least one device.")

        self.devices = [self._normalize_device(entry) for entry in raw_devices]
        self.devices_by_id = {device["id"]: device for device in self.devices}
        if len(self.devices_by_id) != len(self.devices):
            raise ValueError("Device ids must be unique.")
        hub_device_id = str(raw.get("hubDeviceId") or "pit").strip() or "pit"
        if hub_device_id not in self.devices_by_id:
            hub_device_id = self.devices[0]["id"]
        self.hub_device_id = hub_device_id
        self.hub_device = self.devices_by_id[self.hub_device_id]

        targets = [
            {
                "id": device["id"],
                "label": device["targetLabel"],
                "path": device["inboxPath"],
            }
            for device in self.devices
            if device["id"] != self.hub_device_id
        ]
        for device in self.devices:
            device["targets"] = targets
            device["defaultTargetId"] = device.get("defaultTargetId") or "pit"
            if device["defaultTargetId"] == self.hub_device_id or device["defaultTargetId"] not in self.devices_by_id:
                device["defaultTargetId"] = targets[0]["id"] if targets else device["id"]

        self.copyparty = CopypartyClient(self.base_url, self.password)

    def _normalize_device(self, raw_device: dict[str, Any]) -> dict[str, Any]:
        device_id = str(raw_device.get("id") or "").strip()
        if not device_id:
            raise ValueError("Each device must define an id.")

        slug = str(raw_device.get("slug") or device_id).strip() or device_id
        mailbox = str(raw_device.get("mailbox") or device_id).strip() or device_id
        device = {
            "id": device_id,
            "slug": slugify(slug),
            "mailbox": mailbox,
            "name": str(raw_device.get("name") or device_id),
            "targetLabel": str(raw_device.get("targetLabel") or raw_device.get("name") or device_id),
            "tagline": str(raw_device.get("tagline") or ""),
            "accentColor": str(raw_device.get("accentColor") or "#5bb0ff"),
            "accentColorStrong": str(raw_device.get("accentColorStrong") or "#7ac2ff"),
            "themeColor": str(raw_device.get("themeColor") or raw_device.get("accentColor") or "#5bb0ff"),
            "capture": bool(raw_device.get("capture")),
            "defaultTargetId": str(raw_device.get("defaultTargetId") or "pit"),
            "shortName": str(raw_device.get("shortName") or raw_device.get("name") or device_id),
        }
        device["inboxPath"] = join_cp_paths(self.inbox_root, mailbox)
        device["dumpPath"] = join_cp_paths(self.dump_root, mailbox)
        device["pagePath"] = f"{RELAY_ROUTE_PREFIX}/devices/{device['slug']}.html"
        device["manifestPath"] = f"{RELAY_ROUTE_PREFIX}/manifests/{device['slug']}.webmanifest"
        return device

    def require_device(self, device_id: str) -> dict[str, Any]:
        device = self.devices_by_id.get(device_id)
        if device is None:
            raise KeyError(f"Unknown device '{device_id}'.")
        return device

    def get_device_by_slug(self, slug: str) -> dict[str, Any] | None:
        normalized_slug = slugify(slug)
        for device in self.devices:
            if device["slug"] == normalized_slug:
                return device
        return None

    def bootstrap_for(self, device_id: str, copyparty_status: dict[str, Any]) -> dict[str, Any]:
        device = self.require_device(device_id)
        return {
            "projectName": self.project_name,
            "copyparty": copyparty_status,
            "copypartyBaseUrl": self.base_url,
            "device": {
                "id": device["id"],
                "slug": device["slug"],
                "name": device["name"],
                "shortName": device["shortName"],
                "tagline": device["tagline"],
                "accentColor": device["accentColor"],
                "accentColorStrong": device["accentColorStrong"],
                "themeColor": device["themeColor"],
                "inboxPath": device["inboxPath"],
                "dumpPath": device["dumpPath"],
                "capture": device["capture"],
                "defaultTargetId": device["defaultTargetId"],
                "pagePath": device["pagePath"],
                "manifestPath": device["manifestPath"],
            },
            "targets": device["targets"],
            "handoffArchive": {
                "deviceId": self.hub_device["id"],
                "label": self.hub_device["targetLabel"],
                "path": self.hub_device["dumpPath"],
            },
            "devices": [
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "shortName": entry["shortName"],
                    "pagePath": entry["pagePath"],
                    "accentColor": entry["accentColor"],
                }
                for entry in self.devices
            ],
        }

    def build_manifest(self, device_id: str) -> dict[str, Any]:
        device = self.require_device(device_id)
        return {
            "name": f"{device['name']} | {self.project_name}",
            "short_name": device["shortName"],
            "start_url": device["pagePath"],
            "scope": f"{RELAY_ROUTE_PREFIX}/",
            "display": "standalone",
            "background_color": "#101217",
            "theme_color": device["themeColor"],
            "description": device["tagline"] or f"{self.project_name} mailbox for {device['name']}.",
            "icons": [
                {
                    "src": f"{RELAY_ROUTE_PREFIX}/assets/icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        }


class RelayService:
    def __init__(self, config: RelayConfig):
        self.config = config

    def _resolve_local_cp_path(self, cp_path: str) -> Path:
        root = self.config.local_storage_root.resolve()
        relative = normalize_cp_path(cp_path).lstrip("/")
        candidate = (root / relative).resolve()
        if root not in {candidate, *candidate.parents}:
            raise RuntimeError(f"Refusing to access path outside Relay storage: {cp_path}")
        return candidate

    def _move_entry_locally(self, source_path: str, destination_path: str) -> None:
        source = self._resolve_local_cp_path(source_path)
        destination = self._resolve_local_cp_path(destination_path)
        if not source.exists():
            raise RuntimeError(f"Source item no longer exists: {source_path}")
        if destination.exists():
            raise RuntimeError(f"Destination already exists: {destination_path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

    def get_devices_payload(self, copyparty_status: dict[str, Any]) -> dict[str, Any]:
        return {
            "projectName": self.config.project_name,
            "copyparty": copyparty_status,
            "devices": [
                {
                    "id": device["id"],
                    "name": device["name"],
                    "shortName": device["shortName"],
                    "tagline": device["tagline"],
                    "pagePath": device["pagePath"],
                    "accentColor": device["accentColor"],
                }
                for device in self.config.devices
            ],
        }

    def list_inbox(self, device_id: str) -> dict[str, Any]:
        device = self.config.require_device(urllib_parse.unquote(device_id))
        response = self.config.copyparty.request("GET", device["inboxPath"], {"ls": ""})
        if response.status == HTTPStatus.NOT_FOUND:
            return {
                "dirs": [],
                "files": [],
                "missing": True,
                "inboxPath": device["inboxPath"],
            }
        if response.status != HTTPStatus.OK:
            raise RuntimeError(f"Listing failed with HTTP {response.status}.")

        payload = json.loads(response.body.decode("utf-8"))
        logger.info(
            "Relay inbox listed for %s: %s dirs, %s files.",
            device["id"],
            len(payload.get("dirs", [])),
            len(payload.get("files", [])),
        )
        return {
            "dirs": payload.get("dirs", []),
            "files": payload.get("files", []),
            "missing": False,
            "inboxPath": device["inboxPath"],
        }

    def send_payload(self, device_id: str, target_id: str, relative_paths: list[str], files: list[Any]) -> dict[str, Any]:
        device = self.config.require_device(urllib_parse.unquote(device_id))
        target = self.config.require_device(target_id)
        logger.info(
            "Relay send requested: source=%s target=%s items=%s.",
            device["id"],
            target["id"],
            len(files),
        )
        if target["id"] == self.config.hub_device_id:
            raise ValueError("Relay Hub is reserved for downloaded handoff storage and cannot be selected as a send destination.")
        if not files:
            raise ValueError("No files were uploaded.")
        if len(relative_paths) != len(files):
            raise ValueError("Uploaded files did not match their relative paths.")

        normalized_relative_paths = [normalize_relative_path(str(path)) for path in relative_paths]
        normalized_relative_paths = strip_shared_android_root_segment(normalized_relative_paths)
        payload_name = create_payload_name(device["id"], len(files))
        payload_path = join_cp_paths(target["inboxPath"], payload_name)
        self.config.copyparty.ensure_folder(target["inboxPath"])
        self.config.copyparty.ensure_folder(payload_path)

        created_directories = {payload_path}
        success_count = 0
        failures: list[str] = []

        for index, upload in enumerate(files):
            relative_path = normalized_relative_paths[index] or (getattr(upload, "filename", None) or "file.bin")
            directory, file_name = split_relative_path(relative_path)
            destination_directory = join_cp_paths(payload_path, directory) if directory else payload_path
            if destination_directory not in created_directories:
                self.config.copyparty.ensure_folder(destination_directory)
                created_directories.add(destination_directory)

            stream = getattr(upload, "file", None)
            if stream is None:
                failures.append(f"{relative_path}: missing upload stream")
                continue

            response = self.config.copyparty.upload_stream(
                destination_directory,
                stream,
                file_name,
                getattr(upload, "content_type", None),
            )
            if 200 <= response.status < 300:
                success_count += 1
                continue
            failures.append(f"{relative_path}: HTTP {response.status}")

        logger.info(
            "Relay payload %s sent: source=%s target=%s uploaded=%s failed=%s.",
            payload_name,
            device["id"],
            target["id"],
            success_count,
            len(failures),
        )
        return {
            "payloadName": payload_name,
            "sourceDeviceId": device["id"],
            "sourceDeviceName": device["name"],
            "targetDeviceId": target["id"],
            "targetDeviceName": target["name"],
            "targetLabel": target["targetLabel"],
            "targetInboxPath": target["inboxPath"],
            "uploaded": success_count,
            "failed": failures,
        }

    def archive_entry(self, device_id: str, entry_name: str, kind: str) -> dict[str, Any]:
        device = self.config.require_device(urllib_parse.unquote(device_id))
        entry_name = leaf_name(entry_name)
        if not entry_name or kind not in {"payload", "file"}:
            raise ValueError("Archive requests require a valid entry name and kind.")

        source_path = join_cp_paths(device["inboxPath"], entry_name)
        archive_device = self.config.hub_device
        archive_root = archive_device["dumpPath"]
        logger.info(
            "Relay archive requested: source=%s entry=%s kind=%s archive=%s.",
            device["id"],
            entry_name,
            kind,
            archive_device["id"],
        )
        self.config.copyparty.ensure_folder(archive_root)
        destination_name = entry_name
        destination_path = join_cp_paths(archive_root, destination_name)
        archive_action = "moved_to_hub_handoff"
        download_entry_name = destination_name
        download_kind = kind

        if normalize_cp_path(source_path) == normalize_cp_path(destination_path):
            response = CopypartyResponse(
                status=HTTPStatus.OK,
                reason="Already in Relay Hub handoff",
                headers={},
                body=b"",
            )
            archive_action = "already_in_hub_handoff"
        else:
            response = self.config.copyparty.move(source_path, destination_path)

        if response.status in (HTTPStatus.CONFLICT, HTTPStatus.PRECONDITION_FAILED):
            destination_name = append_name_suffix(entry_name, secrets.token_hex(2))
            destination_path = join_cp_paths(archive_root, destination_name)
            response = self.config.copyparty.move(source_path, destination_path)
            download_entry_name = destination_name
        if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN, HTTPStatus.METHOD_NOT_ALLOWED):
            self._move_entry_locally(source_path, destination_path)
            archive_action = "moved_locally_to_hub_handoff"
        elif response.status not in (HTTPStatus.CREATED, HTTPStatus.NO_CONTENT, HTTPStatus.OK):
            raise RuntimeError(f"Unable to move item into {archive_root} (HTTP {response.status}).")

        download_name = f"{download_entry_name}.zip" if download_kind == "payload" else download_entry_name
        encoded_name = urllib_parse.quote(download_entry_name, safe="")
        logger.info(
            "Relay archived %s from %s to %s via %s.",
            entry_name,
            device["id"],
            destination_path,
            archive_action,
        )
        return {
            "downloadUrl": (
                f"/api/relay/device/{archive_device['id']}/download/{encoded_name}"
                f"?kind={download_kind}&storage=dump"
            ),
            "entryName": entry_name,
            "downloadEntryName": download_entry_name,
            "kind": kind,
            "suggestedName": download_name,
            "destinationPath": destination_path,
            "archiveAction": archive_action,
            "archiveDeviceId": archive_device["id"],
            "archiveDeviceName": archive_device["name"],
            "archiveDeviceLabel": archive_device["targetLabel"],
            "sourceDeviceId": device["id"],
            "sourceDeviceName": device["name"],
        }

    def prepare_download(self, device_id: str, entry_name: str, kind: str, storage: str = "dump") -> DownloadHandle:
        device = self.config.require_device(urllib_parse.unquote(device_id))
        normalized_name = leaf_name(urllib_parse.unquote(entry_name))
        logger.info(
            "Relay download requested: device=%s entry=%s kind=%s storage=%s.",
            device["id"],
            normalized_name,
            kind,
            storage,
        )
        if kind not in {"file", "payload"}:
            raise ValueError("Invalid download kind.")
        if storage not in {"dump", "inbox"}:
            raise ValueError("Invalid download storage.")

        root_path = device["inboxPath"] if storage == "inbox" else device["dumpPath"]
        source_path = join_cp_paths(root_path, normalized_name)
        response = self.config.copyparty.open_download(source_path, kind)
        status = getattr(response, "status", HTTPStatus.OK)
        if status != HTTPStatus.OK:
            response.close()
            raise RuntimeError(f"Download failed with HTTP {status}.")

        file_name = f"{normalized_name}.zip" if kind == "payload" else normalized_name
        content_type = response.headers.get_content_type()
        logger.info("Relay download prepared: device=%s file=%s.", device["id"], file_name)
        return DownloadHandle(stream=response, content_type=content_type, file_name=file_name)

    def initialize_mailboxes(self) -> dict[str, Any]:
        logger.info("Relay mailbox initialization started.")
        self.config.copyparty.ensure_folder(self.config.inbox_root)
        self.config.copyparty.ensure_folder(self.config.dump_root)
        for device in self.config.devices:
            self.config.copyparty.ensure_folder(device["inboxPath"])
            self.config.copyparty.ensure_folder(device["dumpPath"])

        logger.info("Relay mailbox initialization complete for %s devices.", len(self.config.devices))
        return {
            "status": "ok",
            "inboxRoot": self.config.inbox_root,
            "dumpRoot": self.config.dump_root,
            "devices": [
                {
                    "id": device["id"],
                    "inboxPath": device["inboxPath"],
                    "dumpPath": device["dumpPath"],
                }
                for device in self.config.devices
            ],
        }


def load_relay_config(settings: RelaySettings) -> RelayConfig:
    if not settings.config_path.exists():
        raise FileNotFoundError(f"Relay config not found: {settings.config_path}")

    with settings.config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return RelayConfig(raw, settings)


def resolve_error_message(error: Exception) -> str:
    if isinstance(error, urllib_error.URLError):
        reason = getattr(error, "reason", None)
        if reason:
            return f"Copyparty request failed: {reason}"
        return "Copyparty request failed."
    if isinstance(error, (KeyError, ValueError, RuntimeError, FileNotFoundError)):
        return str(error)
    return f"{type(error).__name__}: {error}"
