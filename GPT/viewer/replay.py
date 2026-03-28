from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SCAFFOLD_EVENT_TYPES = frozenset(
    {
        "session_start",
        "round_start",
        "turn_start",
        "turn_end_snapshot",
        "trick_window_open",
        "trick_window_closed",
    }
)


@dataclass(slots=True)
class TurnReplay:
    turn_index: int
    round_index: int
    acting_player_id: int | None
    events: list[dict] = field(default_factory=list)
    snapshot: dict | None = None

    @property
    def event_types(self) -> list[str]:
        return [event.get("event_type", "") for event in self.events]

    @property
    def player_states(self) -> list[dict]:
        return self.snapshot.get("players", []) if self.snapshot else []

    @property
    def board_state(self) -> dict | None:
        return self.snapshot.get("board") if self.snapshot else None

    @property
    def key_events(self) -> list[dict]:
        return [
            event
            for event in self.events
            if event.get("event_type") not in SCAFFOLD_EVENT_TYPES
        ]

    @property
    def skipped(self) -> bool:
        turn_start = self.events[0] if self.events else {}
        return bool(turn_start.get("event_type") == "turn_start" and turn_start.get("skipped"))

    @property
    def final_f_value(self) -> float | None:
        board = self.board_state
        if board is None:
            return None
        return board.get("f_value")

    def to_dict(self) -> dict:
        return {
            "turn_index": self.turn_index,
            "round_index": self.round_index,
            "acting_player_id": self.acting_player_id,
            "skipped": self.skipped,
            "events": list(self.events),
            "key_events": self.key_events,
            "snapshot": self.snapshot,
        }


@dataclass(slots=True)
class RoundReplay:
    round_index: int
    prelude_events: list[dict] = field(default_factory=list)
    turns: list[TurnReplay] = field(default_factory=list)
    weather_name: str = ""

    def to_dict(self) -> dict:
        return {
            "round_index": self.round_index,
            "weather_name": self.weather_name,
            "prelude_events": list(self.prelude_events),
            "turns": [turn.to_dict() for turn in self.turns],
        }


@dataclass(slots=True)
class SessionReplay:
    session_id: str
    total_events: int
    session_start: dict
    prelude_events: list[dict]
    turns: list[TurnReplay]
    rounds: list[RoundReplay]
    game_end: dict | None = None

    @property
    def winner_player_id(self) -> int | None:
        if not self.game_end:
            return None
        return self.game_end.get("winner_player_id")

    @property
    def end_reason(self) -> str:
        if not self.game_end:
            return ""
        return self.game_end.get("reason", "")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "total_events": self.total_events,
            "session_start": self.session_start,
            "prelude_events": list(self.prelude_events),
            "turns": [turn.to_dict() for turn in self.turns],
            "rounds": [round_replay.to_dict() for round_replay in self.rounds],
            "game_end": self.game_end,
            "winner_player_id": self.winner_player_id,
            "end_reason": self.end_reason,
        }


