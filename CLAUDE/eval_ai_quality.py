"""Phase 1-B: CLAUDE AI Quality Evaluation Script.

Measures:
- Arena: win rates for 4 different profiles in same game (seat-fixed)
- Head-to-head: v3_claude (seat 0) vs v1 (seats 1-3)
- Profile survey: self-play stats per profile (avg turns, bankruptcies, tricks, mark success)

Usage:
    python eval_ai_quality.py [--seeds N] [--save] [--mode all|arena|h2h|survey]
"""
from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import random
from pathlib import Path

from config import DEFAULT_CONFIG
from engine import GameEngine
from ai_policy import HeuristicPolicy, ArenaPolicy


SURVEY_PROFILES = ["heuristic_v1", "heuristic_v2_balanced", "heuristic_v2_v3_claude"]

ARENA_LINEUP = [
    "heuristic_v2_aggressive",
    "heuristic_v2_token_opt",
    "heuristic_v2_control",
    "heuristic_v2_balanced",
]


def run_arena_battle(seeds: list[int]) -> dict:
    """Arena: 4 different profiles in same game (seat-fixed)."""
    # Seats: P1=aggressive, P2=token_opt, P3=control, P4=balanced (1-indexed)
    lineup = {
        1: "heuristic_v2_aggressive",
        2: "heuristic_v2_token_opt",
        3: "heuristic_v2_control",
        4: "heuristic_v2_balanced",
    }
    # profile name -> win count
    win_counts: dict[str, int] = {profile: 0 for profile in lineup.values()}
    total_turns = 0
    total_bankrupt = 0
    n = len(seeds)

    for seed in seeds:
        rng = random.Random(seed)
        policy = ArenaPolicy(player_character_policy_modes=lineup)
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=rng)
        result = engine.run()
        total_turns += result.total_turns
        total_bankrupt += result.bankrupt_players
        # winner_ids are 0-indexed; lineup keys are 1-indexed
        for winner_id in result.winner_ids:
            player_seat_1indexed = winner_id + 1
            if player_seat_1indexed in lineup:
                win_counts[lineup[player_seat_1indexed]] += 1

    win_rates = {profile: win_counts[profile] / n for profile in win_counts}

    return {
        "mode": "arena",
        "games": n,
        "win_rates": win_rates,
        "avg_total_turns": total_turns / n,
        "avg_bankrupt_per_game": total_bankrupt / n,
    }


def run_headtohead(
    seeds: list[int],
    challenger: str = "heuristic_v2_v3_claude",
    baseline: str = "heuristic_v1",
) -> dict:
    """Head-to-head: challenger (seat 0) vs baseline (seats 1-3)."""
    # ArenaPolicy uses 1-indexed seats
    lineup = {
        1: challenger,
        2: baseline,
        3: baseline,
        4: baseline,
    }
    challenger_wins = 0
    baseline_wins = 0
    challenger_tricks_per_turn_sum = 0.0
    challenger_mark_success_rate_sum = 0.0
    n = len(seeds)

    for seed in seeds:
        rng = random.Random(seed)
        policy = ArenaPolicy(player_character_policy_modes=lineup)
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=rng)
        result = engine.run()

        # Check winners (0-indexed). Seat 0 = player_id 0 = challenger
        for winner_id in result.winner_ids:
            if winner_id == 0:
                challenger_wins += 1
            else:
                baseline_wins += 1

        # strategy_summary[0] is seat 0 = challenger
        if result.strategy_summary:
            ss = result.strategy_summary[0]
            turns_taken = ss.get("turns_taken", 0)
            tricks_used = ss.get("tricks_used", 0)
            if turns_taken > 0:
                challenger_tricks_per_turn_sum += tricks_used / turns_taken
            challenger_mark_success_rate_sum += ss.get("mark_success_rate", 0.0)

    return {
        "mode": "h2h",
        "challenger": challenger,
        "baseline": baseline,
        "games": n,
        "challenger_win_rate": challenger_wins / n,
        "baseline_combined_win_rate": baseline_wins / n,
        "challenger_avg_tricks_per_turn": challenger_tricks_per_turn_sum / n,
        "challenger_avg_mark_success_rate": challenger_mark_success_rate_sum / n,
    }


