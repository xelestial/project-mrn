from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.server.src.services.session_service import SessionNotFoundError, SessionService, SessionStateError
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.runtime_service import RuntimeService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class SeatInput(BaseModel):
    seat: int = Field(..., ge=1, le=4)
    seat_type: str
    ai_profile: str | None = None


class CreateSessionRequest(BaseModel):
    seats: list[SeatInput]
    config: dict | None = None


class JoinSessionRequest(BaseModel):
    seat: int = Field(..., ge=1, le=4)
    join_token: str
    display_name: str | None = None


class StartSessionRequest(BaseModel):
    host_token: str


def _service() -> SessionService:
    from apps.server.src.state import session_service

    return session_service


def _stream() -> StreamService:
    from apps.server.src.state import stream_service

    return stream_service


def _runtime() -> RuntimeService:
    from apps.server.src.state import runtime_service

    return runtime_service

def _stream_service() -> StreamService:
    from apps.server.src.state import stream_service

    return stream_service


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


def _error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message, "retryable": False},
        },
    )


@router.post("")
async def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream),
) -> dict:
    try:
        session = service.create_session(
            seats=[seat.model_dump() for seat in payload.seats],
            config=payload.config,
        )
    except SessionStateError as exc:
        _error("INVALID_REQUEST", str(exc))
    await stream.publish(
        session.session_id,
        "event",
        {"event_type": "session_created", "status": session.status.value},
    )
    return _ok(service.to_create_result(session))


@router.get("")
def list_sessions(service: SessionService = Depends(_service)) -> dict:
    sessions = [service.to_public(session) for session in service.list_sessions()]
    return _ok({"sessions": sessions})


@router.get("/{session_id}")
def get_session(session_id: str, service: SessionService = Depends(_service)) -> dict:
    try:
        session = service.get_session(session_id)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    return _ok(service.to_public(session))


@router.post("/{session_id}/join")
async def join_session(
    session_id: str,
    payload: JoinSessionRequest,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream),
) -> dict:
    try:
        result = service.join_session(
            session_id=session_id,
            seat=payload.seat,
            join_token=payload.join_token,
            display_name=payload.display_name,
        )
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    except SessionStateError as exc:
        _error("JOIN_REJECTED", str(exc))
    await stream.publish(
        session_id,
        "event",
        {
            "event_type": "seat_joined",
            "seat": payload.seat,
            "player_id": result.get("player_id"),
        },
    )
    return _ok(result)


@router.post("/{session_id}/start")
async def start_session(
    session_id: str,
    payload: StartSessionRequest,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        session = service.start_session(session_id=session_id, host_token=payload.host_token)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    except SessionStateError as exc:
        _error("INVALID_STATE_TRANSITION", str(exc))
    await stream.publish(
        session_id,
        "event",
        {"event_type": "session_started", "status": session.status.value},
    )
    if service.is_all_ai(session_id):
        await runtime.start_runtime(session_id=session_id, seed=int(session.config.get("seed", 42)))
    return _ok(service.to_public(session))


@router.get("/{session_id}/runtime-status")
def runtime_status(
    session_id: str,
    service: SessionService = Depends(_service),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        service.get_session(session_id)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    return _ok({"session_id": session_id, "runtime": runtime.runtime_status(session_id)})


@router.get("/{session_id}/replay")
async def replay_export(
    session_id: str,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream_service),
) -> dict:
    try:
        service.get_session(session_id)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    events = [message.to_dict() for message in await stream.snapshot(session_id)]
    return _ok({"session_id": session_id, "event_count": len(events), "events": events})
