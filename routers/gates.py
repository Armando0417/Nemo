from __future__ import annotations

import json
from pathlib import Path
import webbrowser

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from gates import GATE_CONFIGS, get_gate_manager

gate_manager = get_gate_manager()

router = APIRouter()
api_router = APIRouter(prefix="/api/gates", tags=["Gates"])
GATE_LOADER_PATH = Path(__file__).resolve().parent.parent / "gate_loader.html"


def _gate_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


@api_router.get("")
def list_gates() -> dict[str, object]:
    return {
        "items": gate_manager.list_statuses(),
    }


@api_router.get("/{gate_slug}/check")
def check_gate(gate_slug: str) -> dict[str, object]:
    try:
        return gate_manager.check_gate(gate_slug)
    except Exception as error:  # noqa: BLE001
        raise _gate_error(error) from error


@api_router.api_route("/{gate_slug}/start", methods=["GET", "POST"])
def start_gate(
    gate_slug: str,
    wait: bool = True,
    timeout: float = Query(default=20.0, ge=0.0, le=120.0),
) -> dict[str, object]:
    try:
        return gate_manager.start_gate(gate_slug, wait_for_ready=wait, timeout=timeout)
    except Exception as error:  # noqa: BLE001
        raise _gate_error(error) from error


@api_router.api_route("/{gate_slug}/stop", methods=["GET", "POST"])
def stop_gate(
    gate_slug: str,
    timeout: float = Query(default=10.0, ge=0.0, le=60.0),
) -> dict[str, object]:
    try:
        return gate_manager.stop_gate(gate_slug, wait_timeout=timeout)
    except Exception as error:  # noqa: BLE001
        raise _gate_error(error) from error


@api_router.api_route("/{gate_slug}/open", methods=["GET", "POST"])
def open_gate(
    request: Request,
    gate_slug: str,
    ensure_started: bool = True,
    launch_browser: bool = True,
    wait: bool = False,
    timeout: float = Query(default=20.0, ge=0.0, le=120.0),
) -> dict[str, object]:
    try:
        if ensure_started:
            status = gate_manager.start_gate(gate_slug, wait_for_ready=wait, timeout=timeout)
        else:
            status = gate_manager.check_gate(gate_slug)

        loader_url = str(request.url_for("gate_private_loader", gate_slug=gate_slug))
        browser_opened = False
        if launch_browser:
            browser_opened = webbrowser.open(loader_url)

        status["action"] = "opened" if browser_opened else "loader_url_ready"
        status["browser_opened"] = browser_opened
        status["loader_url"] = loader_url
        return status
    except Exception as error:  # noqa: BLE001
        raise _gate_error(error) from error


@api_router.get("/meta/catalog")
def gate_catalog() -> dict[str, object]:
    return {
        "items": [
            {
                "slug": gate.slug,
                "name": gate.name,
                "subtitle": gate.subtitle,
                "port": gate.port,
                "url": gate.url,
            }
            for gate in GATE_CONFIGS
        ]
    }


@router.get("/private/gates/{gate_slug}/loader", include_in_schema=False, name="gate_private_loader")
def gate_private_loader(gate_slug: str, request: Request) -> HTMLResponse:
    if not GATE_LOADER_PATH.exists():
        raise HTTPException(status_code=404, detail="gate_loader.html not found")

    try:
        status = gate_manager.check_gate(gate_slug)
    except Exception as error:  # noqa: BLE001
        raise _gate_error(error) from error

    gate_config = next((gate for gate in GATE_CONFIGS if gate.slug == gate_slug), None)
    if gate_config is None:
        raise HTTPException(status_code=404, detail=f"Unknown gate '{gate_slug}'.")

    injected_config = {
        "name": gate_config.name,
        "port": gate_config.port,
        "subtitle": gate_config.subtitle,
        "classification": "RESTRICTED ACCESS",
        "scheme": "http",
    }

    html = GATE_LOADER_PATH.read_text(encoding="utf-8")
    injection = (
        "<script>"
        f"window.__NEMO_GATE_CONFIG__ = {json.dumps(injected_config)};"
        f"window.__NEMO_GATE_STATUS__ = {json.dumps(status)};"
        "</script>"
    )
    if "</head>" in html:
        html = html.replace("</head>", f"{injection}\n  </head>", 1)
    else:
        html = injection + html

    return HTMLResponse(html)


router.include_router(api_router)
