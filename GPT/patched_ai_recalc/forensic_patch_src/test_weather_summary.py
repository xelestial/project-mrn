import random
import unittest

from ai_policy import BasePolicy, HeuristicPolicy, MovementDecision, LapRewardDecision
from config import DEFAULT_CONFIG
from engine import GameEngine
from simulate_with_logs import RunningSummary, result_to_dict


class DummyPolicy(BasePolicy):
    def choose_movement(self, state, player):
        return MovementDecision(False, ())

    def choose_lap_reward(self, state, player):
        return LapRewardDecision("cash")

    def choose_coin_placement_tile(self, state, player):
        return None

    def choose_draft_card(self, state, player, offered_cards):
        return offered_cards[0]

    def choose_final_character(self, state, player, card_choices):
        return state.active_by_card[card_choices[0]]

    def choose_mark_target(self, state, player, actor_name):
        return None

    def choose_geo_bonus(self, state, player, actor_name):
        return "cash"


class WeatherSummaryTests(unittest.TestCase):
    def test_result_to_dict_includes_weather_history(self):
        engine = GameEngine(DEFAULT_CONFIG, HeuristicPolicy(character_policy_mode="random", lap_policy_mode="heuristic_v1"), rng=random.Random(0), enable_logging=False)
        result = engine.run()
        payload = result_to_dict(result)
        self.assertIn("weather_history", payload)
        self.assertEqual(payload["weather_history"], result.weather_history)
        self.assertGreaterEqual(len(payload["weather_history"]), 1)
        self.assertEqual(len(payload["weather_history"]), result.rounds_completed + 1)

    def test_running_summary_tracks_weather_counts(self):
        running = RunningSummary(policy_mode="arena")
        game = {
            "winner_ids": [1],
            "end_reason": "F_THRESHOLD",
            "total_turns": 10,
            "rounds_completed": 2,
            "bankrupt_players": 0,
            "final_f_value": 15,
            "total_placed_coins": 1,
            "player_summary": [
                {"player_id": 0, "cash": 10, "tiles_owned": 1, "placed_score_coins": 1, "hand_coins": 0, "score": 2, "turns_taken": 3, "shards": 0},
                {"player_id": 1, "cash": 10, "tiles_owned": 0, "placed_score_coins": 0, "hand_coins": 0, "score": 0, "turns_taken": 3, "shards": 0},
                {"player_id": 2, "cash": 10, "tiles_owned": 0, "placed_score_coins": 0, "hand_coins": 0, "score": 0, "turns_taken": 2, "shards": 0},
                {"player_id": 3, "cash": 10, "tiles_owned": 0, "placed_score_coins": 0, "hand_coins": 0, "score": 0, "turns_taken": 2, "shards": 0},
            ],
            "strategy_summary": [
                {"player_id": i, "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0, "tricks_used": 0, "shard_income_cash": 0, "mark_attempts": 0, "mark_successes": 0}
                for i in range(4)
            ],
            "weather_history": ["사냥의 계절", "외세의 침략", "사냥의 계절"],
            "player_lap_policy_modes": {},
            "player_character_policy_modes": {},
        }
        running.update(game)
        summary = running.to_dict()
        self.assertEqual(summary["weather_counts"]["사냥의 계절"], 2)
        self.assertEqual(summary["weather_counts"]["외세의 침략"], 1)
        self.assertEqual(summary["weather_game_presence"]["사냥의 계절"], 1)
        self.assertEqual(summary["avg_weather_rounds_per_game"], 3.0)


if __name__ == "__main__":
    unittest.main()
