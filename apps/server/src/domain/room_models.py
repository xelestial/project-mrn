from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from apps.server.src.domain.session_models import (
    ParticipantClientType,
    SeatType,
    SessionVisibility,
    utc_now_iso,
)


class RoomStatus(str, Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


@dataclass(slots=True)
class RoomSeat:
    seat: int
    seat_type: SeatType
    ai_profile: str | None = None
    participant_client: ParticipantClientType | None = None
    participant_config: dict = field(default_factory=dict)
    player_id: int | None = None
    nickname: str | None = None
    ready: bool = False
    connected: bool = False
    room_member_token: str | None = None
    session_token: str | None = None


@dataclass(slots=True)
class Room:
    room_no: int
    room_title: str
    status: RoomStatus
    seats: list[RoomSeat]
    host_seat: int
    visibility: SessionVisibility = SessionVisibility.PRIVATE
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    closed_at: str | None = None
    session_id: str | None = None
