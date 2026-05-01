import asyncio
import os
import socket
import sys

from fastapi import FastAPI

from routers.codex import router as codex_router
from routers.dns import router as dns_router
from routers.gates import router as gates_router
from routers.ishtar import router as ishtar_router
from routers.priestess import router as priestess_router
from routers.proxy import router as proxy_router
from routers.relay import router as relay_router
from routers.startup_services import router as startup_services_router
from gates import GATE_CONFIGS, get_gate_manager
from nemo_dns import get_dns_resolver
from priestess import get_priestess_manager
from startup_services import get_startup_service_manager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI(title="Nemo")
app.include_router(codex_router)
app.include_router(ishtar_router)
app.include_router(relay_router)
app.include_router(gates_router)
app.include_router(startup_services_router)
app.include_router(priestess_router)
app.include_router(dns_router)
app.include_router(proxy_router)


@app.on_event("startup")
async def start_nemo_startup_services() -> None:
    get_startup_service_manager().start_auto_services()
    get_dns_resolver().start()
    get_priestess_manager().start()


@app.on_event("shutdown")
async def shutdown_managed_gates() -> None:
    get_gate_manager().shutdown_managed()
    get_dns_resolver().stop()
    get_startup_service_manager().shutdown_managed()
    get_priestess_manager().stop()


@app.get("/")
async def read_root():
    return {
        "app": "Nemo",
        "sections": {
            "codex": {
                "frontend": "/codex",
                "api": "/api/codex",
            },
            "ishtar": {
                "frontend": "/ishtar",
                "api": "/api/ishtar",
            },
            "relay": {
                "frontend": "/relay",
                "api": "/api/relay",
            },
            "gates": {
                "api": "/api/gates",
                "items": [gate.slug for gate in GATE_CONFIGS],
                "proxy": {
                    gate.slug: f"/{gate.slug}"
                    for gate in GATE_CONFIGS
                },
            },
            "startup_services": {
                "api": "/api/startup-services",
                "items": ["tailscale", "adguard"],
            },
            "priestess": {
                "api": "/api/priestess",
            },
            "dns": {
                "api": "/api/dns",
            },
        },
    }


def _nemo_port() -> int:
    raw = os.getenv("NEMO_PORT", "80")
    try:
        return int(raw)
    except ValueError:
        return 80


def _check_bind(host: str, port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except PermissionError as exc:
        raise PermissionError(
            f"Nemo cannot bind to {host}:{port}. On Windows, port 80 requires Administrator. "
            "Run Nemo as Administrator or set NEMO_PORT=8080."
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Nemo cannot bind to {host}:{port}: {exc}. If port 80 is occupied, stop the other service "
            "or set NEMO_PORT=8080."
        ) from exc
    finally:
        probe.close()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("NEMO_HOST", "0.0.0.0")
    port = _nemo_port()
    try:
        _check_bind(host, port)
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    uvicorn.run("server:app", host=host, port=port)
