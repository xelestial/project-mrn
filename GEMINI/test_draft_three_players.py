import random
import unittest

from ai_policy import BasePolicy, MovementDecision, LapRewardDecision
from characters import CARD_TO_NAMES
from config import DEFAULT_CONFIG
from engine import GameEngine
from state import GameState


class SimpleDraftPolicy(BasePolicy):
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


class ThreePlayerDraftTests(unittest.TestCase):
    def setUp(self):
        self.engine = GameEngine(DEFAULT_CONFIG, SimpleDraftPolicy(), rng=random.Random(0), enable_logging=True)
        self.state = GameState.create(DEFAULT_CONFIG)
        self.engine._strategy_stats = [
            {"purchases":0,"purchase_t2":0,"purchase_t3":0,"rent_paid":0,"own_tile_visits":0,
             "f1_visits":0,"f2_visits":0,"s_visits":0,"s_cash_plus1":0,"s_cash_plus2":0,"s_cash_minus1":0,
             "malicious_visits":0,"bankruptcies":0,"cards_used":0,"card_turns":0,"single_card_turns":0,"pair_card_turns":0,
             "lap_cash_choices":0,"lap_coin_choices":0,"lap_shard_choices":0,"coins_gained_own_tile":0,"coins_placed":0,
             "character":"","shards_gained_f":0,"shards_gained_lap":0,"draft_cards":[],"marked_target_names":[]}
            for _ in range(DEFAULT_CONFIG.player_count)
        ]

    def test_three_player_draft_only_alive_players_and_two_cards_each(self):
        self.state.players[3].alive = False
        self.state.marker_owner_id = 0
        self.engine._run_draft(self.state)

        alive_ids = [0, 1, 2]
        dead = self.state.players[3]
        all_picks = []
        for pid in alive_ids:
            p = self.state.players[pid]
            self.assertEqual(len(p.drafted_cards), 2)
            self.assertTrue(p.current_character)
            all_picks.extend(p.drafted_cards)
        self.assertEqual(len(all_picks), 6)
        self.assertEqual(len(set(all_picks)), 6)
        self.assertEqual(dead.drafted_cards, [])
        self.assertEqual(dead.current_character, "")
        hidden = [e for e in self.engine._action_log if e.get("event") == "draft_hidden_card"]
        self.assertEqual(len(hidden), 1)

    def test_three_player_draft_starts_from_next_alive_if_marker_owner_dead(self):
        self.state.players[0].alive = False
        self.state.marker_owner_id = 0
        self.engine._run_draft(self.state)
        phase1 = [e for e in self.engine._action_log if e.get("event") == "draft_pick" and e.get("phase") == 1]
        self.assertEqual([e["player"] for e in phase1], [2, 3, 4])
        for pid in [1, 2, 3]:
            self.assertEqual(len(self.state.players[pid].drafted_cards), 2)
        self.assertEqual(self.state.players[0].drafted_cards, [])


if __name__ == "__main__":
    unittest.main()
