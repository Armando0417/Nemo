from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)

import cgi
import http.client
import json
import mimetypes
import os
import posixpath
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
CHUNK_SIZE = 1024 * 256


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


def join_cp_paths(base: str, child: str) -> str:
	return normalize_cp_path(f"{base}/{child}")


def normalize_relative_path(path: str) -> str:
	return normalize_cp_path(strip_leaked_upload_root(path)).lstrip("/")


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


def append_name_suffix(name: str, suffix: str) -> str:
	stem, ext = split_file_name(name)
	return f"{stem}-{suffix}{ext}" if ext else f"{stem}-{suffix}"


def split_file_name(name: str) -> tuple[str, str]:
	dot_index = name.rfind(".")
	if dot_index <= 0 or dot_index >= len(name) - 1:
		return name, ""
	return name[:dot_index], name[dot_index:]


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
class UploadStreamField:
	file: Any
	type: str | None = None


class CopypartyClient:
	def __init__(self, base_url: str, password: str):
		self.base_url = base_url.rstrip("/")
		self.password = password.strip()

	def build_url(self, cp_path: str, extra_query: dict[str, Any] | None = None) -> str:
		split = urllib_parse.urlsplit(self.base_url)
		path = normalize_cp_path(cp_path)
		joined_path = join_cp_paths(split.path or "/", path)
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
	) -> CopypartyResponse:
		url = self.build_url(cp_path, extra_query)
		request = urllib_request.Request(url=url, method=method, headers=headers or {}, data=body)
		try:
			with urllib_request.urlopen(request, timeout=120) as response:
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

	def ensure_folder(self, cp_path: str) -> None:
		segments = [piece for piece in normalize_cp_path(cp_path).split("/") if piece]
		cursor = "/"
		for segment in segments:
			cursor = join_cp_paths(cursor, segment)
			response = self.request("MKCOL", cursor)
			if response.status in (HTTPStatus.CREATED, HTTPStatus.METHOD_NOT_ALLOWED, HTTPStatus.CONFLICT):
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

	def _upload_stream(self, cp_path: str, stream: Any, file_name: str, content_type: str) -> CopypartyResponse:
		url = self.build_url(cp_path, {"j": ""})
		split = urllib_parse.urlsplit(url)
		request_path = urllib_parse.urlunsplit(("", "", split.path, split.query, ""))
		boundary = f"titanrelay-{secrets.token_hex(12)}"
		prefix = (
			f"--{boundary}\r\n"
			f'Content-Disposition: form-data; name="f"; filename="{file_name}"\r\n'
			f"Content-Type: {content_type}\r\n\r\n"
		).encode("utf-8")
		suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
		stream.seek(0, os.SEEK_SET)
		stream.seek(0, os.SEEK_END)
		size = stream.tell()
		stream.seek(0, os.SEEK_SET)
		content_length = len(prefix) + size + len(suffix)

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

	def upload_file(self, cp_path: str, field: cgi.FieldStorage, file_name: str) -> CopypartyResponse:
		stream = field.file
		if stream is None:
			raise RuntimeError(f"No file stream provided for {file_name}.")
		return self._upload_stream(cp_path, stream, file_name, field.type or guess_content_type(file_name))

	def upload_stream(
		self,
		cp_path: str,
		stream: Any,
		file_name: str,
		content_type: str | None = None,
	) -> CopypartyResponse:
		return self._upload_stream(cp_path, stream, file_name, content_type or guess_content_type(file_name))

	def open_download(self, cp_path: str, kind: str):
		extra_query = {"zip": ""} if kind == "payload" else None
		return urllib_request.urlopen(self.build_url(cp_path, extra_query), timeout=600)


