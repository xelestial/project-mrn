from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

import argparse, json
from pathlib import Path
from simulate_with_logs import run as run_sim

LAP_MODES = ["cash_focus", "shard_focus", "coin_focus", "balanced", "heuristic_v1"]


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def summarize(summary: dict) -> dict:
    return {
        "games": summary.get("games", 0),
        "lap_policy_mode": summary.get("lap_policy_mode"),
        "end_reasons": summary.get("end_reasons", {}),
        "avg_total_turns": summary.get("avg_total_turns", 0.0),
        "avg_final_f_value": summary.get("avg_final_f_value", 0.0),
        "avg_total_placed_coins": summary.get("avg_total_placed_coins", 0.0),
        "avg_tricks_used_per_player": summary.get("avg_tricks_used_per_player", 0.0),
        "avg_final_shards_per_player": summary.get("avg_final_shards_per_player", 0.0),
        "avg_shard_income_per_player": summary.get("avg_shard_income_per_player", 0.0),
        "lap_choice_counts": summary.get("lap_choice_counts", {}),
        "lap_choice_rates": summary.get("lap_choice_rates", {}),
        "winner_avg": summary.get("basic_stats", {}).get("winner_avg", {}),
        "winner_strategy_avg": summary.get("basic_stats", {}).get("winner_strategy_avg", {}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulations', type=int, default=100)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--output-dir', type=str, default='lap_policy_compare_output')
    ap.add_argument('--starting-cash', type=int, default=None)
    args = ap.parse_args()
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    out = {"modes": {}}
    for mode in LAP_MODES:
        mode_dir = root / mode
        # starting cash override via env-free patchless route: edit default config in-process not supported here.
        run_sim(args.simulations, args.seed, str(mode_dir), policy_mode='heuristic_v1', lap_policy_mode=mode)
        summ = load_json(mode_dir / 'summary.json')
        out['modes'][mode] = summarize(summ)
    (root / 'lap_policy_comparison.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
