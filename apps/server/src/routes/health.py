from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    return {
        "ok": True,
        "data": {"status": "ok"},
        "error": None,
    }

