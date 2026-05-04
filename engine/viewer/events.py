from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VisEvent:
    event_type: str
    session_id: str
    round_index: int
    turn_index: int
    step_index: int
    acting_player_id: int | None
    public_phase: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "round_index": self.round_index,
            "turn_index": self.turn_index,
            "step_index": self.step_index,
            "acting_player_id": self.acting_player_id,
            "public_phase": self.public_phase,
        }
        data.update(self.payload)
        return data


class Phase:
    SESSION_START = "session_start"
    WEATHER = "weather"
    DRAFT = "draft"
    CHARACTER_SELECT = "character_select"
    TURN_START = "turn_start"
    TRICK_WINDOW = "trick_window"
    MOVEMENT = "movement"
    LANDING = "landing"
    FORTUNE = "fortune"
    MARK = "mark"
    ECONOMY = "economy"
    LAP_REWARD = "lap_reward"
    TURN_END = "turn_end"
    GAME_END = "game_end"
