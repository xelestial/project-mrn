from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from apps.server.src.infra.game_debug_log import write_game_debug_log

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])


@router.post("/frontend-log")
async def frontend_log(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    event = _text(payload.get("event"), "frontend_event")
    session_id = _optional_text(payload.get("session_id"))
    seq = payload.get("seq") if isinstance(payload.get("seq"), int) else None
    fields: dict[str, Any] = {
        "session_id": session_id,
        "seq": seq,
        "payload": payload.get("payload"),
    }
    write_game_debug_log("frontend", event, **fields)
    return JSONResponse(status_code=202, content={"ok": True, "data": {"accepted": True}, "error": None})


def _text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
