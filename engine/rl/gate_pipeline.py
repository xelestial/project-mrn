from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_policies import run_policy_comparison
from rl.diagnostics import write_learning_diagnostics
from rl.train_policy import train_behavior_clone
from simulate_with_logs import run as simulate_run


def run_gate_pipeline(
    *,
    output_dir: str | Path,
    train_games: int,
    eval_games: int,
    mixed_seat_games: int,
    seed: int,
    baseline_policy: str = "heuristic_v3_engine",
    epochs: int = 8,
    hidden_size: int = 64,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    replay_path = out / "train_source" / "rl_replay.jsonl"

    train_source_summary = simulate_run(
        simulations=int(train_games),
        seed=int(seed),
        output_dir=str(out / "train_source"),
        log_level="none",
        policy_mode=baseline_policy,
        lap_policy_mode=baseline_policy,
        emit_summary=False,
        emit_rl_replay=True,
        rl_replay_path=str(replay_path),
    )
    model_dir = out / "model"
    model_summary = train_behavior_clone(
        replay_path=replay_path,
        output_dir=model_dir,
        seed=seed,
        epochs=epochs,
        hidden_size=hidden_size,
    )
    comparison = run_policy_comparison(
        simulations=eval_games,
        seed=seed,
        output_dir=out / "compare",
        baseline_policy=baseline_policy,
        candidate_policy="rl_v1",
        candidate_model_dir=model_dir,
        lap_policy_mode=baseline_policy,
        policy_eval_replay=replay_path,
        mixed_seat_simulations=mixed_seat_games,
    )
    diagnostics = write_learning_diagnostics(
        replay_path=replay_path,
        comparison_path=out / "compare" / "comparison.json",
        output_path=out / "learning_diagnostics.json",
    )
    summary = {
        "version": 1,
        "output_dir": str(out),
        "replay_path": str(replay_path),
        "model_dir": str(model_dir),
        "comparison_path": str(out / "compare" / "comparison.json"),
        "diagnostics_path": str(out / "learning_diagnostics.json"),
        "train_source": {
            "games": train_games,
            "summary": train_source_summary,
        },
        "model": model_summary,
        "comparison": {
            "accepted": bool((comparison.get("acceptance") or {}).get("accepted")),
            "checks": (comparison.get("acceptance") or {}).get("checks") or {},
            "metrics": comparison.get("metrics") or {},
        },
        "diagnostics": {
            "rows": diagnostics["rows"],
            "negative_reward_rate": diagnostics["negative_reward_rate"],
            "worst_actions": diagnostics["worst_actions"][:5],
            "comparison_findings": diagnostics["comparison_findings"],
        },
    }
    (out / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MRN RL train, mixed-seat comparison, and diagnostics in one gate command.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--train-games", type=int, default=200)
    parser.add_argument("--eval-games", type=int, default=100)
    parser.add_argument("--mixed-seat-games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260507)
    parser.add_argument("--baseline-policy", default="heuristic_v3_engine")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--hidden-size", type=int, default=64)
    args = parser.parse_args(argv)
    summary = run_gate_pipeline(
        output_dir=args.output_dir,
        train_games=args.train_games,
        eval_games=args.eval_games,
        mixed_seat_games=args.mixed_seat_games,
        seed=args.seed,
        baseline_policy=args.baseline_policy,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
    )
    print(json.dumps({"accepted": summary["comparison"]["accepted"], "output_dir": summary["output_dir"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
