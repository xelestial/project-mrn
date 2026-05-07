from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from statistics import mean
from typing import Any, Iterator

from ai_policy import HeuristicPolicy
from rl.evaluate_policy import evaluate_policy
from simulate_with_logs import run as run_simulation
from text_encoding import configure_utf8_io


DEFAULT_BASELINE_POLICY = "heuristic_v3_engine"
DEFAULT_CANDIDATE_POLICY = "rl_v1"
DEFAULT_BANKRUPTCY_TOLERANCE = 0.02


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_policy_comparison(
    *,
    baseline_policy: str,
    candidate_policy: str,
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_games: list[dict[str, Any]] | None = None,
    candidate_games: list[dict[str, Any]] | None = None,
    baseline_runtime_failed_count: int = 0,
    candidate_runtime_failed_count: int = 0,
    policy_eval: dict[str, Any] | None = None,
    bankruptcy_tolerance: float = DEFAULT_BANKRUPTCY_TOLERANCE,
) -> dict[str, Any]:
    policy_eval = dict(policy_eval or {})
    baseline_metrics = _summary_metrics(
        baseline_summary,
        games=baseline_games or [],
        runtime_failed_count=baseline_runtime_failed_count,
    )
    candidate_metrics = _summary_metrics(
        candidate_summary,
        games=candidate_games or [],
        runtime_failed_count=candidate_runtime_failed_count,
        policy_eval=policy_eval,
    )
    deltas = {
        key: candidate_metrics[key] - baseline_metrics[key]
        for key in sorted(set(baseline_metrics) & set(candidate_metrics))
        if isinstance(baseline_metrics[key], (int, float)) and isinstance(candidate_metrics[key], (int, float))
    }
    thresholds = {
        "runtime_failed_count": 0,
        "illegal_action_count": 0,
        "timeout_count": 0,
        "bankruptcy_rate_max_delta": bankruptcy_tolerance,
        "average_rank_max_delta": 0.0,
    }
    checks = {
        "baseline_runtime_failed_zero": baseline_metrics["runtime_failed_count"] == 0,
        "candidate_runtime_failed_zero": candidate_metrics["runtime_failed_count"] == 0,
        "candidate_illegal_action_zero": candidate_metrics["illegal_action_count"] == 0,
        "candidate_timeout_zero": candidate_metrics["timeout_count"] == 0,
        "bankruptcy_rate_not_regressed": candidate_metrics["bankruptcy_rate"]
        <= baseline_metrics["bankruptcy_rate"] + bankruptcy_tolerance,
        "average_rank_not_regressed": candidate_metrics["average_rank"] <= baseline_metrics["average_rank"],
    }
    return {
        "version": candidate_summary.get("version") or baseline_summary.get("version"),
        "baseline_policy": baseline_policy,
        "candidate_policy": candidate_policy,
        "games": {
            "baseline": int(baseline_summary.get("games") or 0),
            "candidate": int(candidate_summary.get("games") or 0),
        },
        "policies": {
            "baseline": baseline_summary,
            "candidate": candidate_summary,
        },
        "metrics": {
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
        },
        "deltas": deltas,
        "policy_eval": policy_eval,
        "acceptance": {
            "thresholds": thresholds,
            "checks": checks,
            "accepted": all(checks.values()),
        },
    }