class TitanRelayConfig:
	def __init__(self, raw: dict[str, Any]):
		self.project_name = str(raw.get("projectName") or "TitanRelay").strip() or "TitanRelay"
		server = raw.get("server") or {}
		self.host = str(server.get("host") or "127.0.0.1")
		self.port = int(server.get("port") or 8732)
		copyparty = raw.get("copyparty") or {}
		self.base_url = str(copyparty.get("baseUrl") or "http://127.0.0.1:3923").rstrip("/")
		self.password = str(copyparty.get("password") or "")
		mailboxes = raw.get("mailboxes") or {}
		self.inbox_root = normalize_cp_path(str(mailboxes.get("inboxRoot") or "/device-handoff"))
		self.dump_root = normalize_cp_path(str(mailboxes.get("dumpRoot") or "/device-handoff-dump"))
		raw_devices = raw.get("devices")
		if not isinstance(raw_devices, list) or not raw_devices:
			raise ValueError("Config must include at least one device.")
		self.devices = [self._normalize_device(entry) for entry in raw_devices]
		self.devices_by_id = {device["id"]: device for device in self.devices}
		if len(self.devices_by_id) != len(self.devices):
			raise ValueError("Device ids must be unique.")
		targets = [
			{
				"id": device["id"],
				"label": device["targetLabel"],
				"path": device["inboxPath"],
			}
			for device in self.devices
		]
		for device in self.devices:
			device["targets"] = targets
			device["defaultTargetId"] = device.get("defaultTargetId") or "pit"
			if device["defaultTargetId"] not in self.devices_by_id:
				device["defaultTargetId"] = self.devices[0]["id"]
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
		device["pagePath"] = f"/devices/{device['slug']}.html"
		device["manifestPath"] = f"/manifests/{device['slug']}.webmanifest"
		return device

	def bootstrap_for(self, device_id: str) -> dict[str, Any]:
		device = self.require_device(device_id)
		return {
			"projectName": self.project_name,
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

	def require_device(self, device_id: str) -> dict[str, Any]:
		device = self.devices_by_id.get(device_id)
		if device is None:
			raise KeyError(f"Unknown device '{device_id}'.")
		return device

	def build_manifest(self, device_id: str) -> dict[str, Any]:
		device = self.require_device(device_id)
		return {
			"name": f"{device['name']} | {self.project_name}",
			"short_name": device["shortName"],
			"start_url": device["pagePath"],
			"scope": "/",
			"display": "standalone",
			"background_color": "#101217",
			"theme_color": device["themeColor"],
			"description": device["tagline"] or f"{self.project_name} mailbox for {device['name']}.",
			"icons": [
				{
					"src": "/assets/icon.svg",
					"sizes": "any",
					"type": "image/svg+xml",
					"purpose": "any maskable",
				}
			],
		}


def load_config(path: Path) -> TitanRelayConfig:
	with path.open("r", encoding="utf-8") as handle:
		raw = json.load(handle)
	return TitanRelayConfig(raw)


def resolve_error_message(error: Exception) -> str:
	if isinstance(error, urllib_error.URLError):
		reason = getattr(error, "reason", None)
		if reason:
			return f"Copyparty request failed: {reason}"
		return "Copyparty request failed."
	if isinstance(error, (KeyError, ValueError, RuntimeError)):
		return str(error)
	return f"{type(error).__name__}: {error}"


class TitanRelayRequestHandler(SimpleHTTPRequestHandler):
	server_version = "TitanRelay/1.0"

	def __init__(self, *args, directory: str | None = None, **kwargs):
		super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

	@property
	def relay_config(self) -> TitanRelayConfig:
		return self.server.relay_config  # type: ignore[attr-defined]

	def do_GET(self) -> None:
		parsed = urllib_parse.urlsplit(self.path)
		if parsed.path.startswith("/api/"):
			self.handle_api_get(parsed)
			return
		if parsed.path.startswith("/manifests/") and parsed.path.endswith(".webmanifest"):
			self.handle_manifest(parsed.path)
			return
		super().do_GET()

	def do_POST(self) -> None:
		parsed = urllib_parse.urlsplit(self.path)
		if not parsed.path.startswith("/api/"):
			self.send_error(HTTPStatus.NOT_FOUND)
			return
		self.handle_api_post(parsed)

	def log_message(self, format: str, *args: Any) -> None:
		sys.stdout.write(f"[TitanRelay] {self.address_string()} - {format % args}\n")

	def end_headers(self) -> None:
		self.send_header("Cache-Control", "no-store")
		super().end_headers()

	def handle_api_get(self, parsed) -> None:
		path = parsed.path
		if path == "/api/health":
			self.write_json({"ok": True, "projectName": self.relay_config.project_name})
			return
		if path == "/api/devices":
			self.write_json(
				{
					"projectName": self.relay_config.project_name,
					"devices": [
						{
							"id": device["id"],
							"name": device["name"],
							"shortName": device["shortName"],
							"tagline": device["tagline"],
							"pagePath": device["pagePath"],
							"accentColor": device["accentColor"],
						}
						for device in self.relay_config.devices
					],
				}
			)
			return
		if path.startswith("/api/bootstrap/"):
			device_id = urllib_parse.unquote(path.removeprefix("/api/bootstrap/"))
			self.write_json(self.relay_config.bootstrap_for(device_id))
			return
		if path.startswith("/api/device/") and path.endswith("/inbox"):
			device_id = path[len("/api/device/") : -len("/inbox")]
			self.handle_inbox_listing(device_id)
			return
		if path.startswith("/api/device/") and "/download/" in path:
			self.handle_download(path, urllib_parse.parse_qs(parsed.query, keep_blank_values=True))
			return
		self.send_error(HTTPStatus.NOT_FOUND)

	def handle_api_post(self, parsed) -> None:
		path = parsed.path
		if path.startswith("/api/device/") and path.endswith("/send"):
			device_id = path[len("/api/device/") : -len("/send")]
			self.handle_send(device_id)
			return
		if path.startswith("/api/device/") and path.endswith("/archive"):
			device_id = path[len("/api/device/") : -len("/archive")]
			self.handle_archive(device_id)
			return
		self.send_error(HTTPStatus.NOT_FOUND)

	def handle_manifest(self, path: str) -> None:
		slug = path.removeprefix("/manifests/").removesuffix(".webmanifest")
		for device in self.relay_config.devices:
			if device["slug"] == slug:
				self.write_json(self.relay_config.build_manifest(device["id"]), content_type="application/manifest+json")
				return
		self.send_error(HTTPStatus.NOT_FOUND)

	def handle_inbox_listing(self, device_id: str) -> None:
		try:
			device = self.relay_config.require_device(urllib_parse.unquote(device_id))
			response = self.relay_config.copyparty.request("GET", device["inboxPath"], {"ls": ""})
			if response.status == HTTPStatus.NOT_FOUND:
				self.write_json(
					{
						"dirs": [],
						"files": [],
						"missing": True,
						"inboxPath": device["inboxPath"],
					}
				)
				return
			if response.status != HTTPStatus.OK:
				raise RuntimeError(f"Listing failed with HTTP {response.status}.")
			payload = json.loads(response.body.decode("utf-8"))
			self.write_json(
				{
					"dirs": payload.get("dirs", []),
					"files": payload.get("files", []),
					"missing": False,
					"inboxPath": device["inboxPath"],
				}
			)
		except Exception as error:  # noqa: BLE001
			self.write_json({"error": resolve_error_message(error)}, status=HTTPStatus.BAD_GATEWAY)

	def handle_send(self, device_id: str) -> None:
		try:
			device = self.relay_config.require_device(urllib_parse.unquote(device_id))
			content_type = self.headers.get("Content-Type", "")
			if "multipart/form-data" not in content_type:
				raise ValueError("Send requests must use multipart/form-data.")
			form = cgi.FieldStorage(
				fp=self.rfile,
				headers=self.headers,
				environ={
					"REQUEST_METHOD": "POST",
					"CONTENT_TYPE": content_type,
					"CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
				},
				keep_blank_values=True,
			)
			target_id = str(form.getfirst("targetId") or "").strip()
			target = self.relay_config.require_device(target_id)
			relative_paths = json.loads(str(form.getfirst("relativePaths") or "[]"))
			file_fields = form["file"] if "file" in form else []
			if isinstance(file_fields, list):
				files = file_fields
			elif isinstance(file_fields, cgi.FieldStorage):
				files = [file_fields]
			else:
				files = []
			if not files:
				raise ValueError("No files were uploaded.")
			if not isinstance(relative_paths, list) or len(relative_paths) != len(files):
				raise ValueError("Uploaded files did not match their relative paths.")

			normalized_relative_paths = [normalize_relative_path(str(path)) for path in relative_paths]
			normalized_relative_paths = strip_shared_android_root_segment(normalized_relative_paths)
			payload_name = create_payload_name(device["id"], len(files))
			payload_path = join_cp_paths(target["inboxPath"], payload_name)
			self.relay_config.copyparty.ensure_folder(target["inboxPath"])
			self.relay_config.copyparty.ensure_folder(payload_path)

			created_directories = {payload_path}
			success_count = 0
			failures: list[str] = []
			for index, field in enumerate(files):
				relative_path = normalized_relative_paths[index] or (field.filename or "file.bin")
				directory, file_name = split_relative_path(relative_path)
				destination_directory = join_cp_paths(payload_path, directory) if directory else payload_path
				if destination_directory not in created_directories:
					self.relay_config.copyparty.ensure_folder(destination_directory)
					created_directories.add(destination_directory)
				response = self.relay_config.copyparty.upload_file(destination_directory, field, file_name)
				if 200 <= response.status < 300:
					success_count += 1
					continue
				failures.append(f"{relative_path}: HTTP {response.status}")

			self.write_json(
				{
					"payloadName": payload_name,
					"targetLabel": target["targetLabel"],
					"uploaded": success_count,
					"failed": failures,
				}
			)
		except Exception as error:  # noqa: BLE001
			self.write_json({"error": resolve_error_message(error)}, status=HTTPStatus.BAD_GATEWAY)

	def handle_archive(self, device_id: str) -> None:
		try:
			device = self.relay_config.require_device(urllib_parse.unquote(device_id))
			payload = self.read_json_body()
			entry_name = leaf_name(str(payload.get("name") or ""))
			kind = str(payload.get("kind") or "")
			if not entry_name or kind not in {"payload", "file"}:
				raise ValueError("Archive requests require a valid entry name and kind.")
			source_path = join_cp_paths(device["inboxPath"], entry_name)
			self.relay_config.copyparty.ensure_folder(device["dumpPath"])
			destination_name = entry_name
			destination_path = join_cp_paths(device["dumpPath"], destination_name)
			response = self.relay_config.copyparty.move(source_path, destination_path)
			archive_action = "moved"
			download_entry_name = destination_name
			download_kind = kind
			if response.status in (HTTPStatus.CONFLICT, HTTPStatus.PRECONDITION_FAILED):
				destination_name = append_name_suffix(entry_name, secrets.token_hex(2))
				destination_path = join_cp_paths(device["dumpPath"], destination_name)
				response = self.relay_config.copyparty.move(source_path, destination_path)
			if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
				download_entry_name, download_kind, destination_path = self.copy_entry_to_dump(
					source_path,
					device["dumpPath"],
					destination_name,
					kind,
				)
				archive_action = "copied"
			elif response.status not in (HTTPStatus.CREATED, HTTPStatus.NO_CONTENT, HTTPStatus.OK):
				raise RuntimeError(f"Unable to move item into {device['dumpPath']} (HTTP {response.status}).")
			download_name = f"{download_entry_name}.zip" if download_kind == "payload" else download_entry_name
			encoded_name = urllib_parse.quote(download_entry_name, safe="")
			self.write_json(
				{
					"downloadUrl": f"/api/device/{device['id']}/download/{encoded_name}?kind={download_kind}",
					"suggestedName": download_name,
					"destinationPath": destination_path,
					"archiveAction": archive_action,
				}
			)
		except Exception as error:  # noqa: BLE001
			self.write_json({"error": resolve_error_message(error)}, status=HTTPStatus.BAD_GATEWAY)

	def copy_entry_to_dump(
		self,
		source_path: str,
		dump_path: str,
		entry_name: str,
		kind: str,
	) -> tuple[str, str, str]:
		stored_name = f"{entry_name}.zip" if kind == "payload" else entry_name
		candidate_name = stored_name
		content_type = "application/zip" if kind == "payload" else guess_content_type(stored_name)
		for _attempt in range(2):
			with self.relay_config.copyparty.open_download(source_path, kind) as download_response:
				status = getattr(download_response, "status", HTTPStatus.OK)
				if status != HTTPStatus.OK:
					raise RuntimeError(f"Download failed with HTTP {status}.")
				with tempfile.TemporaryFile() as temp_file:
					shutil.copyfileobj(download_response, temp_file, CHUNK_SIZE)
					temp_file.seek(0, os.SEEK_SET)
					response = self.relay_config.copyparty.upload_stream(
						dump_path,
						temp_file,
						candidate_name,
						content_type,
					)
			if 200 <= response.status < 300:
				return candidate_name, "file", join_cp_paths(dump_path, candidate_name)
			if response.status in (HTTPStatus.CONFLICT, HTTPStatus.PRECONDITION_FAILED):
				candidate_name = append_name_suffix(stored_name, secrets.token_hex(2))
				continue
			raise RuntimeError(f"Unable to copy item into {dump_path} (HTTP {response.status}).")
		raise RuntimeError(f"Unable to copy item into {dump_path}; filename conflict persisted.")

	def handle_download(self, path: str, query: dict[str, list[str]]) -> None:
		try:
			prefix = "/api/device/"
			remainder = path[len(prefix) :]
			device_id, after_device = remainder.split("/download/", 1)
			device = self.relay_config.require_device(urllib_parse.unquote(device_id))
			entry_name = leaf_name(urllib_parse.unquote(after_device))
			kind = (query.get("kind") or ["file"])[0]
			if kind not in {"file", "payload"}:
				raise ValueError("Invalid download kind.")
			source_path = join_cp_paths(device["dumpPath"], entry_name)
			with self.relay_config.copyparty.open_download(source_path, kind) as response:
				status = getattr(response, "status", HTTPStatus.OK)
				if status != HTTPStatus.OK:
					raise RuntimeError(f"Download failed with HTTP {status}.")
				file_name = f"{entry_name}.zip" if kind == "payload" else entry_name
				self.send_response(HTTPStatus.OK)
				self.send_header("Content-Type", response.headers.get_content_type())
				self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
				self.send_header("Cache-Control", "no-store")
				self.end_headers()
				shutil.copyfileobj(response, self.wfile, length=CHUNK_SIZE)
		except Exception as error:  # noqa: BLE001
			self.write_json({"error": resolve_error_message(error)}, status=HTTPStatus.BAD_GATEWAY)

	def read_json_body(self) -> dict[str, Any]:
		content_length = int(self.headers.get("Content-Length", "0") or "0")
		raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
		return json.loads(raw_body.decode("utf-8"))

	def write_json(
		self,
		payload: dict[str, Any],
		status: int = HTTPStatus.OK,
		content_type: str = "application/json; charset=utf-8",
	) -> None:
		body = json.dumps(payload, indent=2).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)


