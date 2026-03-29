from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.session_service import SessionNotFoundError, SessionService
from apps.server.src.services.stream_service import StreamService

router = APIRouter(prefix="/api/v1/sessions", tags=["prompts"])


class DebugPromptRequest(BaseModel):
    request_id: str
    request_type: str
    player_id: int
    timeout_ms: int = 30000
    choices: list[dict] = []
    public_context: dict | None = None


def _sessions() -> SessionService:
    from apps.server.src.state import session_service

    return session_service


def _prompts() -> PromptService:
    from apps.server.src.state import prompt_service

    return prompt_service


def _stream() -> StreamService:
    from apps.server.src.state import stream_service

    return stream_service


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


@router.post("/{session_id}/prompts/debug")
async def create_debug_prompt(
    session_id: str,
    payload: DebugPromptRequest,
    sessions: SessionService = Depends(_sessions),
    prompts: PromptService = Depends(_prompts),
    stream: StreamService = Depends(_stream),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "SESSION_NOT_FOUND",
                "message": "Session not found.",
                "retryable": False,
            },
        }

    prompt_payload = payload.model_dump()
    try:
        pending = prompts.create_prompt(session_id=session_id, prompt=prompt_payload)
    except ValueError as exc:
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": "PROMPT_REJECTED",
                "message": str(exc),
                "retryable": False,
            },
        }
    msg = await stream.publish(session_id, "prompt", prompt_payload)
    return _ok(
        {
            "request_id": pending.request_id,
            "seq": msg.seq,
            "status": "prompt_sent",
            "http_status": status.HTTP_200_OK,
        }
    )