class ReplayProjection:
    """Project flat visual events into replay-friendly session/round/turn views."""

    def __init__(self, events: Iterable[dict]) -> None:
        self._events = [dict(event) for event in events]
        self._session = self._build()
        self._turns_by_turn_index = {
            turn.turn_index: turn
            for turn in self._session.turns
        }
        self._rounds_by_round_index = {
            round_replay.round_index: round_replay
            for round_replay in self._session.rounds
        }

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
            payload = json.load(f)
        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict):
            if isinstance(payload.get("raw_events"), list):
                events = payload["raw_events"]
            elif isinstance(payload.get("events"), list):
                events = payload["events"]
            else:
                raise ValueError("JSON replay payload must contain raw_events or events")
        else:
            raise TypeError("JSON replay payload must be a list or dict")
        return cls(events)

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
        return len(self._session.turns)

    @property
    def round_count(self) -> int:
        return len(self._session.rounds)

    def raw_events(self) -> list[dict]:
        return list(self._events)

    def to_dict(self) -> dict:
        return {
            "schema": "gpt.phase2.replay.v1",
            "session": self._session.to_dict(),
            "event_counts": self.counts_by_event_type(),
            "raw_events": self.raw_events(),
        }

    def events_by_type(self, event_type: str) -> list[dict]:
        return [event for event in self._events if event.get("event_type") == event_type]

    def counts_by_event_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events:
            event_type = event.get("event_type", "")
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts

    def turn_at(self, position: int) -> TurnReplay:
        return self._session.turns[position]

    def get_turn(self, turn_index: int) -> TurnReplay | None:
        return self._turns_by_turn_index.get(turn_index)

    def get_round(self, round_index: int) -> RoundReplay | None:
        return self._rounds_by_round_index.get(round_index)

    def turns_for_player(self, player_id: int) -> list[TurnReplay]:
        return [
            turn
            for turn in self._session.turns
            if turn.acting_player_id == player_id
        ]

    def turns_for_round(self, round_index: int) -> list[TurnReplay]:
        round_replay = self.get_round(round_index)
        if round_replay is None:
            return []
        return list(round_replay.turns)

    def round_prelude_events(self, round_index: int) -> list[dict]:
        round_replay = self.get_round(round_index)
        if round_replay is None:
            return []
        return list(round_replay.prelude_events)

    def _build(self) -> SessionReplay:
        if not self._events:
            return SessionReplay(
                session_id="",
                total_events=0,
                session_start={},
                prelude_events=[],
                turns=[],
                rounds=[],
                game_end=None,
            )

        session_start = {}
        session_prelude_events: list[dict] = []
        rounds: list[RoundReplay] = []
        turns: list[TurnReplay] = []
        current_round: RoundReplay | None = None
        current_turn: TurnReplay | None = None
        game_end: dict | None = None

        for event in self._events:
            event_type = event.get("event_type")

            if event_type == "session_start":
                session_start = event
                continue

            if event_type == "game_end":
                game_end = event
                if current_turn is not None:
                    current_turn.events.append(event)
                elif current_round is not None:
                    current_round.prelude_events.append(event)
                else:
                    session_prelude_events.append(event)
                continue

            if event_type == "round_start":
                current_round = RoundReplay(round_index=event.get("round_index", 0))
                current_round.prelude_events.append(event)
                rounds.append(current_round)
                current_turn = None
                continue

            if event_type == "weather_reveal":
                if current_round is None:
                    session_prelude_events.append(event)
                else:
                    current_round.weather_name = event.get("weather_name") or event.get("card", "")
                    current_round.prelude_events.append(event)
                continue

            if event_type == "turn_start":
                if current_round is None:
                    current_round = RoundReplay(round_index=event.get("round_index", 0))
                    rounds.append(current_round)
                current_turn = TurnReplay(
                    turn_index=event.get("turn_index", 0),
                    round_index=event.get("round_index", 0),
                    acting_player_id=event.get("acting_player_id"),
                    events=[event],
                )
                current_round.turns.append(current_turn)
                turns.append(current_turn)
                continue

            if current_turn is not None:
                current_turn.events.append(event)
                if event_type == "turn_end_snapshot":
                    current_turn.snapshot = _extract_turn_snapshot(event)
                    current_turn = None
                continue

            if current_round is not None:
                current_round.prelude_events.append(event)
            else:
                session_prelude_events.append(event)

        first_event = self._events[0]
        return SessionReplay(
            session_id=first_event.get("session_id", ""),
            total_events=len(self._events),
            session_start=session_start,
            prelude_events=session_prelude_events,
            turns=turns,
            rounds=rounds,
            game_end=game_end,
        )


def _extract_turn_snapshot(event: dict) -> dict | None:
    nested = event.get("snapshot") or {}
    players = event.get("players") or nested.get("players")
    board = event.get("board") or nested.get("board")
    if players is None and board is None:
        return None
    snapshot: dict = {}
    if players is not None:
        snapshot["players"] = players
    if board is not None:
        snapshot["board"] = board
    return snapshot
