from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(str, Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    ABORTED = "aborted"


class SeatType(str, Enum):
    HUMAN = "human"
    AI = "ai"


class ParticipantClientType(str, Enum):
    HUMAN_HTTP = "human_http"
    LOCAL_AI = "local_ai"
    EXTERNAL_AI = "external_ai"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class SeatConfig:
    seat: int
    seat_type: SeatType
    ai_profile: str | None = None
    participant_client: ParticipantClientType | None = None
    participant_config: dict = field(default_factory=dict)
    player_id: int | None = None
    display_name: str | None = None
    connected: bool = False


@dataclass(slots=True)
class Session:
    session_id: str
    status: SessionStatus
    seats: list[SeatConfig]
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    abort_reason: str | None = None
    round_index: int = 0
    turn_index: int = 0
    host_token: str = ""
    join_tokens: dict[int, str] = field(default_factory=dict)
    session_tokens: dict[int, str] = field(default_factory=dict)
    resolved_parameters: dict = field(default_factory=dict)
    parameter_manifest: dict = field(default_factory=dict)
