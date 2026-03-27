from __future__ import annotations

import argparse
import copy
import json
import random
import traceback
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from ai_policy import ArenaPolicy, HeuristicPolicy
from board_layout_creator import load_board_config
from config import DEFAULT_CONFIG
from doc_integrity import summarize_integrity
from engine import GameEngine
from metadata import GAME_VERSION
from game_rules_loader import load_ruleset
from stats_utils import compute_basic_stats_from_games
from text_encoding import configure_utf8_io


@lru_cache(maxsize=1)
def _cached_integrity_summary() -> dict:
    return summarize_integrity()


def _integrity_summary() -> dict:
    return dict(_cached_integrity_summary())


def result_to_dict(result, log_level: str = "summary", integrity: dict | None = None):
    integrity = dict(integrity or _integrity_summary())
    payload = {
        "version": GAME_VERSION,
        "doc_integrity_ok": integrity["ok"],
        "checked_pairs": integrity["checked_pairs"],
        "winner_ids": [w + 1 for w in result.winner_ids],
        "end_reason": result.end_reason,
        "total_turns": result.total_turns,
        "rounds_completed": result.rounds_completed,
        "alive_count": result.alive_count,
        "bankrupt_players": result.bankrupt_players,
        "final_f_value": result.final_f_value,
        "total_placed_coins": result.total_placed_coins,
        "player_summary": result.player_summary,
        "strategy_summary": result.strategy_summary,
        "weather_history": list(result.weather_history),
        "bankruptcy_events": list(result.bankruptcy_events),
    }
    if log_level == "full":
        payload["action_log"] = result.action_log
    return payload


