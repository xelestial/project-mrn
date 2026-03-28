"""Phase 2 — ReplayProjection: event stream → navigable turn snapshots.

Consumes the flat VisEvent list produced by VisEventStream.to_list() (or loaded
from a .jsonl / .json file) and groups events into per-turn structures so that
renderers can iterate over the game as a sequence of turns.

Usage:
    from viewer.replay import ReplayProjection

    proj = ReplayProjection.from_jsonl("replay.jsonl")
    for turn in proj.turns:
        print(turn.turn_index, turn.key_events)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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
    """One complete turn: all events that occurred + terminal snapshot."""

    turn_index: int
    round_index: int
    acting_player_id: int | None
    events: list[dict] = field(default_factory=list)
    snapshot: dict | None = None  # turn_end_snapshot payload (players + board)

    @property
    def player_states(self) -> list[dict]:
        """PlayerPublicState dicts from turn_end_snapshot, or empty list."""
        return self.snapshot.get("players", []) if self.snapshot else []

    @property
    def board_state(self) -> dict | None:
        """BoardPublicState dict from turn_end_snapshot, or None."""
        return self.snapshot.get("board") if self.snapshot else None

    @property
    def key_events(self) -> list[dict]:
        """Meaningful events (excludes session/turn scaffolding)."""
        return [e for e in self.events if e.get("event_type") not in _SKIP_IN_KEY_EVENTS]

    @property
    def skipped(self) -> bool:
        """True when this turn was skipped (bankrupt / forced skip)."""
        for e in self.events:
            if e.get("event_type") == "turn_start" and e.get("skipped"):
                return True
        return False


@dataclass
class RoundReplay:
    """One round grouping of turns."""

    round_index: int
    weather: str = ""
    turns: list[TurnReplay] = field(default_factory=list)


@dataclass
class SessionReplay:
    """Full session metadata + all turns."""

    session_id: str
    total_events: int
    turns: list[TurnReplay]
    rounds: list[RoundReplay]
    session_start: dict
    game_end: dict | None = None

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


# ---------------------------------------------------------------------------
# ReplayProjection
# ---------------------------------------------------------------------------


class ReplayProjection:
    """Projects a flat VisEvent list into a navigable replay structure.

    The primary grouping unit is a *turn*, bounded by ``turn_start`` →
    ``turn_end_snapshot`` events.  The terminal state of each turn is stored
    directly in ``TurnReplay.snapshot`` (from ``turn_end_snapshot`` payload)
    so renderers never need to reconstruct state from scratch.

    Rounds are synthesised from ``round_start`` events for hierarchical
    navigation.
    """

    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)
        self._session = self._build()

    # ------------------------------------------------------------------
    # Class-method constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_list(cls, events: list[dict]) -> "ReplayProjection":
        """Construct from an in-memory list (e.g. VisEventStream.to_list())."""
        return cls(events)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "ReplayProjection":
        """Construct from a JSONL file (one event per line)."""
        events: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return cls(events)

    @classmethod
    def from_json(cls, path: str | Path) -> "ReplayProjection":
        """Construct from a JSON array file."""
        with open(path, encoding="utf-8") as f:
            events = json.load(f)
        return cls(events)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def session(self) -> SessionReplay:
        return self._session

    @property
    def turns(self) -> list[TurnReplay]:
        return self._session.turns

    @property
    def rounds(self) -> list[RoundReplay]:
        return self._session.rounds

    def raw_events(self) -> list[dict]:
        return list(self._events)

    def events_by_type(self, event_type: str) -> list[dict]:
        return [e for e in self._events if e.get("event_type") == event_type]

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> SessionReplay:
        events = self._events
        if not events:
            return SessionReplay(
                session_id="", total_events=0,
                turns=[], rounds=[], session_start={},
            )

        session_id = events[0].get("session_id", "")
        session_start = events[0] if events[0].get("event_type") == "session_start" else {}
        game_end = events[-1] if events[-1].get("event_type") == "game_end" else None

        turns: list[TurnReplay] = []
        rounds: list[RoundReplay] = []
        current_turn: TurnReplay | None = None
        current_round: RoundReplay | None = None

        for event in events:
            etype = event.get("event_type")

            if etype == "round_start":
                # Synthesise a new round container
                ridx = event.get("round_index", 0)
                current_round = RoundReplay(round_index=ridx)
                rounds.append(current_round)

            elif etype == "weather_reveal":
                if current_round is not None:
                    current_round.weather = event.get("weather_name", event.get("card", ""))

            elif etype == "turn_start":
                current_turn = TurnReplay(
                    turn_index=event.get("turn_index", 0),
                    round_index=event.get("round_index", 0),
                    acting_player_id=event.get("acting_player_id"),
                    events=[event],
                )
                turns.append(current_turn)
                if current_round is not None:
                    current_round.turns.append(current_turn)

            elif current_turn is not None:
                current_turn.events.append(event)

                if etype == "turn_end_snapshot":
                    # Extract snapshot payload.
                    # CLAUDE engine: flat-merged → event["players"], event["board"]
                    # GPT engine:   nested      → event["snapshot"]["players/board"]
                    nested = event.get("snapshot") or {}
                    players = event.get("players") or nested.get("players")
                    board = event.get("board") or nested.get("board")
                    snapshot: dict = {}
                    if players is not None:
                        snapshot["players"] = players
                    if board is not None:
                        snapshot["board"] = board
                    current_turn.snapshot = snapshot if snapshot else None
                    current_turn = None  # turn closed

            # Events before the first turn_start (session_start, round_start,
            # weather_reveal, draft_pick, final_character_choice) are NOT
            # attached to any turn but are available via raw_events() /
            # events_by_type().

        return SessionReplay(
            session_id=session_id,
            total_events=len(events),
            turns=turns,
            rounds=rounds,
            session_start=session_start,
            game_end=game_end,
        )
