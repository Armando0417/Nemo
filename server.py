import asyncio
import sys

from fastapi import FastAPI

from routers.codex import router as codex_router
from routers.gates import router as gates_router
from routers.ishtar import router as ishtar_router
from routers.priestess import router as priestess_router
from routers.relay import router as relay_router
from routers.startup_services import router as startup_services_router
from gates import GATE_CONFIGS, get_gate_manager
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


@app.on_event("startup")
async def start_nemo_startup_services() -> None:
    get_startup_service_manager().start_auto_services()
    get_priestess_manager().start()


@app.on_event("shutdown")
async def shutdown_managed_gates() -> None:
    get_gate_manager().shutdown_managed()
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
            },
            "startup_services": {
                "api": "/api/startup-services",
                "items": ["tailscale", "adguard"],
            },
            "priestess": {
                "api": "/api/priestess",
            },
        },
    }
