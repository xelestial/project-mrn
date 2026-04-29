from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.server.src.core.error_payload import build_error_payload

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> JSONResponse:
    from apps.server.src.state import (
        redis_connection,
        room_storage_backend,
        session_storage_backend,
        stream_storage_backend,
    )

    data = {
        "status": "ok",
        "storage": {
            "sessions": session_storage_backend,
            "rooms": room_storage_backend,
            "streams": stream_storage_backend,
        },
        "redis": None,
    }
    error = None
    ok = True
    if redis_connection is not None:
        try:
            redis_health = redis_connection.health_check()
        except Exception as exc:
            ok = False
            data["status"] = "degraded"
            redis_health = {
                "configured": True,
                "ok": False,
                "error": str(exc),
                "key_prefix": redis_connection.settings.key_prefix,
            }
        data["redis"] = redis_health
        if redis_health.get("ok") is not True:
            ok = False
            data["status"] = "degraded"
            error = build_error_payload(
                code="REDIS_UNAVAILABLE",
                message="Redis health check failed.",
                retryable=True,
            )
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "ok": ok,
            "data": data,
            "error": error,
        },
    )
