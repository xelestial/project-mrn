from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from apps.server.src.core.admin_auth import require_admin
from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.infra.structured_log import log_event
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


def _debug_module_prompt(session_id: str, payload: dict) -> dict:
    request_id = str(payload.get("request_id") or "debug")
    frame_id = f"seq:debug:{session_id}"
    module_id = f"mod:debug:{request_id}"
    module_cursor = "debug:await_prompt"
    return {
        **payload,
        "runner_kind": "module",
        "resume_token": f"debug:{session_id}:{request_id}",
        "frame_id": frame_id,
        "module_id": module_id,
        "module_type": "TrickChoiceModule",
        "module_cursor": module_cursor,
        "runtime_module": {
            "runner_kind": "module",
            "frame_type": "sequence",
            "frame_id": frame_id,
            "module_id": module_id,
            "module_type": "TrickChoiceModule",
            "module_cursor": module_cursor,
        },
    }


@router.post("/{session_id}/prompts/debug", dependencies=[Depends(require_admin)])
async def create_debug_prompt(
    session_id: str,
    payload: DebugPromptRequest,
    sessions: SessionService = Depends(_sessions),
    prompts: PromptService = Depends(_prompts),
    stream: StreamService = Depends(_stream),
) -> dict:
    log_event(
        "prompt_create_requested",
        session_id=session_id,
        request_id=payload.request_id,
        player_id=payload.player_id,
        request_type=payload.request_type,
    )
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        return {
            "ok": False,
            "data": None,
            "error": build_error_payload(code="SESSION_NOT_FOUND", message="Session not found.", retryable=False),
        }

    prompt_payload = _debug_module_prompt(session_id, payload.model_dump())
    try:
        pending = prompts.create_prompt(session_id=session_id, prompt=prompt_payload)
    except ValueError as exc:
        log_event(
            "prompt_create_rejected",
            session_id=session_id,
            request_id=payload.request_id,
            reason=str(exc),
        )
        return {
            "ok": False,
            "data": None,
            "error": build_error_payload(code="PROMPT_REJECTED", message=str(exc), retryable=False),
        }
    msg = await stream.publish(session_id, "prompt", prompt_payload)
    log_event(
        "prompt_sent",
        session_id=session_id,
        request_id=pending.request_id,
        player_id=pending.player_id,
        seq=msg.seq,
    )
    return _ok(
        {
            "request_id": pending.request_id,
            "seq": msg.seq,
            "status": "prompt_sent",
            "http_status": status.HTTP_200_OK,
        }
    )
