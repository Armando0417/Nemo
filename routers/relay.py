from __future__ import annotations

import json
from pathlib import Path
import mimetypes

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from relay.config import get_settings
from relay.runtime import CopypartyRuntimeManager
from relay.service import RelayService, load_relay_config, resolve_error_message
from priestess import get_priestess_manager

settings = get_settings()
relay_config = load_relay_config(settings)
relay_service = RelayService(relay_config)
copyparty_runtime = CopypartyRuntimeManager(settings)
priestess_manager = get_priestess_manager()

router = APIRouter()
api_router = APIRouter(prefix="/api/relay", tags=["Relay"])


class ArchiveRequest(BaseModel):
    name: str
    kind: str


def _copyparty_status(start_if_needed: bool | None = False) -> dict:
    if start_if_needed is False:
        return copyparty_runtime.status(relay_config.copyparty)
    return copyparty_runtime.ensure_running(relay_config.copyparty, start_if_needed=start_if_needed)


def _require_copyparty() -> dict:
    status = _copyparty_status(start_if_needed=None)
    if status["reachable"]:
        return status
    detail = status["detail"] or f"Copyparty is not reachable at {relay_config.base_url}."
    raise HTTPException(status_code=502, detail=detail)


def _relay_exception(error: Exception) -> HTTPException:
    detail = resolve_error_message(error)
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=detail)
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=detail)
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=503, detail=detail)
    return HTTPException(status_code=502, detail=detail)


@api_router.get("")
async def root() -> dict[str, object]:
    return {
        "message": "Welcome to Relay inside Nemo.",
        "copyparty": _copyparty_status(start_if_needed=False),
    }


@api_router.get("/health")
async def relay_health() -> dict[str, object]:
    return {
        "ok": True,
        "projectName": relay_config.project_name,
        "copyparty": _copyparty_status(start_if_needed=False),
    }


@api_router.get("/copyparty/status")
async def relay_copyparty_status() -> dict[str, object]:
    return _copyparty_status(start_if_needed=False)


@api_router.post("/copyparty/ensure")
async def relay_copyparty_ensure() -> dict[str, object]:
    return _copyparty_status(start_if_needed=True)


@api_router.post("/system/init-mailboxes")
async def relay_init_mailboxes() -> dict[str, object]:
    _require_copyparty()
    try:
        return relay_service.initialize_mailboxes()
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error


@api_router.get("/devices")
async def relay_devices() -> dict[str, object]:
    return relay_service.get_devices_payload(_copyparty_status(start_if_needed=False))


@api_router.get("/bootstrap/{device_id}")
async def relay_bootstrap(device_id: str) -> dict[str, object]:
    try:
        return relay_config.bootstrap_for(
            device_id,
            _copyparty_status(start_if_needed=False),
        )
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error


@api_router.get("/device/{device_id}/inbox")
async def relay_inbox(device_id: str) -> dict[str, object]:
    _require_copyparty()
    try:
        return relay_service.list_inbox(device_id)
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error


@api_router.post("/device/{device_id}/send")
async def relay_send(device_id: str, request: Request) -> dict[str, object]:
    _require_copyparty()
    try:
        form = await request.form()
        target_id = str(form.get("targetId") or "").strip()
        relative_paths_raw = str(form.get("relativePaths") or "[]")
        relative_paths = json.loads(relative_paths_raw)
        files = [entry for entry in form.getlist("file") if hasattr(entry, "file")]
        result = relay_service.send_payload(device_id, target_id, relative_paths, files)
        result["alert"] = priestess_manager.notify_relay_payload(result)
        return result
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error


@api_router.post("/device/{device_id}/archive")
async def relay_archive(device_id: str, payload: ArchiveRequest) -> dict[str, object]:
    _require_copyparty()
    try:
        result = relay_service.archive_entry(device_id, payload.name, payload.kind)
        result["alert"] = priestess_manager.notify_relay_archive(result)
        return result
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error


@api_router.get("/device/{device_id}/download/{entry_name:path}")
async def relay_download(
    device_id: str,
    entry_name: str,
    kind: str = "file",
    storage: str = "dump",
) -> StreamingResponse:
    _require_copyparty()
    try:
        handle = relay_service.prepare_download(device_id, entry_name, kind, storage=storage)
    except Exception as error:  # noqa: BLE001
        raise _relay_exception(error) from error

    headers = {
        "Content-Disposition": f'attachment; filename="{handle.file_name}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(
        iter(lambda: handle.stream.read(1024 * 256), b""),
        media_type=handle.content_type,
        headers=headers,
        background=BackgroundTask(handle.stream.close),
    )


@router.get("/relay/manifests/{slug}.webmanifest", include_in_schema=False)
async def relay_manifest(slug: str) -> JSONResponse:
    device = relay_config.get_device_by_slug(slug)
    if not device:
        raise HTTPException(status_code=404, detail="Manifest not found")
    return JSONResponse(
        relay_config.build_manifest(device["id"]),
        media_type="application/manifest+json",
    )


def _frontend_response(path: str) -> Response:
    web_root = settings.web_root.resolve()
    normalized_path = path.strip("/")
    if normalized_path in {"", "."}:
        return FileResponse(web_root / "index.html")

    candidate = (web_root / normalized_path).resolve()
    if web_root not in {candidate, *candidate.parents}:
        raise HTTPException(status_code=404, detail="Not found")

    if candidate.exists() and candidate.is_file():
        media_type, _ = mimetypes.guess_type(candidate.name)
        return FileResponse(candidate, media_type=media_type)

    html_candidate = candidate.with_suffix(".html") if not Path(normalized_path).suffix else None
    if html_candidate and html_candidate.exists() and html_candidate.is_file():
        return FileResponse(html_candidate, media_type="text/html")

    if Path(normalized_path).suffix:
        raise HTTPException(status_code=404, detail="Static asset not found")

    return FileResponse(web_root / "index.html")


@router.get("/relay", include_in_schema=False)
async def relay_frontend_root() -> Response:
    return _frontend_response("")


@router.get("/relay/{path:path}", include_in_schema=False)
async def relay_frontend(path: str) -> Response:
    return _frontend_response(path)


router.include_router(api_router)
