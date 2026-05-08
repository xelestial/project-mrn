from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from rl.replay import iter_replay_rows


def build_learning_diagnostics(
    *,
    replay_rows: Iterable[dict[str, Any]],
    comparison: dict[str, Any] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    rows = list(replay_rows)
    decision_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    action_buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        decision_key = str(row.get("decision_key") or "unknown")
        action_id = str(row.get("chosen_action_id") or "")
        decision_buckets[decision_key].append(row)
        action_buckets[(decision_key, action_id)].append(row)

    by_decision = {
        decision: _bucket_summary(bucket)
        for decision, bucket in sorted(decision_buckets.items())
    }
    by_action = [
        {
            "decision_key": decision,
            "action_id": action,
            **_bucket_summary(bucket),
        }
        for (decision, action), bucket in sorted(action_buckets.items())
    ]
    by_action.sort(key=lambda item: (item["avg_reward"], -item["rows"]))

    high_weight_losses = [
        _row_digest(row)
        for row in sorted(
            (row for row in rows if _reward_total(row) < 0.0),
            key=lambda row: (_sample_weight(row), abs(_reward_total(row))),
            reverse=True,
        )[:top_n]
    ]

    report = {
        "version": 1,
        "rows": len(rows),
        "decision_count": len(by_decision),
        "avg_reward": _mean(_reward_total(row) for row in rows),
        "avg_sample_weight": _mean(_sample_weight(row) for row in rows),
        "negative_reward_rate": _mean(1.0 if _reward_total(row) < 0.0 else 0.0 for row in rows),
        "by_decision": by_decision,
        "worst_actions": by_action[:top_n],
        "best_actions": list(reversed(by_action[-top_n:])),
        "high_weight_losses": high_weight_losses,
        "comparison_findings": _comparison_findings(comparison or {}),
    }
    return report


def write_learning_diagnostics(
    *,
    replay_path: str | Path,
    output_path: str | Path,
    comparison_path: str | Path | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    comparison = _load_json(comparison_path) if comparison_path else None
    report = build_learning_diagnostics(
        replay_rows=iter_replay_rows(replay_path),
        comparison=comparison,
        top_n=top_n,
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _bucket_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [_rank(row) for row in rows if _rank(row) is not None]
    actions = Counter(str(row.get("chosen_action_id") or "") for row in rows)
    return {
        "rows": len(rows),
        "avg_reward": _mean(_reward_total(row) for row in rows),
        "avg_sample_weight": _mean(_sample_weight(row) for row in rows),
        "negative_reward_rate": _mean(1.0 if _reward_total(row) < 0.0 else 0.0 for row in rows),
        "win_rate": _mean(1.0 if _outcome(row).get("won") else 0.0 for row in rows),
        "avg_rank": _mean(float(rank) for rank in ranks),
        "top_actions": actions.most_common(5),
    }


def _comparison_findings(comparison: dict[str, Any]) -> dict[str, Any]:
    if not comparison:
        return {"failing_checks": [], "worst_mixed_seat_rotations": []}
    failing_checks = [
        path
        for path, value in _walk_checks(comparison)
        if value is False
    ]
    rotations = list(((comparison.get("mixed_seat") or {}).get("rotations") or []))
    worst_rotations = []
    for rotation in rotations:
        deltas = rotation.get("deltas") if isinstance(rotation.get("deltas"), dict) else {}
        worst_rotations.append(
            {
                "seat": rotation.get("seat"),
                "seed": rotation.get("seed"),
                "accepted": bool(rotation.get("accepted")),
                "average_rank_delta": float(deltas.get("average_rank") or 0.0),
                "bankruptcy_rate_delta": float(deltas.get("bankruptcy_rate") or 0.0),
                "win_rate_delta": float(deltas.get("win_rate") or 0.0),
            }
        )
    worst_rotations.sort(key=lambda item: (item["bankruptcy_rate_delta"], item["average_rank_delta"]), reverse=True)
    return {
        "accepted": bool((comparison.get("acceptance") or {}).get("accepted")),
        "failing_checks": failing_checks,
        "worst_mixed_seat_rotations": worst_rotations[:8],
    }


def _walk_checks(value: Any, prefix: str = "") -> Iterable[tuple[str, bool]]:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key == "checks" and isinstance(child, dict):
                for check_key, check_value in child.items():
                    if isinstance(check_value, bool):
                        yield f"{path}.{check_key}", check_value
            else:
                yield from _walk_checks(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_checks(child, f"{prefix}[{index}]")


def _row_digest(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": row.get("game_id"),
        "seed": row.get("seed"),
        "step": row.get("step"),
        "player_id": row.get("player_id"),
        "decision_key": row.get("decision_key"),
        "chosen_action_id": row.get("chosen_action_id"),
        "reward": _reward_total(row),
        "sample_weight": _sample_weight(row),
        "outcome": row.get("outcome") if isinstance(row.get("outcome"), dict) else {},
    }


def _reward_total(row: dict[str, Any]) -> float:
    reward = row.get("reward") if isinstance(row.get("reward"), dict) else {}
    return _number(reward.get("total"))


def _sample_weight(row: dict[str, Any]) -> float:
    return _number(row.get("sample_weight"), default=1.0)


def _outcome(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("outcome") if isinstance(row.get("outcome"), dict) else {}


def _rank(row: dict[str, Any]) -> int | None:
    rank = _outcome(row).get("rank")
    return int(rank) if isinstance(rank, int) else None


def _mean(values: Iterable[float]) -> float:
    vals = [float(value) for value in values]
    return sum(vals) / len(vals) if vals else 0.0


def _number(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build RL learning diagnostics from replay and comparison artifacts.")
    parser.add_argument("--replay", required=True)
    parser.add_argument("--comparison")
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args(argv)
    report = write_learning_diagnostics(
        replay_path=args.replay,
        comparison_path=args.comparison,
        output_path=args.output,
        top_n=args.top_n,
    )
    print(json.dumps({key: report[key] for key in ["rows", "decision_count", "avg_reward", "negative_reward_rate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
