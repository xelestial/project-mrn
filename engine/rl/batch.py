from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rl.replay import iter_replay_rows
from simulate_with_logs import run as simulate_run


def run_replay_batch(
    *,
    simulations: int,
    seed: int,
    output_dir: str | Path,
    policy_mode: str = "arena",
    lap_policy_mode: str = "heuristic_v3_engine",
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    replay_path = out / "rl_replay.jsonl"

    summary = simulate_run(
        simulations=simulations,
        seed=seed,
        output_dir=str(out),
        log_level="none",
        policy_mode=policy_mode,
        lap_policy_mode=lap_policy_mode,
        emit_summary=False,
        emit_rl_replay=True,
        rl_replay_path=str(replay_path),
    )
    errors_path = out / "errors.jsonl"
    failed_games = 0
    if errors_path.exists():
        failed_games = sum(1 for line in errors_path.read_text(encoding="utf-8").splitlines() if line.strip())
    replay_rows = sum(1 for _ in iter_replay_rows(replay_path)) if replay_path.exists() else 0
    manifest = {
        "simulations": simulations,
        "seed": seed,
        "policy_mode": policy_mode,
        "lap_policy_mode": lap_policy_mode,
        "replay_path": str(replay_path),
        "replay_rows": replay_rows,
        "failed_games": failed_games,
        "summary": summary,
    }
    (out / "rl_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