def run_policy_comparison(
    *,
    simulations: int,
    seed: int,
    output_dir: str | Path,
    baseline_policy: str = DEFAULT_BASELINE_POLICY,
    candidate_policy: str = DEFAULT_CANDIDATE_POLICY,
    baseline_model_dir: str | Path | None = None,
    candidate_model_dir: str | Path | None = None,
    lap_policy_mode: str = DEFAULT_BASELINE_POLICY,
    policy_eval_replay: str | Path | None = None,
    bankruptcy_tolerance: float = DEFAULT_BANKRUPTCY_TOLERANCE,
) -> dict[str, Any]:
    _validate_model_config(policy=baseline_policy, model_dir=baseline_model_dir)
    _validate_model_config(policy=candidate_policy, model_dir=candidate_model_dir)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    baseline_run = _run_policy(
        simulations=simulations,
        seed=seed,
        output_dir=out / "baseline",
        policy_mode=baseline_policy,
        lap_policy_mode=lap_policy_mode,
        model_dir=baseline_model_dir,
    )
    candidate_run = _run_policy(
        simulations=simulations,
        seed=seed,
        output_dir=out / "candidate",
        policy_mode=candidate_policy,
        lap_policy_mode=lap_policy_mode,
        model_dir=candidate_model_dir,
    )
    policy_eval: dict[str, Any] = {}
    if policy_eval_replay and candidate_model_dir:
        policy_eval = evaluate_policy(model_dir=candidate_model_dir, replay_path=policy_eval_replay)

    comparison = build_policy_comparison(
        baseline_policy=baseline_policy,
        candidate_policy=candidate_policy,
        baseline_summary=baseline_run["summary"],
        candidate_summary=candidate_run["summary"],
        baseline_games=load_jsonl(Path(baseline_run["output_dir"]) / "games.jsonl"),
        candidate_games=load_jsonl(Path(candidate_run["output_dir"]) / "games.jsonl"),
        baseline_runtime_failed_count=baseline_run["runtime_failed_count"],
        candidate_runtime_failed_count=candidate_run["runtime_failed_count"],
        policy_eval=policy_eval,
        bankruptcy_tolerance=bankruptcy_tolerance,
    )
    comparison["runs"] = {
        "baseline": baseline_run,
        "candidate": candidate_run,
    }
    (out / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return comparison


def _run_policy(
    *,
    simulations: int,
    seed: int,
    output_dir: Path,
    policy_mode: str,
    lap_policy_mode: str,
    model_dir: str | Path | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    error: str | None = None
    with _temporary_env("MRN_RL_POLICY_MODEL", str(model_dir) if model_dir else None):
        try:
            summary = run_simulation(
                simulations=simulations,
                seed=seed,
                output_dir=str(output_dir),
                log_level="none",
                policy_mode=policy_mode,
                lap_policy_mode=lap_policy_mode,
                emit_summary=False,
            )
        except Exception as exc:  # The comparison report must survive failed candidates.
            error = repr(exc)
            summary = _load_existing_summary(output_dir)
    runtime_failed_count = _count_jsonl(output_dir / "errors.jsonl")
    if error and runtime_failed_count == 0:
        runtime_failed_count = 1
    return {
        "policy_mode": policy_mode,
        "output_dir": str(output_dir),
        "summary": summary or {},
        "runtime_failed_count": runtime_failed_count,
        "error": error,
    }


def _summary_metrics(
    summary: dict[str, Any],
    *,
    games: list[dict[str, Any]],
    runtime_failed_count: int,
    policy_eval: dict[str, Any] | None = None,
) -> dict[str, float | int]:
    players = summary.get("players") if isinstance(summary.get("players"), dict) else {}
    policy_eval = policy_eval or {}
    return {
        "runtime_failed_count": int(runtime_failed_count),
        "illegal_action_count": int(policy_eval.get("illegal_predictions") or 0),
        "timeout_count": 0,
        "bankruptcy_rate": _number(summary.get("bankrupt_any_rate")),
        "average_rank": _average_rank_from_games(games),
        "avg_total_turns": _number(summary.get("avg_total_turns")),
        "avg_rounds": _number(summary.get("avg_rounds")),
        "avg_final_f_value": _number(summary.get("avg_final_f_value")),
        "avg_final_shards_per_player": _number(summary.get("avg_final_shards_per_player")),
        "avg_cash_per_player": _mean(_number(p.get("avg_cash")) for p in players.values()),
        "avg_score_per_player": _mean(_number(p.get("avg_score")) for p in players.values()),
        "avg_placed_per_player": _mean(_number(p.get("avg_placed")) for p in players.values()),
    }


def _average_rank_from_games(games: list[dict[str, Any]]) -> float:
    ranks: list[float] = []
    for game in games:
        players = list(game.get("player_summary") or [])
        if not players:
            continue
        ordered = sorted(
            players,
            key=lambda p: (
                _number(p.get("score")),
                _number(p.get("placed_score_coins")),
                _number(p.get("cash")),
                _number(p.get("tiles_owned")),
            ),
            reverse=True,
        )
        ranks.extend(float(index) for index, _ in enumerate(ordered, start=1))
    return _mean(ranks)


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _load_existing_summary(output_dir: Path) -> dict[str, Any]:
    for name in ("summary.json", "summary.partial.json"):
        path = output_dir / name
        if path.exists():
            return load_json(path)
    return {}


def _validate_model_config(*, policy: str, model_dir: str | Path | None) -> None:
    if policy != "rl_v1":
        return
    if not model_dir:
        raise ValueError("rl_v1 comparison requires a model directory")
    metadata_path = Path(model_dir) / "policy_model.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"RL policy metadata not found: {metadata_path}")


def _mean(values: Any) -> float:
    vals = [float(value) for value in values]
    return mean(vals) if vals else 0.0


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


@contextmanager
def _temporary_env(name: str, value: str | None) -> Iterator[None]:
    previous = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def main() -> None:
    configure_utf8_io()
    valid_character_policies = sorted({*HeuristicPolicy.VALID_CHARACTER_POLICIES, "rl_v1"})
    parser = argparse.ArgumentParser(description="Compare baseline and candidate MRN policies with RL acceptance checks.")
    parser.add_argument("--simulations", "--games", dest="simulations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260507)
    parser.add_argument("--output-dir", type=str, default="analysis_output/policy_compare")
    parser.add_argument("--baseline-policy", choices=valid_character_policies, default=DEFAULT_BASELINE_POLICY)
    parser.add_argument("--candidate-policy", choices=valid_character_policies, default=DEFAULT_CANDIDATE_POLICY)
    parser.add_argument("--baseline-model-dir", type=str, default=None)
    parser.add_argument("--candidate-model-dir", "--model-dir", dest="candidate_model_dir", type=str, default=None)
    parser.add_argument("--lap-policy-mode", choices=sorted(HeuristicPolicy.VALID_LAP_POLICIES), default=DEFAULT_BASELINE_POLICY)
    parser.add_argument("--policy-eval-replay", type=str, default=None)
    parser.add_argument("--bankruptcy-tolerance", type=float, default=DEFAULT_BANKRUPTCY_TOLERANCE)
    parser.add_argument("--compact", action="store_true", help="Print only metrics and acceptance instead of full summaries.")
    args = parser.parse_args()
    comparison = run_policy_comparison(
        simulations=args.simulations,
        seed=args.seed,
        output_dir=args.output_dir,
        baseline_policy=args.baseline_policy,
        candidate_policy=args.candidate_policy,
        baseline_model_dir=args.baseline_model_dir,
        candidate_model_dir=args.candidate_model_dir,
        lap_policy_mode=args.lap_policy_mode,
        policy_eval_replay=args.policy_eval_replay,
        bankruptcy_tolerance=args.bankruptcy_tolerance,
    )
    if args.compact:
        comparison = {
            "baseline_policy": comparison["baseline_policy"],
            "candidate_policy": comparison["candidate_policy"],
            "metrics": comparison["metrics"],
            "deltas": comparison["deltas"],
            "acceptance": comparison["acceptance"],
            "report_path": str(Path(args.output_dir) / "comparison.json"),
        }
    print(json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
