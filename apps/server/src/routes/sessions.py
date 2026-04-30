from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.engine_config_factory import EngineConfigFactory
from apps.server.src.services.session_service import SessionNotFoundError, SessionService, SessionStateError
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.runtime_service import RuntimeService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class SeatInput(BaseModel):
    seat: int = Field(..., ge=1)
    seat_type: str
    ai_profile: str | None = None
    participant_client: str | None = None
    participant_config: dict | None = None


class CreateSessionRequest(BaseModel):
    seats: list[SeatInput]
    config: dict | None = None


class JoinSessionRequest(BaseModel):
    seat: int = Field(..., ge=1)
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


def _initial_active_by_card(session) -> dict[int, str]:
    import random

    config = EngineConfigFactory().create(session.resolved_parameters)
    runtime = dict(session.resolved_parameters.get("runtime", {}))
    seed = int(runtime.get("seed", session.config.get("seed", 42)))
    if config.characters.randomize_starting_active_by_card:
        from characters import randomized_active_by_card

        return dict(randomized_active_by_card(random.Random(seed)))
    return dict(config.characters.starting_active_by_card)


def _error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "ok": False,
            "data": None,
            "error": build_error_payload(code=code, message=message, retryable=False),
        },
    )


def _session_auth_error(exc: SessionStateError) -> None:
    reason = str(exc)
    if reason == "spectator_not_allowed":
        _error("SPECTATOR_NOT_ALLOWED", "Spectator access is not allowed for this session.", status.HTTP_401_UNAUTHORIZED)
    _error("INVALID_SESSION_TOKEN", "Invalid session token.", status.HTTP_401_UNAUTHORIZED)


@router.post("")
async def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream),
) -> dict:
    log_event("session_create_requested", seat_count=len(payload.seats))
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
        {
            "event_type": "session_created",
            "status": session.status.value,
            "manifest_hash": session.parameter_manifest.get("manifest_hash"),
        },
    )
    log_event(
        "session_created",
        session_id=session.session_id,
        manifest_hash=session.parameter_manifest.get("manifest_hash"),
    )
    return _ok(service.to_create_result(session))


@router.get("")
def list_sessions(service: SessionService = Depends(_service)) -> dict:
    sessions = [
        service.to_public(session, include_private_identifier=False)
        for session in service.list_sessions()
    ]
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
    log_event("session_join_requested", session_id=session_id, seat=payload.seat)
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
    log_event(
        "session_joined",
        session_id=session_id,
        seat=payload.seat,
        player_id=result.get("player_id"),
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
    log_event("session_start_requested", session_id=session_id)
    try:
        session = service.start_session(session_id=session_id, host_token=payload.host_token)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    except SessionStateError as exc:
        _error("INVALID_STATE_TRANSITION", str(exc))
    await stream.publish(
        session_id,
        "event",
        {
            "event_type": "session_start",
            "status": session.status.value,
            "round_index": session.round_index,
            "turn_index": session.turn_index,
            "player_count": len(session.seats),
            "players": [
                {
                    "seat": seat.seat,
                    "player_id": seat.player_id,
                    "seat_type": seat.seat_type.value,
                    "ai_profile": seat.ai_profile,
                    "participant_client": seat.participant_client.value if seat.participant_client is not None else None,
                    "participant_config": dict(seat.participant_config),
                }
                for seat in session.seats
            ],
            "active_by_card": _initial_active_by_card(session),
            "manifest_hash": session.parameter_manifest.get("manifest_hash"),
        },
    )
    await stream.publish(
        session_id,
        "event",
        {
            "event_type": "session_started",
            "status": session.status.value,
            "manifest_hash": session.parameter_manifest.get("manifest_hash"),
        },
    )
    await stream.publish(
        session_id,
        "event",
        {
            "event_type": "parameter_manifest",
            "parameter_manifest": session.parameter_manifest,
            "active_by_card": _initial_active_by_card(session),
        },
    )
    log_event(
        "session_started",
        session_id=session_id,
        manifest_hash=session.parameter_manifest.get("manifest_hash"),
        player_count=len(session.seats),
    )
    runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
    await runtime.start_runtime(
        session_id=session_id,
        seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
        policy_mode=runtime_cfg.get("policy_mode"),
    )
    return _ok(service.to_public(session))


@router.get("/{session_id}/runtime-status")
def runtime_status(
    session_id: str,
    token: str | None = None,
    service: SessionService = Depends(_service),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        service.verify_session_token(session_id, token)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    except SessionStateError as exc:
        _session_auth_error(exc)
    return _ok({"session_id": session_id, "runtime": runtime.public_runtime_status(session_id)})


@router.get("/{session_id}/replay")
async def replay_export(
    session_id: str,
    token: str | None = None,
    service: SessionService = Depends(_service),
    stream: StreamService = Depends(_stream_service),
) -> dict:
    try:
        service.get_session(session_id)
        auth_ctx = service.verify_session_token(session_id, token)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    except SessionStateError as exc:
        _session_auth_error(exc)
    viewer = ViewerContext(
        role=str(auth_ctx.get("role") or "spectator"),
        session_id=session_id,
        seat=auth_ctx.get("seat"),
        player_id=auth_ctx.get("player_id"),
    )
    events = []
    for message in await stream.snapshot(session_id):
        projected = await stream.project_message_for_viewer(message.to_dict(), viewer)
        if projected is not None:
            events.append(projected)
    view_state = await stream.latest_view_state_for_viewer(session_id, viewer)
    replay_export_payload = {
        "schema_version": 1,
        "schema_name": "mrn.redacted_replay_export",
        "visibility": "player" if viewer.is_seat else "spectator",
        "browser_safe": True,
        "session_id": session_id,
        "viewer": {
            "role": viewer.role,
            "seat": viewer.seat,
            "player_id": viewer.player_id,
        },
        "event_count": len(events),
        "events": events,
        "view_state": view_state,
    }
    return _ok(replay_export_payload)
