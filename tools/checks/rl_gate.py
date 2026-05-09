from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from rl.gate_pipeline import run_gate_pipeline  # noqa: E402


PROFILES = {
    "smoke": {
        "train_games": 8,
        "eval_games": 3,
        "mixed_seat_games": 1,
        "epochs": 1,
        "hidden_size": 16,
    },
    "local": {
        "train_games": 200,
        "eval_games": 100,
        "mixed_seat_games": 20,
        "epochs": 8,
        "hidden_size": 64,
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MRN RL learning gate pipeline.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=20260507)
    parser.add_argument("--baseline-policy", default="heuristic_v3_engine")
    parser.add_argument("--train-games", type=int)
    parser.add_argument("--eval-games", type=int)
    parser.add_argument("--mixed-seat-games", type=int)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--hidden-size", type=int)
    args = parser.parse_args(argv)

    config = dict(PROFILES[args.profile])
    for key in ["train_games", "eval_games", "mixed_seat_games", "epochs", "hidden_size"]:
        override = getattr(args, key)
        if override is not None:
            config[key] = override

    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "tmp" / "rl" / args.profile
    summary = run_gate_pipeline(
        output_dir=output_dir,
        seed=args.seed,
        baseline_policy=args.baseline_policy,
        **config,
    )
    accepted = bool(summary["comparison"]["accepted"])
    checks = summary["comparison"]["checks"]
    stable = all(
        bool(checks.get(check_name))
        for check_name in [
            "baseline_runtime_failed_zero",
            "candidate_runtime_failed_zero",
            "candidate_illegal_action_zero",
            "candidate_timeout_zero",
        ]
    )
    print(
        json.dumps(
            {
                "accepted": accepted,
                "stable": stable,
                "profile": args.profile,
                "output_dir": str(output_dir),
                "summary": summary["comparison"],
                "diagnostics_path": summary["diagnostics_path"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if args.profile == "smoke":
        return 0 if stable else 1
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