def run_profile_survey(profiles: list[str], seeds: list[int]) -> list[dict]:
    """Self-play stats per profile (4 players all same profile)."""
    results = []
    n = len(seeds)

    for profile in profiles:
        total_turns = 0
        total_bankrupt = 0
        tricks_per_player_per_turn_sum = 0.0
        mark_success_rate_sum = 0.0
        player_count_total = 0

        for seed in seeds:
            rng = random.Random(seed)
            policy = HeuristicPolicy(
                character_policy_mode=profile,
                lap_policy_mode="heuristic_v1",
            )
            engine = GameEngine(DEFAULT_CONFIG, policy, rng=rng)
            result = engine.run()
            total_turns += result.total_turns
            total_bankrupt += result.bankrupt_players

            for ss in result.strategy_summary:
                turns_taken = ss.get("turns_taken", 0)
                tricks_used = ss.get("tricks_used", 0)
                if turns_taken > 0:
                    tricks_per_player_per_turn_sum += tricks_used / turns_taken
                mark_success_rate_sum += ss.get("mark_success_rate", 0.0)
                player_count_total += 1

        avg_mark_success_rate = (
            mark_success_rate_sum / player_count_total
            if player_count_total > 0
            else 0.0
        )
        avg_tricks_per_player_per_turn = (
            tricks_per_player_per_turn_sum / player_count_total
            if player_count_total > 0
            else 0.0
        )

        results.append({
            "profile": profile,
            "games": n,
            "avg_total_turns": total_turns / n,
            "avg_bankrupt_per_game": total_bankrupt / n,
            "avg_tricks_per_player_per_turn": avg_tricks_per_player_per_turn,
            "avg_mark_success_rate": avg_mark_success_rate,
        })

    return results


def _print_arena(data: dict) -> None:
    print("\n=== Arena Battle Results ===")
    print(f"Games: {data['games']}")
    print(f"Avg total turns: {data['avg_total_turns']:.1f}")
    print(f"Avg bankrupt/game: {data['avg_bankrupt_per_game']:.2f}")
    print("\nWin Rates:")
    for profile, rate in data["win_rates"].items():
        print(f"  {profile:<35} {rate*100:6.1f}%")


def _print_h2h(data: dict) -> None:
    print("\n=== Head-to-Head Results ===")
    print(f"Challenger: {data['challenger']}")
    print(f"Baseline:   {data['baseline']}")
    print(f"Games: {data['games']}")
    print(f"Challenger win rate:          {data['challenger_win_rate']*100:6.1f}%")
    print(f"Baseline combined win rate:   {data['baseline_combined_win_rate']*100:6.1f}%")
    print(f"Challenger avg tricks/turn:   {data['challenger_avg_tricks_per_turn']:.4f}")
    print(f"Challenger avg mark success:  {data['challenger_avg_mark_success_rate']:.4f}")


def _print_survey(data: list[dict]) -> None:
    print("\n=== Profile Survey Results ===")
    header = f"{'Profile':<35} {'Games':>5} {'AvgTurns':>9} {'AvgBankrupt':>11} {'Tricks/PT':>10} {'MarkSucc':>9}"
    print(header)
    print("-" * len(header))
    for row in data:
        print(
            f"{row['profile']:<35} "
            f"{row['games']:>5} "
            f"{row['avg_total_turns']:>9.1f} "
            f"{row['avg_bankrupt_per_game']:>11.2f} "
            f"{row['avg_tricks_per_player_per_turn']:>10.4f} "
            f"{row['avg_mark_success_rate']:>9.4f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1-B: CLAUDE AI Quality Evaluation")
    ap.add_argument("--seeds", type=int, default=50, help="Number of seeds (default: 50)")
    ap.add_argument("--save", action="store_true", help="Save results as JSON to eval_baselines/")
    ap.add_argument(
        "--mode",
        choices=["all", "arena", "h2h", "survey"],
        default="all",
        help="Evaluation mode (default: all)",
    )
    args = ap.parse_args()

    seeds = list(range(args.seeds))
    output: dict = {}

    if args.mode in ("all", "arena"):
        print(f"Running arena battle ({args.seeds} seeds)...", flush=True)
        arena_result = run_arena_battle(seeds)
        output["arena"] = arena_result
        _print_arena(arena_result)

    if args.mode in ("all", "h2h"):
        print(f"\nRunning head-to-head ({args.seeds} seeds)...", flush=True)
        h2h_result = run_headtohead(seeds)
        output["h2h"] = h2h_result
        _print_h2h(h2h_result)

    if args.mode in ("all", "survey"):
        print(f"\nRunning profile survey ({args.seeds} seeds)...", flush=True)
        survey_result = run_profile_survey(SURVEY_PROFILES, seeds)
        output["survey"] = survey_result
        _print_survey(survey_result)

    if args.save:
        save_dir = Path(__file__).parent / "eval_baselines"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"baseline_s{args.seeds}.json"
        save_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved to {save_path}")


if __name__ == "__main__":
    main()
