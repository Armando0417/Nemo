from __future__ import annotations

from fastapi import APIRouter

from nemo_dns import get_dns_resolver

router = APIRouter(prefix="/api/dns", tags=["DNS"])


@router.get("")
def dns_status() -> dict[str, object]:
    return get_dns_resolver().status()
