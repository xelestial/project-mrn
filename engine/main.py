from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from config import DEFAULT_CONFIG, GameConfig
from engine import GameEngine
from metadata import GAME_VERSION
from policy.factory import PolicyFactory
from stats_utils import compute_basic_stats_from_games
from text_encoding import configure_utf8_io


def summarize(results, policy_mode: str):
    end_reasons = Counter(r.end_reason for r in results)
    win_counter = Counter()
    tied_games = 0
    player_turns = defaultdict(list)
    player_cash = defaultdict(list)
    player_tiles = defaultdict(list)
    player_coins = defaultdict(list)
    player_scores = defaultdict(list)
    bankrupt_any = 0

    game_dicts = []
    for r in results:
        game_dict = {
            "version": GAME_VERSION,
            "winner_ids": [w + 1 for w in r.winner_ids],
            "end_reason": r.end_reason,
            "total_turns": r.total_turns,
            "rounds_completed": r.rounds_completed,
            "alive_count": r.alive_count,
            "bankrupt_players": r.bankrupt_players,
            "final_f_value": r.final_f_value,
            "total_placed_coins": r.total_placed_coins,
            "player_summary": r.player_summary,
            "strategy_summary": r.strategy_summary,
        }
        game_dicts.append(game_dict)
        if len(r.winner_ids) > 1:
            tied_games += 1
        else:
            win_counter[r.winner_ids[0]] += 1
        if r.bankrupt_players > 0:
            bankrupt_any += 1
        for p in r.player_summary:
            pid = p["player_id"]
            player_turns[pid].append(p["turns_taken"])
            player_cash[pid].append(p["cash"])
            player_tiles[pid].append(p["tiles_owned"])
            player_coins[pid].append(p["placed_score_coins"])
            player_scores[pid].append(p["score"])

    payload = {
        "version": GAME_VERSION,
        "policy_mode": policy_mode,
        "games": len(results),
        "end_reasons": dict(end_reasons),
        "bankrupt_any_rate": bankrupt_any / len(results) if results else 0.0,
        "avg_total_turns": mean(r.total_turns for r in results) if results else 0.0,
        "median_total_turns": median(r.total_turns for r in results) if results else 0.0,
        "avg_rounds_completed": mean(r.rounds_completed for r in results) if results else 0.0,
        "avg_final_f_value": mean(r.final_f_value for r in results) if results else 0.0,
        "avg_total_placed_coins": mean(r.total_placed_coins for r in results) if results else 0.0,
        "tie_rate": tied_games / len(results) if results else 0.0,
        "wins": {str(pid + 1): (win_counter[pid] / len(results) if results else 0.0) for pid in range(4)},
        "players": {},
        "basic_stats": compute_basic_stats_from_games(game_dicts),
    }

    for pid in range(4):
        payload["players"][str(pid + 1)] = {
            "avg_turns_taken": mean(player_turns[pid]) if player_turns[pid] else 0.0,
            "avg_cash": mean(player_cash[pid]) if player_cash[pid] else 0.0,
            "avg_tiles_owned": mean(player_tiles[pid]) if player_tiles[pid] else 0.0,
            "avg_placed_score_coins": mean(player_coins[pid]) if player_coins[pid] else 0.0,
            "avg_score": mean(player_scores[pid]) if player_scores[pid] else 0.0,
        }
    return payload


def run_batch(simulations: int = 1000, seed: int = 42, config: GameConfig | None = None, policy_mode: str = "heuristic_v3_engine"):
    rng = random.Random(seed)
    policy = PolicyFactory.create_runtime_policy(
        policy_mode=policy_mode,
        lap_policy_mode="heuristic_v3_engine",
    )
    runtime_config = config if config is not None else DEFAULT_CONFIG
    results = []
    for _ in range(simulations):
        engine = GameEngine(config=runtime_config, policy=policy, rng=random.Random(rng.randrange(1 << 30)))
        results.append(engine.run())
    return summarize(results, policy_mode=policy_mode)


def run_single_logged(seed: int = 42, config: GameConfig | None = None, policy_mode: str = "heuristic_v3_engine"):
    policy = PolicyFactory.create_runtime_policy(
        policy_mode=policy_mode,
        lap_policy_mode="heuristic_v3_engine",
    )
    runtime_config = config if config is not None else DEFAULT_CONFIG
    engine = GameEngine(config=runtime_config, policy=policy, rng=random.Random(seed), enable_logging=True)
    return engine.run()


def main(simulations: int = 1000, seed: int = 42, output_path: str | None = None, policy_mode: str = "heuristic_v3_engine"):
    configure_utf8_io()
    summary = run_batch(simulations=simulations, seed=seed, policy_mode=policy_mode)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(simulations=1000, seed=42, policy_mode="heuristic_v3_engine")
