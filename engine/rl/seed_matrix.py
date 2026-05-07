from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

from rl.replay import iter_replay_rows
from simulate_with_logs import run as simulate_run


def run_seed_matrix(
    *,
    seeds: Iterable[int],
    simulations_per_seed: int,
    output_dir: str | Path,
    policy_mode: str = "heuristic_v3_engine",
    model_dir: str | Path | None = None,
    lap_policy_mode: str = "heuristic_v3_engine",
    log_level: str = "none",
    emit_rl_replay: bool = False,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    seed_values = [int(seed) for seed in seeds]
    previous_model = os.environ.get("MRN_RL_POLICY_MODEL")
    if model_dir is not None:
        os.environ["MRN_RL_POLICY_MODEL"] = str(model_dir)
    try:
        results = [
            _run_one_seed(
                seed=seed,
                simulations=simulations_per_seed,
                output_dir=output_path,
                policy_mode=policy_mode,
                lap_policy_mode=lap_policy_mode,
                log_level=log_level,
                emit_rl_replay=emit_rl_replay,
            )
            for seed in seed_values
        ]
    finally:
        if previous_model is None:
            os.environ.pop("MRN_RL_POLICY_MODEL", None)
        else:
            os.environ["MRN_RL_POLICY_MODEL"] = previous_model
    matrix = {
        "policy_mode": policy_mode,
        "model_dir": str(model_dir) if model_dir is not None else None,
        "simulations_per_seed": int(simulations_per_seed),
        "seed_count": len(seed_values),
        "seeds": seed_values,
        "total_games": int(simulations_per_seed) * len(seed_values),
        "total_failed_games": sum(result["failed_games"] for result in results),
        "total_replay_rows": sum(result["replay_rows"] for result in results),
        "results": results,
    }
    (output_path / "seed_matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return matrix


def _run_one_seed(
    *,
    seed: int,
    simulations: int,
    output_dir: Path,
    policy_mode: str,
    lap_policy_mode: str,
    log_level: str,
    emit_rl_replay: bool,
) -> dict[str, Any]:
    seed_dir = output_dir / f"seed_{seed}"
    replay_path = seed_dir / "rl_replay.jsonl"
    summary = simulate_run(
        simulations=int(simulations),
        seed=int(seed),
        output_dir=str(seed_dir),
        log_level=log_level,
        policy_mode=policy_mode,
        lap_policy_mode=lap_policy_mode,
        emit_summary=False,
        emit_rl_replay=emit_rl_replay,
        rl_replay_path=str(replay_path),
    )
    failed_games = _count_jsonl(seed_dir / "errors.jsonl")
    replay_rows = sum(1 for _ in iter_replay_rows(replay_path)) if replay_path.exists() else 0
    return {
        "seed": int(seed),
        "games": int(simulations),
        "failed_games": failed_games,
        "replay_rows": replay_rows,
        "output_dir": str(seed_dir),
        "summary": summary,
    }


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _parse_seed_spec(spec: str) -> list[int]:
    if "-" in spec:
        start_raw, end_raw = spec.split("-", 1)
        start = int(start_raw)
        end = int(end_raw)
        step = 1 if end >= start else -1
        return list(range(start, end + step, step))
    return [int(part) for part in spec.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic policy simulations across a seed matrix.")
    parser.add_argument("--seeds", required=True, help="Comma list or inclusive range, e.g. 1,2,3 or 100-119")
    parser.add_argument("--simulations-per-seed", type=int, default=1)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--policy-mode", default="heuristic_v3_engine")
    parser.add_argument("--model-dir")
    parser.add_argument("--lap-policy-mode", default="heuristic_v3_engine")
    parser.add_argument("--log-level", default="none")
    parser.add_argument("--emit-rl-replay", action="store_true")
    args = parser.parse_args(argv)
    matrix = run_seed_matrix(
        seeds=_parse_seed_spec(args.seeds),
        simulations_per_seed=args.simulations_per_seed,
        output_dir=args.output_dir,
        policy_mode=args.policy_mode,
        model_dir=args.model_dir,
        lap_policy_mode=args.lap_policy_mode,
        log_level=args.log_level,
        emit_rl_replay=args.emit_rl_replay,
    )
    print(json.dumps({k: matrix[k] for k in ["policy_mode", "seed_count", "total_games", "total_failed_games"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
