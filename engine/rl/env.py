from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(slots=True)
class ReplayLearningEnv:
    rows: list[dict[str, Any]]
    _index: int = field(default=0, init=False)

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self.rows = list(rows)
        if not self.rows:
            raise ValueError("ReplayLearningEnv requires at least one replay row")
        self._index = 0

    def reset(self) -> dict[str, Any]:
        self._index = 0
        return dict(self.rows[0].get("observation") or {})

    def legal_actions(self) -> list[dict[str, Any]]:
        return list(self.rows[self._index].get("legal_actions") or [])

    def step(self, action_id: str) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        row = self.rows[self._index]
        reward_payload = row.get("reward") if isinstance(row.get("reward"), dict) else {}
        reward = float(reward_payload.get("total", 0.0) or 0.0)
        expert_action_id = str(row.get("chosen_action_id") or "")
        self._index += 1
        done = self._index >= len(self.rows)
        next_observation = {} if done else dict(self.rows[self._index].get("observation") or {})
        return next_observation, reward, done, {
            "expert_action_id": expert_action_id,
            "matched_expert": str(action_id) == expert_action_id,
            "row": row,
        }
