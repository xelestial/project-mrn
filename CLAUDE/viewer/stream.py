"""viewer/stream.py — VisEventStream: append-only structured event collector.

Attach to GameEngine at construction to capture all visualization events.
The stream is ordered, append-only, and deterministic in sequence.

Usage:
    stream = VisEventStream()
    engine = GameEngine(config, policy, event_stream=stream)
    engine.run()
    stream.to_jsonl("replay.jsonl")   # write for replay
    events = stream.events            # access in-memory list
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .events import VisEvent


class VisEventStream:
    """Ordered, append-only stream of VisEvent objects.

    Implements the event ordering rule from SHARED_VISUAL_RUNTIME_CONTRACT:
    - ordered (by step_index)
    - append-only
    - deterministic in sequence (step_index is monotonically increasing)
    """

    def __init__(self) -> None:
        self._events: list[VisEvent] = []

    def append(self, event: VisEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[VisEvent]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[VisEvent]:
        return iter(self._events)

    def by_type(self, event_type: str) -> list[VisEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def by_player(self, player_id: int) -> list[VisEvent]:
        """Return events for a given 1-indexed player_id."""
        return [e for e in self._events if e.acting_player_id == player_id]

    def to_jsonl(self, path: str | Path) -> None:
        """Write stream to newline-delimited JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def to_list(self) -> list[dict]:
        """Return all events as a list of dicts (JSON-serializable)."""
        return [e.to_dict() for e in self._events]

    def summary(self) -> dict:
        """Return a brief summary for debugging."""
        from collections import Counter
        counts = Counter(e.event_type for e in self._events)
        return {
            "total_events": len(self._events),
            "by_type": dict(counts),
        }