class TitanRelayHTTPServer(ThreadingHTTPServer):
	def __init__(self, server_address, handler_class, relay_config: TitanRelayConfig):
		super().__init__(server_address, handler_class)
		self.relay_config = relay_config


def initialize_mailboxes(config: TitanRelayConfig) -> None:
	config.copyparty.ensure_folder(config.inbox_root)
	config.copyparty.ensure_folder(config.dump_root)
	for device in config.devices:
		config.copyparty.ensure_folder(device["inboxPath"])
		config.copyparty.ensure_folder(device["dumpPath"])


def print_summary(config: TitanRelayConfig) -> None:
	print(f"Project: {config.project_name}")
	print(f"Server: http://{config.host}:{config.port}")
	print(f"Copyparty: {config.base_url}")
	print("Mailboxes:")
	for device in config.devices:
		print(f"  - {device['id']}: {device['inboxPath']} -> {device['dumpPath']}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Serve TitanRelay as a standalone Copyparty mailbox app.")
	parser.add_argument("--config", default=str(PROJECT_ROOT / "titanrelay.json"))
	parser.add_argument("--check-config", action="store_true")
	parser.add_argument("--init-mailboxes", action="store_true")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	config = load_config(Path(args.config))
	if args.check_config:
		print_summary(config)
		return 0
	if args.init_mailboxes:
		initialize_mailboxes(config)
		print("Mailbox folders are ready.")
		return 0
	server = TitanRelayHTTPServer((config.host, config.port), TitanRelayRequestHandler, config)
	print_summary(config)
	print("Press Ctrl+C to stop TitanRelay.")
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print("\nTitanRelay stopped.")
	finally:
		server.server_close()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
