from __future__ import annotations

import json
import random
import unittest
from pathlib import Path

from ai_policy import BasePolicy, HeuristicPolicy, LapRewardDecision
from config import DEFAULT_CONFIG, GameConfig
from engine import GameEngine
from state import GameState
from doc_integrity import summarize_integrity
from fortune_cards import build_fortune_deck
from metadata import GAME_VERSION
from simulate_with_logs import run as run_with_logs
from stats_utils import compute_basic_stats_from_games
from trick_cards import build_trick_deck
from weather_cards import build_weather_deck


class _ShardLapPolicy(BasePolicy):
    def choose_lap_reward(self, state, player):
        return LapRewardDecision(choice="shards")




class _TargetPolicy(BasePolicy):
    def __init__(self, target_name: str | None = None):
        self.target_name = target_name

    def choose_mark_target(self, state, player, actor_name):
        return self.target_name




def _first_block_lands(state):
    return state.block_tile_positions(1, land_only=True)


class ConfigSettingsTest(unittest.TestCase):
    def test_default_config_values(self) -> None:
        self.assertEqual(DEFAULT_CONFIG.shards.starting_shards, 4)
        self.assertEqual(DEFAULT_CONFIG.shards.lap_reward_shards, 3)
        self.assertEqual(DEFAULT_CONFIG.economy.starting_cash, 20)
        self.assertEqual(DEFAULT_CONFIG.coins.lap_reward_cash, 5)
        self.assertEqual(DEFAULT_CONFIG.coins.lap_reward_coins, 3)
        self.assertTrue(DEFAULT_CONFIG.coins.can_place_on_first_purchase)
        self.assertEqual(DEFAULT_CONFIG.board.f_end_value, 15.0)
        self.assertTrue(DEFAULT_CONFIG.characters.randomize_starting_active_by_card)
        self.assertIsNone(DEFAULT_CONFIG.end.tiles_to_trigger_end)
        self.assertEqual(DEFAULT_CONFIG.end.monopolies_to_trigger_end, 3)
        self.assertEqual(DEFAULT_CONFIG.end.higher_tiles_to_trigger_end, 9)
        board = DEFAULT_CONFIG.board.build_loop()
        first_f2 = board.index(DEFAULT_CONFIG.board.side_pattern[-1])
        side_land_positions = [pos for pos, kind in enumerate(board[:first_f2]) if kind in DEFAULT_CONFIG.economy.tile_rules]
        purchase_costs = [DEFAULT_CONFIG.economy.purchase_cost_for(board, pos) for pos in side_land_positions]
        rent_costs = [DEFAULT_CONFIG.economy.rent_cost_for(board, pos) for pos in side_land_positions]
        self.assertEqual(purchase_costs, [5, 5, 3, 4, 3, 5, 5])
        self.assertEqual(rent_costs, [5, 5, 3, 4, 3, 5, 5])
        malicious_costs = [DEFAULT_CONFIG.economy.malicious_cost_for(board, pos, DEFAULT_CONFIG.board.malicious_land_multiplier) for pos in side_land_positions]
        self.assertEqual(DEFAULT_CONFIG.board.malicious_land_multiplier, 3)
        self.assertEqual(malicious_costs, [15, 15, 9, 12, 9, 15, 15])
        state = GameState.create(GameConfig())
        first_tile = state.tile_at(side_land_positions[0])
        self.assertEqual(first_tile.purchase_cost, 5)
        self.assertEqual(first_tile.rent_cost, 5)
        self.assertEqual(first_tile.zone_color, state.block_color_map[first_tile.block_id])

    def test_players_start_with_updated_shards(self) -> None:
        state = GameState.create(GameConfig())
        self.assertEqual(len(state.players), 4)
        self.assertTrue(all(p.shards == 4 for p in state.players))

    def test_lap_reward_shards_uses_updated_value(self) -> None:
        config = GameConfig()
        state = GameState.create(config)
        player = state.players[0]
        player.current_character = "객주"
        engine = GameEngine(config, _ShardLapPolicy(), rng=random.Random(123), enable_logging=False)
        engine._strategy_stats = [
            {
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "shards_gained_lap": 0,
            }
            for _ in range(config.player_count)
        ]
        before = player.shards
        event = engine._apply_lap_reward(state, player)
        self.assertEqual(event["choice"], "shards")
        self.assertEqual(event["shards_delta"], 3)
        self.assertEqual(player.shards, before + 3)
        self.assertEqual(engine._strategy_stats[player.player_id]["lap_shard_choices"], 1)
        self.assertEqual(engine._strategy_stats[player.player_id]["shards_gained_lap"], 3)


    def test_build_result_tracks_lap_and_mark_stats(self) -> None:
        config = GameConfig()
        state = GameState.create(config)
        actor = state.players[0]
        actor.current_character = "산적"
        actor.total_steps = len(state.board) * 2 + 1
        target = state.players[1]
        target.current_character = "아전"

        engine = GameEngine(config, _TargetPolicy("아전"), rng=random.Random(123), enable_logging=False)
        engine._strategy_stats = [
            {
                "lap_cash_choices": 1, "lap_coin_choices": 2, "lap_shard_choices": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "marked_target_names": [],
            },
            {"lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "mark_attempts": 0, "mark_successes": 0, "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0, "marked_target_names": []},
            {"lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "mark_attempts": 0, "mark_successes": 0, "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0, "marked_target_names": []},
            {"lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "mark_attempts": 0, "mark_successes": 0, "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0, "marked_target_names": []},
        ]
        engine._queue_mark(state, actor.player_id, "아전", {"type": "bandit_tax"})
        state.winner_ids = [actor.player_id]
        state.end_reason = "SEVEN_TILES"

        result = engine._build_result(state)
        psummary = result.player_summary[0]
        ssummary = result.strategy_summary[0]
        self.assertEqual(psummary["laps_completed"], 2)
        self.assertEqual(psummary["lap_rewards_received"], 3)
        self.assertEqual(ssummary["laps_completed"], 2)
        self.assertEqual(ssummary["lap_rewards_received"], 3)
        self.assertEqual(ssummary["mark_attempts"], 1)
        self.assertEqual(ssummary["mark_successes"], 1)
        self.assertAlmostEqual(ssummary["mark_success_rate"], 1.0)

    def test_basic_stats_tracks_laps_and_mark_success_rate(self) -> None:
        stats = compute_basic_stats_from_games([
            {
                "winner_ids": [1],
                "player_summary": [
                    {"player_id": 0, "score": 7, "cash": 10, "tiles_owned": 4, "placed_score_coins": 3, "hand_coins": 1, "shards": 5, "laps_completed": 2, "lap_rewards_received": 2, "character": "객주"},
                    {"player_id": 1, "score": 5, "cash": 8, "tiles_owned": 3, "placed_score_coins": 2, "hand_coins": 0, "shards": 4, "laps_completed": 1, "lap_rewards_received": 1, "character": "아전"},
                ],
                "strategy_summary": [
                    {"player_id": 0, "mark_attempts": 2, "mark_successes": 1, "mark_success_rate": 0.5},
                    {"player_id": 1, "mark_attempts": 1, "mark_successes": 1, "mark_success_rate": 1.0},
                ],
            }
        ])
        self.assertEqual(stats["first_place_laps_completed_avg"], 2.0)
        self.assertEqual(stats["first_place_lap_reward_avg"], 2.0)
        self.assertEqual(stats["total_mark_attempts"], 3)
        self.assertEqual(stats["total_mark_successes"], 2)
        self.assertAlmostEqual(stats["mark_success_rate"], 2 / 3)


    def test_v2_marker_fallback_triggers_on_leader_emergency_only(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        other = state.players[2]
        player.current_character = "아전"
        leader.current_character = "중매꾼"
        other.current_character = "객주"
        leader.tiles_owned = 8
        leader.cash = 18
        other.tiles_owned = 3
        other.cash = 12

        v2 = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        v1 = HeuristicPolicy(character_policy_mode="heuristic_v1")
        v2_bonus = v2._distress_marker_bonus(state, player, ["교리 연구관", "객주"])
        v1_bonus = v1._distress_marker_bonus(state, player, ["교리 연구관", "객주"])

        self.assertGreater(v2_bonus["교리 연구관"], 0.0)
        self.assertEqual(v1_bonus["교리 연구관"], 0.0)

    def test_v2_mark_target_prioritizes_emergency_leader(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        follower = state.players[2]
        player.current_character = "자객"
        leader.current_character = "중매꾼"
        follower.current_character = "객주"
        leader.tiles_owned = 8
        leader.cash = 18
        follower.tiles_owned = 4
        follower.cash = 18

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
        leader_score, leader_reasons = policy._target_score_breakdown_v2(state, player, "자객", leader)
        follower_score, _ = policy._target_score_breakdown_v2(state, player, "자객", follower)

        self.assertGreater(leader_score, follower_score)
        self.assertIn("urgent_leader_target", leader_reasons)


    def test_v2_marker_counter_stays_live_even_with_direct_denial_option(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        follower = state.players[2]
        player.current_character = "아전"
        leader.current_character = "객주"
        follower.current_character = "파발꾼"
        leader.tiles_owned = 8
        leader.cash = 5
        leader.position = len(state.board) - 1
        follower.tiles_owned = 3
        follower.cash = 12
        state.active_by_card[3] = "탈출 노비"
        state.active_by_card[7] = "중매꾼"
        state.active_by_card[8] = "건설업자"

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_balanced")
        bonus = policy._distress_marker_bonus(state, player, ["자객", "교리 연구관"])

        self.assertGreater(bonus["교리 연구관"], 0.0)

    def test_v2_marker_flip_removes_leader_needed_escape_face(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        follower = state.players[2]
        player.current_character = "교리 연구관"
        leader.current_character = "객주"
        follower.current_character = "아전"
        leader.tiles_owned = 8
        leader.cash = 5
        leader.position = len(state.board) - 1
        follower.tiles_owned = 3
        follower.cash = 10
        state.active_by_card[3] = "탈출 노비"
        state.active_by_card[4] = "아전"
        state.active_by_card[7] = "중매꾼"
        state.active_by_card[8] = "건설업자"

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        choice = policy.choose_active_flip_card(state, player, [3, 4])

        self.assertEqual(choice, 3)

    def test_control_profile_prefers_marker_over_costly_direct_denial_when_cash_dry(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        other = state.players[2]
        player.current_character = "아전"
        player.cash = 3
        leader.current_character = "객주"
        leader.tiles_owned = 8
        leader.cash = 6
        leader.position = len(state.board) - 1
        other.current_character = "중매꾼"
        other.tiles_owned = 3
        other.cash = 12
        state.active_by_card[3] = "탈출 노비"
        state.active_by_card[7] = "중매꾼"
        state.active_by_card[8] = "건설업자"

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        marker_score, _ = policy._character_score_breakdown_v2(state, player, "교리 연구관")
        direct_score, _ = policy._character_score_breakdown_v2(state, player, "자객")

        self.assertGreater(marker_score, direct_score)

    def test_control_profile_keeps_pace_when_no_leader_emergency(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        rival = state.players[1]
        player.current_character = "아전"
        player.cash = 30
        rival.current_character = "객주"
        rival.tiles_owned = 2
        rival.cash = 10
        land_positions = _first_block_lands(state)
        state.tile_owner[land_positions[0]] = player.player_id
        state.tile_owner[land_positions[1]] = player.player_id
        player.tiles_owned = 2

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        growth_score, _ = policy._character_score_breakdown_v2(state, player, "중매꾼")
        direct_score, _ = policy._character_score_breakdown_v2(state, player, "자객")

        self.assertGreater(growth_score, direct_score)

    def test_control_lap_reward_prefers_shards_in_leader_emergency(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        follower = state.players[2]
        player.current_character = "교리 연구관"
        player.cash = 10
        player.shards = 2
        leader.current_character = "중매꾼"
        leader.tiles_owned = 8
        leader.cash = 18
        follower.current_character = "객주"
        follower.tiles_owned = 3
        follower.cash = 12

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_control")
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "shards")

    def test_control_lap_reward_keeps_cash_escape_when_critically_low(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        rival = state.players[1]
        player.current_character = "교리 연구관"
        player.cash = 2
        player.shards = 4
        rival.current_character = "객주"
        rival.tiles_owned = 3
        rival.cash = 10

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_control")
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "cash")

    def test_control_lap_reward_keeps_shards_when_emergency_high_but_liquidity_safe(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        player.current_character = "교리 감독관"
        player.cash = 6
        player.shards = 2
        leader.current_character = "중매꾼"
        leader.tiles_owned = 8
        leader.cash = 20

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_control")
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "shards")


    def test_control_finisher_window_prefers_expansion_followup(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        rival = state.players[1]
        player.current_character = "교리 연구관"
        player.cash = 12
        player.control_finisher_turns = 2
        player.control_finisher_reason = "solo_leader_broken"
        rival.current_character = "객주"
        rival.tiles_owned = 4
        rival.cash = 9
        land_positions = _first_block_lands(state)
        state.tile_owner[land_positions[0]] = player.player_id
        state.tile_owner[land_positions[1]] = player.player_id
        player.tiles_owned = 2

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        growth_score, _ = policy._character_score_breakdown_v2(state, player, "중매꾼")
        direct_score, _ = policy._character_score_breakdown_v2(state, player, "자객")

        self.assertGreater(growth_score, direct_score)

    def test_control_finisher_window_lap_reward_can_take_coins_when_safe_and_placeable(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        rival = state.players[1]
        player.current_character = "객주"
        player.cash = 12
        player.shards = 4
        player.control_finisher_turns = 2
        player.visited_owned_tile_indices = {1}
        land_pos = _first_block_lands(state)[0]
        state.tile_owner[land_pos] = player.player_id
        state.tile_coins[land_pos] = 0
        player.tiles_owned = 1
        rival.current_character = "중매꾼"
        rival.tiles_owned = 6
        rival.cash = 12

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_control")
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "coins")

    def test_control_lap_reward_takes_cash_when_low_cash_rent_pressure_stacks(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        leader = state.players[1]
        player.current_character = "교리 감독관"
        player.cash = 5
        player.shards = 5
        player.position = 1
        player.visited_owned_tile_indices.clear()
        player.trick_hand = []
        leader.current_character = "중매꾼"
        leader.tiles_owned = 7
        leader.cash = 18

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_control")
        policy._liquidity_risk_metrics = lambda state, player, character_name: {
            "expected_loss": 6.0,
            "worst_loss": 8.0,
            "reserve": 7.0,
            "cash_after_reserve": -2.0,
            "own_burden_cost": 1.0,
        }
        policy._rent_pressure_breakdown = lambda state, player, character_name: (2.4, ["stacked_rent"])
        policy._burden_context = lambda state, viewer, legal_targets=None: {
            "own_burdens": 1.0,
            "visible_all_burdens": 1.0,
            "cleanup_pressure": 2.8,
            "burden_holders": 1.0,
            "hidden_burden_estimate": 0.0,
            "legal_visible_burden_total": 0.0,
            "legal_visible_burden_peak": 0.0,
            "legal_low_cash_targets": 0.0,
        }
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "cash")



    def test_control_prefers_profit_mark_actor_over_plain_denial(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        target = state.players[1]
        player.current_character = "교리 감독관"
        player.shards = 5
        player.cash = 12
        target.current_character = "객주"
        target.cash = 16
        target.tiles_owned = 5

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_control")
        bandit_score, _ = policy._character_score_breakdown_v2(state, player, "산적")
        assassin_score, _ = policy._character_score_breakdown_v2(state, player, "자객")

        self.assertGreater(bandit_score, assassin_score)

    def test_token_opt_lap_reward_prefers_coins_when_revisit_window_open(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        player.current_character = "파발꾼"
        player.cash = 9
        player.hand_coins = 2
        player.position = 0
        land_pos = _first_block_lands(state)[0]
        state.tile_owner[land_pos] = player.player_id
        state.tile_coins[land_pos] = 1
        player.tiles_owned = 1
        player.visited_owned_tile_indices = {land_pos}

        policy = HeuristicPolicy(lap_policy_mode="heuristic_v2_token_opt")
        choice = policy.choose_lap_reward(state, player)

        self.assertEqual(choice.choice, "coins")

    def test_token_opt_movement_prefers_exact_placeable_revisit(self) -> None:
        state = GameState.create(GameConfig())
        player = state.players[0]
        player.current_character = "파발꾼"
        land_pos = _first_block_lands(state)[0]
        player.position = (land_pos - 3) % len(state.board)
        player.hand_coins = 2
        player.used_dice_cards = {3, 4, 5, 6}
        state.tile_owner[land_pos] = player.player_id
        state.tile_coins[land_pos] = 2
        player.tiles_owned = 1
        player.visited_owned_tile_indices = {land_pos}

        policy = HeuristicPolicy(character_policy_mode="heuristic_v2_token_opt")
        policy._landing_score = lambda state, player, pos: 0.0
        decision = policy.choose_movement(state, player)

        self.assertTrue(decision.use_cards)
        self.assertEqual(sum(decision.card_values), 3)

    def test_cached_decks_return_fresh_lists(self) -> None:
        fortune_a = build_fortune_deck()
        fortune_b = build_fortune_deck()
        self.assertIsNot(fortune_a, fortune_b)
        self.assertEqual(fortune_a, fortune_b)
        fortune_a.pop()
        self.assertNotEqual(len(fortune_a), len(fortune_b))

        trick_a = build_trick_deck()
        trick_b = build_trick_deck()
        self.assertIsNot(trick_a, trick_b)
        self.assertEqual(trick_a, trick_b)
        trick_a.pop()
        self.assertNotEqual(len(trick_a), len(trick_b))

        weather_a = build_weather_deck()
        weather_b = build_weather_deck()
        self.assertIsNot(weather_a, weather_b)
        self.assertEqual(weather_a, weather_b)
        weather_a.pop()
        self.assertNotEqual(len(weather_a), len(weather_b))

    def test_run_none_log_level_stays_summary_only(self) -> None:
        out_dir = Path("tmp_test_run_none")
        if out_dir.exists():
            for child in out_dir.iterdir():
                child.unlink()
            out_dir.rmdir()
        summary = run_with_logs(
            simulations=1,
            seed=7,
            output_dir=str(out_dir),
            log_level="none",
            emit_summary=False,
        )
        self.assertEqual(summary["version"], GAME_VERSION)
        games_path = out_dir / "games.jsonl"
        self.assertTrue(games_path.exists())
        row = json.loads(games_path.read_text(encoding="utf-8").strip())
        self.assertNotIn("action_log", row)
        self.assertEqual(row["version"], GAME_VERSION)
        for child in out_dir.iterdir():
            child.unlink()
        out_dir.rmdir()

    def test_module_doc_integrity(self) -> None:
        integrity = summarize_integrity()
        self.assertTrue(integrity["ok"], integrity["failures"])

if __name__ == "__main__":
    unittest.main()


class SummaryReliabilityTests(unittest.TestCase):
    def test_basic_stats_use_character_choice_counts_when_final_character_blank(self):
        from stats_utils import compute_basic_stats_from_games
        games = [{
            "winner_ids": [1],
            "player_summary": [
                {"player_id": 0, "character": "", "score": 3, "tiles_owned": 1, "placed_score_coins": 0, "hand_coins": 0, "cash": 5, "shards": 4, "laps_completed": 1, "lap_rewards_received": 1},
                {"player_id": 1, "character": "", "score": 1, "tiles_owned": 0, "placed_score_coins": 0, "hand_coins": 0, "cash": 2, "shards": 1, "laps_completed": 0, "lap_rewards_received": 0},
            ],
            "strategy_summary": [
                {"player_id": 0, "character": "", "last_selected_character": "박수", "character_choice_counts": {"박수": 2}, "mark_attempts": 0, "mark_successes": 0},
                {"player_id": 1, "character": "", "last_selected_character": "중매꾼", "character_choice_counts": {"중매꾼": 1}, "mark_attempts": 0, "mark_successes": 0},
            ],
        }]
        stats = compute_basic_stats_from_games(games)
        self.assertEqual(stats["character_pick_counts"]["박수"], 2)
        self.assertEqual(stats["character_pick_counts"]["중매꾼"], 1)
        self.assertEqual(stats["winner_character_counts"]["박수"], 1)
        self.assertEqual(stats["final_character_counts"]["박수"], 1)

    def test_basic_stats_tracks_missing_and_null_reliability(self):
        from stats_utils import compute_basic_stats_from_games
        games = [{
            "winner_ids": [1],
            "player_summary": [
                {"player_id": 0, "character": "", "score": None, "tiles_owned": 1, "placed_score_coins": 0, "hand_coins": None, "cash": 5, "shards": 4, "laps_completed": 1, "lap_rewards_received": 1},
            ],
            "strategy_summary": [
                {"player_id": 0, "character": "", "last_selected_character": "", "character_choice_counts": {}, "mark_attempts": 0, "mark_successes": 0},
            ],
        }]
        stats = compute_basic_stats_from_games(games)
        self.assertEqual(stats["reliability"]["missing_character_summary_rows"], 1)
        self.assertEqual(stats["reliability"]["missing_strategy_character_rows"], 1)
        self.assertEqual(stats["reliability"]["null_numeric_fields"]["score"], 1)
        self.assertEqual(stats["reliability"]["null_numeric_fields"]["hand"], 1)
