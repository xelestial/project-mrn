"""viewer/events.py — structured event definitions (SHARED_VISUAL_RUNTIME_CONTRACT Layer 1).

Every event emitted by the engine substrate carries the common envelope fields
defined in SHARED_VISUAL_RUNTIME_CONTRACT.md, plus event-specific payload fields.

Serialization: VisEvent.to_dict() produces a flat JSON-serializable dict with
all common + payload fields at the top level, matching the contract schema.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisEvent:
    """Common envelope for all visualization events.

    Common fields (SHARED_CONTRACT §Minimum Event Schema):
        event_type          — snake_case event name from Layer 1
        session_id          — UUID4 string per game run
        round_index         — 1-indexed round number
        turn_index          — 1-indexed global turn counter
        step_index          — monotonic step counter within session (deterministic sequence id)
        acting_player_id    — 1-indexed player id, or None for session/round-level events
        public_phase        — phase string from Phase constants below

    Event-specific fields are stored in payload and merged into the top-level
    dict on serialization.
    """
    event_type: str
    session_id: str
    round_index: int
    turn_index: int
    step_index: int
    acting_player_id: int | None
    public_phase: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Flat JSON-serializable dict with all fields at top level."""
        d: dict = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "round_index": self.round_index,
            "turn_index": self.turn_index,
            "step_index": self.step_index,
            "acting_player_id": self.acting_player_id,
            "public_phase": self.public_phase,
        }
        d.update(self.payload)
        return d


class Phase:
    """Allowed public_phase values (SHARED_CONTRACT §Public Phase Values)."""
    SESSION_START    = "session_start"
    WEATHER          = "weather"
    DRAFT            = "draft"
    CHARACTER_SELECT = "character_select"
    TURN_START       = "turn_start"
    TRICK_WINDOW     = "trick_window"
    MOVEMENT         = "movement"
    LANDING          = "landing"
    FORTUNE          = "fortune"
    MARK             = "mark"
    ECONOMY          = "economy"
    LAP_REWARD       = "lap_reward"
    TURN_END         = "turn_end"
    GAME_END         = "game_end"
