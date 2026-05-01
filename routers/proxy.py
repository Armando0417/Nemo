from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.background import BackgroundTask
import httpx
import websockets

from gates import get_gate_manager
from gates.config import GateConfig, get_gate_map

router = APIRouter(tags=["Gate Proxy"])

GATE_LOADER_PATH = Path(__file__).resolve().parent.parent / "gate_loader.html"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

gate_map = get_gate_map()
gate_manager = get_gate_manager()


def _require_proxy_gate(slug: str) -> GateConfig:
    gate = gate_map.get(slug)
    if gate is None:
        raise HTTPException(status_code=404, detail=f"Unknown gate '{slug}'.")
    return gate


def _target_url(gate: GateConfig, path: str, query: str) -> str:
    target = f"{gate.url}/{path.lstrip('/')}" if path else f"{gate.url}/"
    return f"{target}?{query}" if query else target


def _target_ws_url(gate: GateConfig, path: str, query: str) -> str:
    target = f"ws://127.0.0.1:{gate.port}/{path.lstrip('/')}" if path else f"ws://127.0.0.1:{gate.port}/"
    return f"{target}?{query}" if query else target


def _forward_request_headers(request: Request, gate: GateConfig) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-length"
    }
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    headers["x-forwarded-prefix"] = f"/{gate.slug}"
    return headers


def _forward_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def _loader_or_error(gate: GateConfig, request: Request) -> HTMLResponse:
    if not GATE_LOADER_PATH.exists():
        return HTMLResponse(
            f"<h1>{gate.name} is offline</h1><p>Start it from /api/gates/{gate.slug}/start.</p>",
            status_code=503,
        )

    status = gate_manager.check_gate(gate.slug, use_cache=False)
    html = GATE_LOADER_PATH.read_text(encoding="utf-8")
    start_url = str(request.url_for("start_gate", gate_slug=gate.slug))
    injected = (
        "<script>"
        "window.__NEMO_GATE_CONFIG__ = "
        + _json_script(
            {
                "name": gate.name,
                "subtitle": gate.subtitle,
                "port": gate.port,
                "host": request.url.hostname or "localhost",
                "scheme": request.url.scheme,
                "targetUrl": f"/{gate.slug}",
                "startUrl": start_url,
            }
        )
        + ";"
        "window.__NEMO_GATE_STATUS__ = "
        + _json_script(status)
        + ";"
        "</script>"
    )
    if "</head>" in html:
        html = html.replace("</head>", f"{injected}\n  </head>", 1)
    else:
        html = injected + html
    return HTMLResponse(html, status_code=503)


def _json_script(payload: object) -> str:
    import json

    return json.dumps(payload).replace("</", "<\\/")


async def _proxy_http(gate_slug: str, path: str, request: Request) -> StreamingResponse | HTMLResponse:
    gate = _require_proxy_gate(gate_slug)
    status = gate_manager.check_gate(gate.slug)
    if not status.get("ready") and not status.get("running"):
        return _loader_or_error(gate, request)

    target_url = _target_url(gate, path, request.url.query)
    client = httpx.AsyncClient(follow_redirects=False, timeout=None)
    try:
        outbound = client.build_request(
            request.method,
            target_url,
            headers=_forward_request_headers(request, gate),
            content=request.stream(),
        )
        response = await client.send(outbound, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        return _loader_or_error(gate, request)

    return StreamingResponse(
        response.aiter_raw(),
        status_code=response.status_code,
        headers=_forward_response_headers(response.headers),
        background=BackgroundTask(_close_proxy_response, response, client),
    )


async def _close_proxy_response(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


@router.api_route("/akashic", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
@router.api_route("/akashic/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def proxy_akashic(request: Request, path: str = ""):
    return await _proxy_http("akashic", path, request)


@router.api_route("/htv", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
@router.api_route("/htv/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def proxy_htv(request: Request, path: str = ""):
    return await _proxy_http("htv", path, request)


@router.api_route("/voyager", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
@router.api_route("/voyager/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def proxy_voyager(request: Request, path: str = ""):
    return await _proxy_http("voyager", path, request)


def _websocket_headers(websocket: WebSocket, gate: GateConfig) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in websocket.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    ] + [
        ("x-forwarded-host", websocket.headers.get("host", "")),
        ("x-forwarded-proto", "ws"),
        ("x-forwarded-prefix", f"/{gate.slug}"),
    ]


async def _proxy_websocket(gate_slug: str, path: str, websocket: WebSocket) -> None:
    gate = _require_proxy_gate(gate_slug)
    status = gate_manager.check_gate(gate.slug)
    if not status.get("ready") and not status.get("running"):
        await websocket.close(code=1013, reason=f"{gate.name} is offline.")
        return

    query = urlencode(websocket.query_params.multi_items())
    target_url = _target_ws_url(gate, path, query)
    await websocket.accept()
    try:
        async with websockets.connect(
            target_url,
            additional_headers=_websocket_headers(websocket, gate),
            max_size=None,
        ) as upstream:
            client_to_upstream = asyncio.create_task(_client_to_upstream(websocket, upstream))
            upstream_to_client = asyncio.create_task(_upstream_to_client(websocket, upstream))
            done, pending = await asyncio.wait(
                {client_to_upstream, upstream_to_client},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass


async def _client_to_upstream(websocket: WebSocket, upstream) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            await upstream.close()
            return
        if "text" in message:
            await upstream.send(message["text"])
        elif "bytes" in message:
            await upstream.send(message["bytes"])


async def _upstream_to_client(websocket: WebSocket, upstream) -> None:
    async for message in upstream:
        if isinstance(message, bytes):
            await websocket.send_bytes(message)
        else:
            await websocket.send_text(message)


@router.websocket("/akashic")
@router.websocket("/akashic/{path:path}")
async def websocket_akashic(websocket: WebSocket, path: str = "") -> None:
    await _proxy_websocket("akashic", path, websocket)


@router.websocket("/htv")
@router.websocket("/htv/{path:path}")
async def websocket_htv(websocket: WebSocket, path: str = "") -> None:
    await _proxy_websocket("htv", path, websocket)


@router.websocket("/voyager")
@router.websocket("/voyager/{path:path}")
async def websocket_voyager(websocket: WebSocket, path: str = "") -> None:
    await _proxy_websocket("voyager", path, websocket)
