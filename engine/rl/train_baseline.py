from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rl.replay import iter_replay_rows


def train_behavior_baseline(*, replay_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    rows = list(iter_replay_rows(replay_path))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    counts: dict[str, Counter[str]] = defaultdict(Counter)
    value_sums: dict[str, float] = defaultdict(float)
    decision_rows: Counter[str] = Counter()
    correct = 0
    evaluated = 0
    for row in rows:
        decision_key = str(row.get("decision_key") or "unknown")
        action_id = str(row.get("chosen_action_id") or "")
        if action_id:
            counts[decision_key][action_id] += 1
            evaluated += 1
        reward = row.get("reward") if isinstance(row.get("reward"), dict) else {}
        value_sums[decision_key] += float(reward.get("total", 0.0) or 0.0)
        decision_rows[decision_key] += 1

    policy: dict[str, dict[str, Any]] = {}
    for decision_key, action_counts in counts.items():
        top_action = action_counts.most_common(1)[0][0] if action_counts else ""
        policy[decision_key] = {
            "default_action_id": top_action,
            "action_counts": dict(action_counts),
            "avg_reward": value_sums[decision_key] / decision_rows[decision_key] if decision_rows[decision_key] else 0.0,
        }
        correct += action_counts[top_action]

    result = {
        "rows": len(rows),
        "decision_count": len(decision_rows),
        "behavior_accuracy": (correct / evaluated) if evaluated else 0.0,
        "policy": policy,
    }
    (out / "policy_baseline.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
