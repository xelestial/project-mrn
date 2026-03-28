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
        return [e for e in self.events if e.get("event_type") not in _SKIP_IN_KEY_EVENTS]

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
            return self.game_end.get("winner_player_id")
        return None

    @property
    def end_reason(self) -> str:
        if self.game_end:
            return self.game_end.get("reason", "")
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
        session_start = events[0] if events[0].get("event_type") == "session_start" else {}
        game_end = events[-1] if events[-1].get("event_type") == "game_end" else None

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
                    current_round.weather = event.get("weather_name", event.get("card", ""))
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
