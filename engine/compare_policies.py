from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulate_with_logs import run as run_sim
from text_encoding import configure_utf8_io


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compare(random_summary: dict, heuristic_summary: dict) -> dict:
    out = {
        "version": heuristic_summary.get("version") or random_summary.get("version"),
        "games": heuristic_summary.get("games", 0),
        "policies": {
            "random": random_summary,
            "heuristic_v1": heuristic_summary,
        },
        "deltas": {},
    }
    keys = ["avg_total_turns", "avg_rounds", "avg_final_f_value", "avg_final_shards_per_player", "avg_shard_income_per_player", "avg_tricks_used_per_player", "avg_total_placed_coins", "bankrupt_any_rate", "tie_rate"]
    for key in keys:
        if key in random_summary and key in heuristic_summary:
            out["deltas"][key] = heuristic_summary[key] - random_summary[key]

    basic_delta = {}
    for block in ["winner_avg", "non_winner_avg", "winner_strategy_avg", "non_winner_strategy_avg"]:
        rblock = random_summary.get("basic_stats", {}).get(block, {})
        hblock = heuristic_summary.get("basic_stats", {}).get(block, {})
        keys = sorted(set(rblock) | set(hblock))
        basic_delta[block] = {k: hblock.get(k, 0.0) - rblock.get(k, 0.0) for k in keys}
    out["basic_stats_delta"] = basic_delta
    return out


def main():
    configure_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulations", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", type=str, default="policy_compare_output")
    args = ap.parse_args()

    root = Path(args.output_dir)
    random_dir = root / "random"
    heuristic_dir = root / "heuristic_v1"
    root.mkdir(parents=True, exist_ok=True)

    run_sim(args.simulations, args.seed, str(random_dir), policy_mode="random")
    run_sim(args.simulations, args.seed, str(heuristic_dir), policy_mode="heuristic_v1")

    random_summary = load_json(random_dir / "summary.json")
    heuristic_summary = load_json(heuristic_dir / "summary.json")
    comparison = compare(random_summary, heuristic_summary)
    (root / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
