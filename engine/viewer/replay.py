"""Phase 2 replay projection helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


_SKIP_IN_KEY_EVENTS = frozenset({
    "session_start",
    "round_start",
    "turn_start",
    "turn_end_snapshot",
    "trick_window_open",
    "trick_window_closed",
})

_TURN_EVENT_ORDER = {
    "turn_start": 0,
    "trick_window_open": 5,
    "trick_used": 10,
    "trick_window_closed": 15,
    "dice_roll": 20,
    "player_move": 30,
    "lap_reward_chosen": 35,
    "landing_resolved": 40,
    "tile_purchased": 50,
    "rent_paid": 50,
    "fortune_drawn": 55,
    "fortune_resolved": 60,
    "mark_resolved": 60,
    "marker_transferred": 70,
    "marker_flip": 72,
    "f_value_change": 75,
    "bankruptcy": 80,
    "turn_end_snapshot": 90,
}


def _turn_event_sort_key(event: dict) -> tuple[int, int]:
    return (
        _TURN_EVENT_ORDER.get(str(event.get("event_type", "")), 50),
        int(event.get("step_index", 0) or 0),
    )


def _ordered_turn_events(events: list[dict]) -> list[dict]:
    if not events:
        return []

    turn_start = [event for event in events if event.get("event_type") == "turn_start"]
    turn_end = [event for event in events if event.get("event_type") == "turn_end_snapshot"]
    middle = [
        event
        for event in events
        if event.get("event_type") not in {"turn_start", "turn_end_snapshot"}
    ]
    middle.sort(key=_turn_event_sort_key)
    return turn_start + middle + turn_end


@dataclass
class TurnReplay:
    """One complete turn with its terminal public snapshot."""

    turn_index: int
    round_index: int
    acting_player_id: int | None
    events: list[dict] = field(default_factory=list)
    snapshot: dict | None = None

    @property
    def player_states(self) -> list[dict]:
        return self.snapshot.get("players", []) if self.snapshot else []

    @property
    def board_state(self) -> dict | None:
        return self.snapshot.get("board") if self.snapshot else None

    @property
    def key_events(self) -> list[dict]:
        return [
            e
            for e in _ordered_turn_events(self.events)
            if e.get("event_type") not in _SKIP_IN_KEY_EVENTS
        ]

    @property
    def skipped(self) -> bool:
        return any(e.get("event_type") == "turn_start" and e.get("skipped") for e in self.events)


@dataclass
class RoundReplay:
    """One round grouping with optional pre-turn public events."""

    round_index: int
    weather: str = ""
    turns: list[TurnReplay] = field(default_factory=list)
    prelude_events: list[dict] = field(default_factory=list)

    @property
    def weather_name(self) -> str:
        return self.weather


@dataclass
class SessionReplay:
    """Top-level replay container."""

    session_id: str
    total_events: int
    turns: list[TurnReplay]
    rounds: list[RoundReplay]
    session_start: dict
    game_end: dict | None = None
    prelude_events: list[dict] = field(default_factory=list)

    @property
    def winner_player_id(self) -> int | None:
        if self.game_end:
            winner = self.game_end.get("winner_player_id")
            if winner is not None:
                return winner
            winner_ids = self.game_end.get("winner_ids") or []
            if winner_ids:
                return winner_ids[0]
        return None

    @property
    def end_reason(self) -> str:
        if self.game_end:
            return str(self.game_end.get("reason") or self.game_end.get("end_reason") or "")
        return ""


class ReplayProjection:
    """Project flat visual events into replay-friendly session/round/turn groupings."""

    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)
        self._session = self._build()

    @classmethod
    def from_list(cls, events: list[dict]) -> "ReplayProjection":
        return cls(events)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "ReplayProjection":
        events: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return cls(events)

    @classmethod
    def from_json(cls, path: str | Path) -> "ReplayProjection":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def session(self) -> SessionReplay:
        return self._session

    @property
    def turns(self) -> list[TurnReplay]:
        return self._session.turns

    @property
    def rounds(self) -> list[RoundReplay]:
        return self._session.rounds

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def raw_events(self) -> list[dict]:
        return list(self._events)

    def events_by_type(self, event_type: str) -> list[dict]:
        return [e for e in self._events if e.get("event_type") == event_type]

    def ordered_events(self) -> list[dict]:
        ordered: list[dict] = []
        current_turn_events: list[dict] = []

        for event in self._events:
            etype = event.get("event_type")
            if etype == "turn_start":
                if current_turn_events:
                    ordered.extend(_ordered_turn_events(current_turn_events))
                current_turn_events = [event]
                continue

            if current_turn_events:
                current_turn_events.append(event)
                if etype == "turn_end_snapshot":
                    ordered.extend(_ordered_turn_events(current_turn_events))
                    current_turn_events = []
                continue

            ordered.append(event)

        if current_turn_events:
            ordered.extend(_ordered_turn_events(current_turn_events))

        return ordered

    def _build(self) -> SessionReplay:
        events = self._events
        if not events:
            return SessionReplay(
                session_id="",
                total_events=0,
                turns=[],
                rounds=[],
                session_start={},
            )

        session_id = events[0].get("session_id", "")
        session_start = next((event for event in events if event.get("event_type") == "session_start"), {})
        game_end = None
        for event in reversed(events):
            if event.get("event_type") == "game_end":
                game_end = event
                break

        turns: list[TurnReplay] = []
        rounds: list[RoundReplay] = []
        session_prelude: list[dict] = []
        current_round: RoundReplay | None = None
        current_turn: TurnReplay | None = None

        for event in events:
            etype = event.get("event_type")

            if etype == "session_start":
                session_prelude.append(event)
                continue

            if etype == "round_start":
                current_round = RoundReplay(round_index=event.get("round_index", 0))
                current_round.prelude_events.append(event)
                rounds.append(current_round)
                continue

            if etype == "weather_reveal":
                if current_round is None:
                    session_prelude.append(event)
                else:
                    current_round.weather = (
                        event.get("weather_name")
                        or event.get("weather")
                        or event.get("card", "")
                    )
                    current_round.prelude_events.append(event)
                continue

            if etype == "turn_start":
                current_turn = TurnReplay(
                    turn_index=event.get("turn_index", 0),
                    round_index=event.get("round_index", 0),
                    acting_player_id=event.get("acting_player_id"),
                    events=[event],
                )
                turns.append(current_turn)
                if current_round is None:
                    current_round = RoundReplay(round_index=event.get("round_index", 0))
                    rounds.append(current_round)
                current_round.turns.append(current_turn)
                continue

            if current_turn is not None:
                current_turn.events.append(event)
                if etype == "turn_end_snapshot":
                    nested = event.get("snapshot") or {}
                    players = event.get("players") or nested.get("players")
                    board = event.get("board") or nested.get("board")
                    snapshot: dict[str, object] = {}
                    if players is not None:
                        snapshot["players"] = players
                    if board is not None:
                        snapshot["board"] = board
                    current_turn.snapshot = snapshot if snapshot else None
                    current_turn = None
                continue

            # Public events before the first turn of a round belong to round prelude.
            # Events before the first round belong to session prelude.
            if current_round is not None:
                current_round.prelude_events.append(event)
            else:
                session_prelude.append(event)

        return SessionReplay(
            session_id=session_id,
            total_events=len(events),
            turns=turns,
            rounds=rounds,
            session_start=session_start,
            game_end=game_end,
            prelude_events=session_prelude,
        )
