from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_policy_evaluation_report(
    *,
    baseline_summary: dict[str, Any] | None = None,
    candidate_summary: dict[str, Any] | None = None,
    policy_eval: dict[str, Any] | None = None,
    seed_matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_metrics = flatten_numeric_metrics(baseline_summary or {})
    candidate_metrics = flatten_numeric_metrics(candidate_summary or {})
    metric_deltas = {
        key: {
            "baseline": baseline_metrics[key],
            "candidate": candidate_metrics[key],
            "delta": candidate_metrics[key] - baseline_metrics[key],
        }
        for key in sorted(set(baseline_metrics) & set(candidate_metrics))
    }
    return {
        "metric_deltas": metric_deltas,
        "policy_eval": policy_eval or {},
        "seed_matrix": _compact_seed_matrix(seed_matrix or {}),
    }


def flatten_numeric_metrics(value: Any, *, prefix: str = "") -> dict[str, float]:
    if isinstance(value, bool):
        return {}
    if isinstance(value, int | float):
        return {prefix: float(value)} if prefix else {}
    if isinstance(value, dict):
        metrics: dict[str, float] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            metrics.update(flatten_numeric_metrics(child, prefix=child_prefix))
        return metrics
    return {}


def _compact_seed_matrix(seed_matrix: dict[str, Any]) -> dict[str, Any]:
    keys = ["policy_mode", "model_dir", "simulations_per_seed", "seed_count", "total_games", "total_failed_games", "total_replay_rows"]
    return {key: seed_matrix[key] for key in keys if key in seed_matrix}


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an RL policy evaluation report from JSON artifacts.")
    parser.add_argument("--baseline-summary")
    parser.add_argument("--candidate-summary")
    parser.add_argument("--policy-eval")
    parser.add_argument("--seed-matrix")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = build_policy_evaluation_report(
        baseline_summary=_load_json(args.baseline_summary),
        candidate_summary=_load_json(args.candidate_summary),
        policy_eval=_load_json(args.policy_eval),
        seed_matrix=_load_json(args.seed_matrix),
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
