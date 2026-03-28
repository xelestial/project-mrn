from __future__ import annotations

import json
from pathlib import Path

from .events import VisEvent
from .replay import ReplayProjection
from .stream import VisEventStream


class LiveSpectatorStream(VisEventStream):
    """Append-only event stream that also materializes live spectator artifacts."""

    def __init__(self, out_dir: str | Path) -> None:
        super().__init__()
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.out_dir / "events.jsonl"
        self.state_path = self.out_dir / "live_state.json"
        self._status = "running"

        self.events_path.write_text("", encoding="utf-8")
        self._write_state()

    def append(self, event: VisEvent) -> None:
        super().append(event)
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        if event.event_type == "game_end":
            self._status = "completed"
        self._write_state()

    def mark_completed(self) -> None:
        self._status = "completed"
        self._write_state()

    def _write_state(self) -> None:
        payload = self._build_live_state()
        temp_path = self.state_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        temp_path.replace(self.state_path)

    def _build_live_state(self) -> dict:
        events = self.to_list()
        projection = ReplayProjection.from_list(events)
        latest_turn = projection.turns[-1].to_dict() if projection.turns else None
        return {
            "schema": "gpt.phase3.live_state.v1",
            "status": self._status,
            "summary": self.summary(),
            "projection": projection.to_dict(),
            "latest_turn": latest_turn,
            "latest_turn_position": projection.turn_count - 1 if projection.turn_count else None,
        }
