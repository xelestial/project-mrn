from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.room_service import (
    RoomNotFoundError,
    RoomService,
    RoomStateError,
)
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.routes.sessions import _initial_active_by_card, _initial_public_snapshot

router = APIRouter(prefix="/api/v1/rooms", tags=["rooms"])


class SeatInput(BaseModel):
    seat: int = Field(..., ge=1)
    seat_type: str
    ai_profile: str | None = None
    participant_client: str | None = None
    participant_config: dict | None = None


class CreateRoomRequest(BaseModel):
    room_title: str = Field(..., min_length=1)
    host_seat: int = Field(..., ge=1)
    nickname: str = Field(..., min_length=1)
    seats: list[SeatInput]
    config: dict | None = None


class JoinRoomRequest(BaseModel):
    seat: int = Field(..., ge=1)
    nickname: str = Field(..., min_length=1)


class ReadyRoomRequest(BaseModel):
    room_member_token: str
    ready: bool = True


class StartRoomRequest(BaseModel):
    room_member_token: str


class LeaveRoomRequest(BaseModel):
    room_member_token: str


def _rooms() -> RoomService:
    from apps.server.src.state import room_service

    return room_service


def _sessions() -> SessionService:
    from apps.server.src.state import session_service

    return session_service


def _stream() -> StreamService:
    from apps.server.src.state import stream_service

    return stream_service


def _runtime() -> RuntimeService:
    from apps.server.src.state import runtime_service

    return runtime_service


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


def _error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "ok": False,
            "data": None,
            "error": build_error_payload(code=code, message=message, retryable=False),
        },
    )


@router.post("")
def create_room(payload: CreateRoomRequest, rooms: RoomService = Depends(_rooms)) -> dict:
    log_event("room_create_requested", room_title=payload.room_title, seat_count=len(payload.seats))
    try:
        result = rooms.create_room(
            room_title=payload.room_title,
            seats=[seat.model_dump() for seat in payload.seats],
            host_seat=payload.host_seat,
            nickname=payload.nickname,
            config=payload.config,
        )
    except RoomStateError as exc:
        _error("ROOM_CREATE_REJECTED", str(exc))
    return _ok(result)


@router.get("")
def list_rooms(rooms: RoomService = Depends(_rooms)) -> dict:
    return _ok({"rooms": [rooms.to_public(room) for room in rooms.list_rooms()]})


@router.get("/{room_no}")
def get_room(room_no: int, rooms: RoomService = Depends(_rooms)) -> dict:
    try:
        room = rooms.get_room(room_no)
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    return _ok(rooms.to_public(room))


@router.post("/{room_no}/join")
def join_room(room_no: int, payload: JoinRoomRequest, rooms: RoomService = Depends(_rooms)) -> dict:
    try:
        result = rooms.join_room(room_no=room_no, seat=payload.seat, nickname=payload.nickname)
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    except RoomStateError as exc:
        _error("ROOM_JOIN_REJECTED", str(exc))
    return _ok(result)


@router.post("/{room_no}/ready")
def set_ready(room_no: int, payload: ReadyRoomRequest, rooms: RoomService = Depends(_rooms)) -> dict:
    try:
        room = rooms.set_ready(
            room_no=room_no,
            room_member_token=payload.room_member_token,
            ready=payload.ready,
        )
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    except RoomStateError as exc:
        _error("ROOM_READY_REJECTED", str(exc))
    return _ok(room)


@router.post("/{room_no}/leave")
def leave_room(room_no: int, payload: LeaveRoomRequest, rooms: RoomService = Depends(_rooms)) -> dict:
    try:
        room = rooms.leave_room(room_no=room_no, room_member_token=payload.room_member_token)
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    except RoomStateError as exc:
        _error("ROOM_LEAVE_REJECTED", str(exc))
    return _ok(room)


@router.get("/{room_no}/resume")
def resume_room(
    room_no: int,
    room_member_token: str = Query(...),
    rooms: RoomService = Depends(_rooms),
) -> dict:
    try:
        payload = rooms.resume_room(room_no=room_no, room_member_token=room_member_token)
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    except RoomStateError as exc:
        _error("ROOM_RESUME_REJECTED", str(exc))
    return _ok(payload)


@router.post("/{room_no}/start")
async def start_room(
    room_no: int,
    payload: StartRoomRequest,
    rooms: RoomService = Depends(_rooms),
    sessions: SessionService = Depends(_sessions),
    stream: StreamService = Depends(_stream),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        result = rooms.start_room(room_no=room_no, room_member_token=payload.room_member_token)
    except RoomNotFoundError:
        _error("ROOM_NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    except RoomStateError as exc:
        _error("ROOM_START_REJECTED", str(exc))

    session_id = str(result["session_id"])
    session = sessions.get_session(session_id)
    session = sessions.start_session(session_id=session_id, host_token=session.host_token)
    active_by_card = _initial_active_by_card(session)
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
                    "display_name": seat.display_name,
                    "ai_profile": seat.ai_profile,
                    "participant_client": seat.participant_client.value if seat.participant_client is not None else None,
                    "participant_config": dict(seat.participant_config),
                }
                for seat in session.seats
            ],
            "active_by_card": active_by_card,
            "snapshot": _initial_public_snapshot(session, active_by_card),
        },
    )
    await stream.publish(
        session_id,
        "event",
        {
            "event_type": "session_started",
            "status": session.status.value,
            "room_no": room_no,
            "room_title": result["room"]["room_title"],
            "players": [
                {
                    "seat": seat.seat,
                    "player_id": seat.player_id,
                    "display_name": seat.display_name,
                }
                for seat in session.seats
            ],
        },
    )
    runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
    await runtime.start_runtime(
        session_id=session_id,
        seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
        policy_mode=runtime_cfg.get("policy_mode"),
    )
    return _ok(result)
