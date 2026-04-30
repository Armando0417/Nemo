from __future__ import annotations

from fastapi import APIRouter

from priestess import get_priestess_manager


priestess_manager = get_priestess_manager()

router = APIRouter()
api_router = APIRouter(prefix="/api/priestess", tags=["Priestess"])


@api_router.get("")
def priestess_root() -> dict[str, object]:
    return {
        "message": "Priestess alert subsystem is available.",
        "status": priestess_manager.status(),
    }


@api_router.get("/status")
def priestess_status() -> dict[str, object]:
    return priestess_manager.status()


@api_router.post("/test")
def priestess_test() -> dict[str, object]:
    return priestess_manager.send_test_alert()


router.include_router(api_router)
