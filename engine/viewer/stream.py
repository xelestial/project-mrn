from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .events import VisEvent


class VisEventStream:
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
        return [e for e in self._events if e.acting_player_id == player_id]

    def to_jsonl(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self._events]

    def summary(self) -> dict:
        from collections import Counter
        counts = Counter(e.event_type for e in self._events)
        return {
            "total_events": len(self._events),
            "by_type": dict(counts),
        }
