from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

import argparse, json
from pathlib import Path
from simulate_with_logs import run as run_sim

BASE = ["cash_focus", "shard_focus", "coin_focus", "heuristic_v1"]


def rotate(lst, n):
    n %= len(lst)
    return lst[n:] + lst[:n]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulations-per-rotation", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", type=str, default="mixed_lap_policy_output")
    ap.add_argument("--starting-cash", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    aggregate = {mode: {"appearances": 0.0, "win_share": 0.0, "outright_wins": 0.0, "score_sum": 0.0, "cash_sum": 0.0, "placed_sum": 0.0, "shards_sum": 0.0} for mode in BASE}
    rotations = []
    for idx in range(4):
        lineup = rotate(BASE, idx)
        rot_dir = root / f"rotation_{idx+1}"
        run_sim(args.simulations_per_rotation, args.seed + idx, str(rot_dir), policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1", player_lap_policy_modes={1: lineup[0], 2: lineup[1], 3: lineup[2], 4: lineup[3]}, starting_cash=args.starting_cash)
        summ = load_json(rot_dir / "summary.json")
        rotations.append({"rotation": idx + 1, "lineup": lineup, "summary": summ})
        for mode, vals in summ.get("lap_policy_stats", {}).items():
            agg = aggregate[mode]
            for k in ["appearances", "win_share", "outright_wins"]:
                agg[k] += vals.get(k, 0.0)
            for src, dst in [("avg_score", "score_sum"), ("avg_cash", "cash_sum"), ("avg_placed", "placed_sum"), ("avg_shards", "shards_sum")]:
                agg[dst] += vals.get(src, 0.0) * vals.get("appearances", 0.0)

    out = {"rotations": [{"rotation": r["rotation"], "lineup": r["lineup"], "avg_total_turns": r["summary"].get("avg_total_turns", 0.0), "avg_final_f_value": r["summary"].get("avg_final_f_value", 0.0), "end_reasons": r["summary"].get("end_reasons", {})} for r in rotations], "policy_win_rates": {}}
    for mode, vals in aggregate.items():
        app = vals["appearances"]
        out["policy_win_rates"][mode] = {
            "appearances": app,
            "win_share": vals["win_share"],
            "win_share_rate": (vals["win_share"] / app) if app else 0.0,
            "outright_wins": vals["outright_wins"],
            "outright_win_rate": (vals["outright_wins"] / app) if app else 0.0,
            "avg_score": (vals["score_sum"] / app) if app else 0.0,
            "avg_cash": (vals["cash_sum"] / app) if app else 0.0,
            "avg_placed": (vals["placed_sum"] / app) if app else 0.0,
            "avg_shards": (vals["shards_sum"] / app) if app else 0.0,
        }
    (root / "mixed_lap_policy_comparison.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
