from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rl.replay import iter_replay_rows
from rl.train_policy import predict_action


def evaluate_policy(*, model_dir: str | Path, replay_path: str | Path) -> dict[str, Any]:
    rows = list(iter_replay_rows(replay_path))
    evaluated = 0
    correct = 0
    illegal_predictions = 0
    by_decision: dict[str, dict[str, int]] = {}

    for row in rows:
        legal_action_ids = {str(action.get("action_id") or "") for action in row.get("legal_actions") or [] if action.get("legal", True)}
        if not legal_action_ids:
            continue
        predicted = predict_action(model_dir=model_dir, row=row).get("action_id") or ""
        chosen = str(row.get("chosen_action_id") or "")
        decision_key = str(row.get("decision_key") or "unknown")
        bucket = by_decision.setdefault(decision_key, {"rows": 0, "correct": 0, "illegal_predictions": 0})
        evaluated += 1
        bucket["rows"] += 1
        if predicted not in legal_action_ids:
            illegal_predictions += 1
            bucket["illegal_predictions"] += 1
            continue
        if predicted == chosen:
            correct += 1
            bucket["correct"] += 1

    return {
        "rows": evaluated,
        "action_accuracy": (correct / evaluated) if evaluated else 0.0,
        "illegal_predictions": illegal_predictions,
        "by_decision": {
            key: {
                **value,
                "action_accuracy": (value["correct"] / value["rows"]) if value["rows"] else 0.0,
            }
            for key, value in sorted(by_decision.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained MRN RL policy against replay JSONL.")
    parser.add_argument("model_dir")
    parser.add_argument("replay_path")
    args = parser.parse_args()
    print(json.dumps(evaluate_policy(model_dir=args.model_dir, replay_path=args.replay_path), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
