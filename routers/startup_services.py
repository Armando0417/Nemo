from __future__ import annotations

from fastapi import APIRouter, HTTPException

from startup_services import STARTUP_SERVICE_CONFIGS, get_startup_service_manager


startup_service_manager = get_startup_service_manager()

router = APIRouter()
api_router = APIRouter(prefix="/api/startup-services", tags=["Startup Services"])


def _service_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


@api_router.get("")
def list_startup_services() -> dict[str, object]:
    return {"items": startup_service_manager.list_statuses()}


@api_router.get("/meta/catalog")
def startup_service_catalog() -> dict[str, object]:
    return {
        "items": [
            {
                "slug": service.slug,
                "name": service.name,
                "command": list(service.command),
                "cwd": str(service.cwd) if service.cwd else None,
                "process_names": list(service.process_names),
                "visible_console": service.visible_console,
                "auto_start": service.auto_start,
                "stop_managed_on_shutdown": service.stop_managed_on_shutdown,
            }
            for service in STARTUP_SERVICE_CONFIGS
        ]
    }


@api_router.get("/{service_slug}/check")
def check_startup_service(service_slug: str) -> dict[str, object]:
    try:
        return startup_service_manager.check_service(service_slug)
    except Exception as error:  # noqa: BLE001
        raise _service_error(error) from error


@api_router.api_route("/{service_slug}/start", methods=["GET", "POST"])
def start_startup_service(service_slug: str) -> dict[str, object]:
    try:
        return startup_service_manager.start_service(service_slug)
    except Exception as error:  # noqa: BLE001
        raise _service_error(error) from error


@api_router.api_route("/{service_slug}/stop", methods=["GET", "POST"])
def stop_startup_service(service_slug: str) -> dict[str, object]:
    try:
        return startup_service_manager.stop_service(service_slug)
    except Exception as error:  # noqa: BLE001
        raise _service_error(error) from error


router.include_router(api_router)