class RunningSummary:
    def __init__(
        self,
        policy_mode: str,
        lap_policy_mode: str = "heuristic_v1",
        player_lap_policy_modes: dict[int, str] | None = None,
        player_character_policy_modes: dict[int, str] | None = None,
        integrity: dict | None = None,
    ) -> None:
        self.policy_mode = policy_mode
        self.lap_policy_mode = lap_policy_mode
        self.player_lap_policy_modes = dict(player_lap_policy_modes or {})
        self.player_character_policy_modes = dict(player_character_policy_modes or {})
        self.integrity = dict(integrity or _integrity_summary())
        self.games = 0
        self.end_reasons = Counter()
        self.bankrupt_any = 0
        self.total_turns: list[int] = []
        self.rounds: list[int] = []
        self.total_placed_coins: list[int] = []
        self.final_f: list[float] = []
        self.character_choice_counts = Counter()
        self.final_shards_per_player: list[float] = []
        self.shard_income_per_player: list[float] = []
        self.tricks_used_per_player: list[float] = []
        self.lap_choice_counts = Counter()
        self.weather_counts = Counter()
        self.weather_game_presence = Counter()
        self.tied = 0
        self.win_counter = Counter()
        self.bankruptcy_cause_counts = Counter()
        self.bankruptcy_tile_kind_counts = Counter()
        self.players = defaultdict(lambda: defaultdict(float))
        self.policy_stats = defaultdict(
            lambda: {
                "appearances": 0.0,
                "win_share": 0.0,
                "outright_wins": 0.0,
                "score_sum": 0.0,
                "cash_sum": 0.0,
                "placed_sum": 0.0,
                "shards_sum": 0.0,
            }
        )
        self.character_policy_stats = defaultdict(
            lambda: {
                "appearances": 0.0,
                "win_share": 0.0,
                "outright_wins": 0.0,
                "score_sum": 0.0,
                "cash_sum": 0.0,
                "placed_sum": 0.0,
                "shards_sum": 0.0,
            }
        )
        self.game_records: list[dict] = []

    @staticmethod
    def _aggregate_policy_stats(source: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        return {
            mode: {
                "appearances": vals["appearances"],
                "win_share": vals["win_share"],
                "win_share_rate": (vals["win_share"] / vals["appearances"]) if vals["appearances"] else 0.0,
                "outright_wins": vals["outright_wins"],
                "outright_win_rate": (vals["outright_wins"] / vals["appearances"]) if vals["appearances"] else 0.0,
                "avg_score": (vals["score_sum"] / vals["appearances"]) if vals["appearances"] else 0.0,
                "avg_cash": (vals["cash_sum"] / vals["appearances"]) if vals["appearances"] else 0.0,
                "avg_placed": (vals["placed_sum"] / vals["appearances"]) if vals["appearances"] else 0.0,
                "avg_shards": (vals["shards_sum"] / vals["appearances"]) if vals["appearances"] else 0.0,
            }
            for mode, vals in source.items()
        }

    @staticmethod
    def _safe_mean(values: Iterable[float]) -> float:
        vals = list(values)
        return mean(vals) if vals else 0.0

    def _reliability_summary(self) -> dict:
        game_seeds = [g.get("game_seed") for g in self.game_records if g.get("game_seed") is not None]
        global_indices = [g.get("global_game_index") for g in self.game_records if g.get("global_game_index") is not None]
        run_chunk_pairs = [
            (g.get("run_id"), g.get("chunk_id"), g.get("chunk_game_id"))
            for g in self.game_records
            if g.get("run_id") is not None and g.get("chunk_id") is not None and g.get("chunk_game_id") is not None
        ]
        game_seed_counts = Counter(game_seeds)
        global_index_counts = Counter(global_indices)
        run_chunk_counts = Counter(run_chunk_pairs)
        return {
            "missing_character_summary_rows": int(sum(1 for g in self.game_records for p in g.get("player_summary", []) if not p.get("character"))),
            "missing_strategy_character_rows": int(sum(1 for g in self.game_records for s in g.get("strategy_summary", []) if not (s.get("character") or s.get("last_selected_character") or s.get("character_choice_counts")))),
            "null_numeric_fields": sorted({
                field
                for g in self.game_records
                for p in g.get("player_summary", [])
                for field in ("cash", "tiles_owned", "placed_score_coins", "hand_coins", "score", "turns_taken", "shards")
                if p.get(field) is None
            }),
            "unique_game_seed_count": len(game_seed_counts),
            "duplicate_game_seed_count": int(sum(1 for _, count in game_seed_counts.items() if count > 1)),
            "duplicate_game_seed_instances": int(sum(count - 1 for count in game_seed_counts.values() if count > 1)),
            "unique_global_game_index_count": len(global_index_counts),
            "duplicate_global_game_index_count": int(sum(1 for _, count in global_index_counts.items() if count > 1)),
            "duplicate_global_game_index_instances": int(sum(count - 1 for count in global_index_counts.values() if count > 1)),
            "duplicate_run_chunk_game_count": int(sum(1 for _, count in run_chunk_counts.items() if count > 1)),
            "duplicate_run_chunk_game_instances": int(sum(count - 1 for count in run_chunk_counts.values() if count > 1)),
        }

    def _base_summary(self, basic_stats: dict) -> dict:
        return {
            "version": GAME_VERSION,
            "doc_integrity_ok": self.integrity["ok"],
            "checked_pairs": self.integrity["checked_pairs"],
            "policy_mode": self.policy_mode,
            "lap_policy_mode": self.lap_policy_mode,
            "player_lap_policy_modes": {str(k): v for k, v in self.player_lap_policy_modes.items()},
            "player_character_policy_modes": {str(k): v for k, v in self.player_character_policy_modes.items()},
            "games": self.games,
            "end_reasons": dict(self.end_reasons),
            "weather_counts": dict(self.weather_counts),
            "weather_game_presence": dict(self.weather_game_presence),
            "basic_stats": basic_stats,
            "reliability": self._reliability_summary(),
        }

    def update(self, g: dict) -> None:
        self.games += 1
        self.game_records.append(g)
        self.end_reasons[g["end_reason"]] += 1
        if g["bankrupt_players"] > 0:
            self.bankrupt_any += 1
        self.total_turns.append(g["total_turns"])
        self.rounds.append(g["rounds_completed"])
        self.total_placed_coins.append(g["total_placed_coins"])
        self.final_f.append(g["final_f_value"])

        weather_history = list(g.get("weather_history", []))
        self.weather_counts.update(weather_history)
        self.weather_game_presence.update(set(weather_history))

        if g.get("player_summary"):
            self.final_shards_per_player.append(sum(p.get("shards", 0) for p in g["player_summary"]) / len(g["player_summary"]))
        if g.get("strategy_summary"):
            self.shard_income_per_player.append(sum(s.get("shard_income_cash", 0) for s in g["strategy_summary"]) / len(g["strategy_summary"]))
            self.tricks_used_per_player.append(sum(s.get("tricks_used", 0) for s in g["strategy_summary"]) / len(g["strategy_summary"]))
            self.lap_choice_counts["cash"] += sum(s.get("lap_cash_choices", 0) for s in g["strategy_summary"])
            self.lap_choice_counts["coins"] += sum(s.get("lap_coin_choices", 0) for s in g["strategy_summary"])
            self.lap_choice_counts["shards"] += sum(s.get("lap_shard_choices", 0) for s in g["strategy_summary"])
            for strat in g["strategy_summary"]:
                counts = strat.get("character_choice_counts") or {}
                if counts:
                    self.character_choice_counts.update(counts)
                elif strat.get("character"):
                    self.character_choice_counts[strat["character"]] += 1
        for evt in g.get("bankruptcy_events", []):
            self.bankruptcy_cause_counts[evt.get("cause_hint") or "unknown"] += 1
            self.bankruptcy_tile_kind_counts[evt.get("tile_kind") or "unknown"] += 1
        if len(g["winner_ids"]) > 1:
            self.tied += 1
        else:
            self.win_counter[g["winner_ids"][0]] += 1

        player_policy_modes = g.get("player_lap_policy_modes", {})
        player_character_modes = g.get("player_character_policy_modes", {})
        winner_ids = g.get("winner_ids", [])
        win_share = 1.0 / len(winner_ids) if winner_ids else 0.0
        for p in g["player_summary"]:
            pid = str(p["player_id"] + 1)
            self.players[pid]["count"] += 1
            self.players[pid]["cash"] += p["cash"]
            self.players[pid]["tiles"] += p["tiles_owned"]
            self.players[pid]["placed"] += p["placed_score_coins"]
            self.players[pid]["hand"] += p["hand_coins"]
            self.players[pid]["score"] += p["score"]
            self.players[pid]["turns"] += p["turns_taken"]
            self.players[pid]["shards"] += p.get("shards", 0)

            policy_name = player_policy_modes.get(str(p["player_id"] + 1), self.player_lap_policy_modes.get(p["player_id"] + 1, self.lap_policy_mode))
            ps = self.policy_stats[policy_name]
            ps["appearances"] += 1.0
            ps["score_sum"] += p.get("score", 0)
            ps["cash_sum"] += p.get("cash", 0)
            ps["placed_sum"] += p.get("placed_score_coins", 0)
            ps["shards_sum"] += p.get("shards", 0)

            character_policy_name = player_character_modes.get(str(p["player_id"] + 1), self.player_character_policy_modes.get(p["player_id"] + 1, self.policy_mode))
            cps = self.character_policy_stats[character_policy_name]
            cps["appearances"] += 1.0
            cps["score_sum"] += p.get("score", 0)
            cps["cash_sum"] += p.get("cash", 0)
            cps["placed_sum"] += p.get("placed_score_coins", 0)
            cps["shards_sum"] += p.get("shards", 0)
            if (p["player_id"] + 1) in winner_ids:
                ps["win_share"] += win_share
                cps["win_share"] += win_share
                if len(winner_ids) == 1:
                    ps["outright_wins"] += 1.0
                    cps["outright_wins"] += 1.0

    def to_dict(self) -> dict:
        basic_stats = compute_basic_stats_from_games(self.game_records)
        summary = self._base_summary(basic_stats)
        if self.games == 0:
            summary.update(
                {
                    "bankrupt_any_rate": 0.0,
                    "avg_total_turns": 0.0,
                    "median_total_turns": 0.0,
                    "avg_rounds": 0.0,
                    "avg_actions_per_player": 0.0,
                    "avg_final_f_value": 0.0,
                    "avg_final_shards_per_player": 0.0,
                    "avg_shard_income_per_player": 0.0,
                    "avg_tricks_used_per_player": 0.0,
                    "avg_weather_rounds_per_game": 0.0,
                    "lap_choice_counts": {"cash": 0, "coins": 0, "shards": 0},
                    "lap_choice_rates": {"cash": 0.0, "coins": 0.0, "shards": 0.0},
                    "character_choice_counts": {},
                    "avg_total_placed_coins": 0.0,
                    "avg_first_place_laps_completed": 0.0,
                    "avg_first_place_lap_rewards_received": 0.0,
                    "total_mark_attempts": 0,
                    "total_mark_successes": 0,
                    "mark_success_rate": 0.0,
                    "tie_rate": 0.0,
                    "wins": {str(i): 0.0 for i in range(1, 5)},
                    "lap_policy_stats": {},
                    "character_policy_stats": {},
                    "players": {},
                }
            )
            return summary

        lap_total = sum(self.lap_choice_counts.values())
        summary.update(
            {
                "bankrupt_any_rate": self.bankrupt_any / self.games,
                "avg_total_turns": mean(self.total_turns),
                "median_total_turns": median(self.total_turns),
                "avg_rounds": mean(self.rounds),
                "avg_actions_per_player": mean(self.total_turns) / 4.0,
                "avg_final_f_value": mean(self.final_f),
                "avg_final_shards_per_player": self._safe_mean(self.final_shards_per_player),
                "avg_shard_income_per_player": self._safe_mean(self.shard_income_per_player),
                "avg_tricks_used_per_player": self._safe_mean(self.tricks_used_per_player),
                "avg_weather_rounds_per_game": sum(self.weather_counts.values()) / self.games,
                "lap_choice_counts": dict(self.lap_choice_counts),
                "lap_choice_rates": (
                    {k: (self.lap_choice_counts[k] / lap_total) for k in ["cash", "coins", "shards"]}
                    if lap_total > 0
                    else {"cash": 0.0, "coins": 0.0, "shards": 0.0}
                ),
                "avg_total_placed_coins": mean(self.total_placed_coins),
                "avg_first_place_laps_completed": basic_stats["first_place_laps_completed_avg"],
                "avg_first_place_lap_rewards_received": basic_stats["first_place_lap_reward_avg"],
                "total_mark_attempts": basic_stats["total_mark_attempts"],
                "total_mark_successes": basic_stats["total_mark_successes"],
                "mark_success_rate": basic_stats["mark_success_rate"],
                "tie_rate": self.tied / self.games,
                "wins": {str(i): self.win_counter[i] / self.games for i in range(1, 5)},
                "bankruptcy_cause_counts": dict(self.bankruptcy_cause_counts),
                "bankruptcy_tile_kind_counts": dict(self.bankruptcy_tile_kind_counts),
                "lap_policy_stats": self._aggregate_policy_stats(self.policy_stats),
                "character_policy_stats": self._aggregate_policy_stats(self.character_policy_stats),
                "players": {
                    pid: {
                        "avg_cash": vals["cash"] / vals["count"],
                        "avg_tiles": vals["tiles"] / vals["count"],
                        "avg_placed": vals["placed"] / vals["count"],
                        "avg_hand": vals["hand"] / vals["count"],
                        "avg_shards": vals["shards"] / vals["count"],
                        "avg_score": vals["score"] / vals["count"],
                        "avg_turns": vals["turns"] / vals["count"],
                    }
                    for pid, vals in self.players.items()
                },
            }
        )
        return summary


def parse_player_lap_policy_modes(spec: str | None) -> dict[int, str]:
    if not spec:
        return {}
    parts = [p.strip() for p in spec.split(',') if p.strip()]
    if len(parts) != 4:
        raise ValueError("player-lap-policies must contain exactly 4 comma-separated modes")
    for mode in parts:
        if mode not in HeuristicPolicy.VALID_LAP_POLICIES:
            raise ValueError(f"Unsupported player lap policy: {mode}")
    return {i + 1: parts[i] for i in range(4)}


def parse_player_character_policy_modes(spec: str | None) -> dict[int, str]:
    if not spec:
        return {}
    parts = [p.strip() for p in spec.split(',') if p.strip()]
    if len(parts) != 4:
        raise ValueError("player-character-policies must contain exactly 4 comma-separated modes")
    for mode in parts:
        if mode not in HeuristicPolicy.VALID_CHARACTER_POLICIES or mode == "arena":
            raise ValueError(f"Unsupported player character policy: {mode}")
    return {i + 1: parts[i] for i in range(4)}


def write_summary(out_dir: Path, running: RunningSummary, filename: str = "summary.json") -> dict:
    summary = running.to_dict()
    (out_dir / filename).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _runtime_config(starting_cash: int | None, board_layout_path: str | None = None, board_layout_meta_path: str | None = None, rule_scripts_path: str | None = None, ruleset_path: str | None = None):
    if starting_cash is None and not board_layout_path and not rule_scripts_path and ruleset_path is None:
        return DEFAULT_CONFIG
    game_config = copy.deepcopy(DEFAULT_CONFIG)
    if starting_cash is not None:
        game_config.economy.starting_cash = starting_cash
    if board_layout_path:
        game_config.board = load_board_config(board_layout_path, metadata_path=board_layout_meta_path)
    if rule_scripts_path is not None:
        game_config.rule_scripts_path = rule_scripts_path
    if ruleset_path is not None:
        game_config.ruleset_path = ruleset_path
        loaded_rules = load_ruleset(ruleset_path)
        if loaded_rules is not None:
            game_config.rules = loaded_rules
            game_config.rules.sync_to_legacy(game_config)
    profile_costs = {name: (rule.purchase_cost, rule.rent_cost) for name, rule in game_config.economy.tile_profile_costs.items()}
    game_config.economy.tile_rule_overrides = game_config.board.build_land_tile_rule_overrides(profile_costs)
    return game_config


def run(
    simulations: int,
    seed: int,
    output_dir: str,
    checkpoint_every: int = 100,
    flush_every: int = 1,
    log_level: str = "summary",
    full_log_every: int = 0,
    policy_mode: str = "arena",
    lap_policy_mode: str = "heuristic_v1",
    player_lap_policy_modes: dict[int, str] | None = None,
    player_character_policy_modes: dict[int, str] | None = None,
    starting_cash: int | None = None,
    board_layout_path: str | None = None,
    board_layout_meta_path: str | None = None,
    rule_scripts_path: str | None = None,
    ruleset_path: str | None = None,
    emit_summary: bool = True,
    run_id: str | None = None,
    root_seed: int | None = None,
    chunk_id: int | None = None,
    global_game_index_start: int = 0,
):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    effective_root_seed = seed if root_seed is None else root_seed
    effective_run_id = run_id or f"run_seed{effective_root_seed}_games{simulations}_{policy_mode}"
    player_lap_policy_modes = dict(player_lap_policy_modes or {})
    player_character_policy_modes = dict(player_character_policy_modes or {})
    integrity = _integrity_summary()
    if policy_mode == "arena":
        if not player_character_policy_modes:
            player_character_policy_modes = {1: "heuristic_v3_gpt", 2: "heuristic_v2_token_opt", 3: "heuristic_v2_control", 4: "heuristic_v2_balanced"}
        if not player_lap_policy_modes:
            player_lap_policy_modes = dict(player_character_policy_modes)
        policy = ArenaPolicy(player_character_policy_modes=player_character_policy_modes, player_lap_policy_modes=player_lap_policy_modes)
    else:
        policy = HeuristicPolicy(character_policy_mode=policy_mode, lap_policy_mode=lap_policy_mode, player_lap_policy_modes=player_lap_policy_modes)
    outer_rng = random.Random(seed)
    running = RunningSummary(
        policy_mode=policy_mode,
        lap_policy_mode=lap_policy_mode,
        player_lap_policy_modes=player_lap_policy_modes,
        player_character_policy_modes=player_character_policy_modes,
        integrity=integrity,
    )

    normalized_log_level = "summary" if log_level == "none" else log_level
    runtime_config = _runtime_config(starting_cash, board_layout_path, board_layout_meta_path, rule_scripts_path, ruleset_path)
    with (out / "games.jsonl").open("w", encoding="utf-8") as f, (out / "errors.jsonl").open("w", encoding="utf-8") as ef:
        for game_id in range(simulations):
            global_game_index = global_game_index_start + game_id
            game_seed = outer_rng.randrange(1 << 30)
            try:
                rng = random.Random(game_seed)
                want_full_log = normalized_log_level == "full" or (
                    normalized_log_level == "sampled" and full_log_every > 0 and ((game_id + 1) % full_log_every == 0)
                )
                engine = GameEngine(runtime_config, policy, rng=rng, enable_logging=want_full_log)
                per_game_log_level = "full" if want_full_log else "summary"
                result = result_to_dict(engine.run(), log_level=per_game_log_level, integrity=integrity)
                result["game_id"] = game_id
                result["chunk_game_id"] = game_id
                result["global_game_index"] = global_game_index
                result["run_id"] = effective_run_id
                result["root_seed"] = effective_root_seed
                result["chunk_seed"] = seed
                result["chunk_id"] = chunk_id
                result["game_seed"] = game_seed
                result["policy_mode"] = policy_mode
                result["lap_policy_mode"] = lap_policy_mode
                result["player_lap_policy_modes"] = {str(k): v for k, v in player_lap_policy_modes.items()}
                result["player_character_policy_modes"] = {str(k): v for k, v in player_character_policy_modes.items()}

                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                if flush_every > 0 and ((game_id + 1) % flush_every == 0):
                    f.flush()

                running.update(result)

                if checkpoint_every > 0 and ((game_id + 1) % checkpoint_every == 0):
                    write_summary(out, running, filename="summary.partial.json")
            except Exception as e:
                ef.write(json.dumps({
                    "game_id": game_id,
                    "chunk_game_id": game_id,
                    "global_game_index": global_game_index,
                    "run_id": effective_run_id,
                    "root_seed": effective_root_seed,
                    "chunk_seed": seed,
                    "chunk_id": chunk_id,
                    "game_seed": game_seed,
                    "error": repr(e),
                    "traceback": traceback.format_exc(),
                }, ensure_ascii=False) + "\n")
                ef.flush()
                raise

    summary = write_summary(out, running, filename="summary.json")
    if emit_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    configure_utf8_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulations", "--games", dest="simulations", type=int, default=1000, help="Number of games to simulate.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", type=str, default="analysis_output")
    ap.add_argument("--checkpoint-every", type=int, default=100)
    ap.add_argument("--flush-every", type=int, default=1)
    ap.add_argument("--log-level", choices=["summary", "full", "sampled", "none"], default="summary")
    ap.add_argument("--full-log-every", type=int, default=0)
    ap.add_argument("--policy-mode", choices=sorted(HeuristicPolicy.VALID_CHARACTER_POLICIES), default="arena")
    ap.add_argument("--lap-policy-mode", choices=sorted(HeuristicPolicy.VALID_LAP_POLICIES), default="heuristic_v3_gpt")
    ap.add_argument("--player-lap-policies", type=str, default="", help="comma-separated 4-player lap policies, e.g. cash_focus,shard_focus,coin_focus,heuristic_v1")
    ap.add_argument("--player-character-policies", type=str, default="", help="comma-separated 4-player character policies, e.g. heuristic_v1,heuristic_v2_token_opt,heuristic_v2_control,heuristic_v2_balanced")
    ap.add_argument("--starting-cash", type=int, default=None)
    ap.add_argument("--board-layout", type=str, default=None, help="Path to board layout JSON/CSV for metadata-driven map creation.")
    ap.add_argument("--board-layout-meta", type=str, default=None, help="Optional sidecar JSON metadata for CSV board layouts.")
    ap.add_argument("--rule-scripts", type=str, default=None, help="Optional JSON rule script overrides.")
    ap.add_argument("--ruleset", type=str, default=None, help="Optional JSON ruleset overrides for injected GameRules.")
    args = ap.parse_args()
    run(
        args.simulations,
        args.seed,
        args.output_dir,
        checkpoint_every=args.checkpoint_every,
        flush_every=args.flush_every,
        log_level=args.log_level,
        full_log_every=args.full_log_every,
        policy_mode=args.policy_mode,
        lap_policy_mode=args.lap_policy_mode,
        player_lap_policy_modes=parse_player_lap_policy_modes(args.player_lap_policies),
        player_character_policy_modes=parse_player_character_policy_modes(args.player_character_policies),
        starting_cash=args.starting_cash,
        board_layout_path=args.board_layout,
        board_layout_meta_path=args.board_layout_meta,
        rule_scripts_path=args.rule_scripts,
        ruleset_path=args.ruleset,
        emit_summary=True,
    )
