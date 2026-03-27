from __future__ import annotations

import random
import unittest

from ai_policy import BasePolicy, LapRewardDecision
from config import GameConfig
from engine import GameEngine
from game_rules import EndConditionRules, ForceSaleRules, GameRules, LapRewardRules, TakeoverRules, TokenRules
from state import GameState


class _CoinLapPolicy(BasePolicy):
    def choose_lap_reward(self, state, player):
        return LapRewardDecision(choice='coins')


class RuleInjectionTest(unittest.TestCase):
    def test_custom_lap_reward_rules_are_injected(self):
        rules = GameRules(lap_reward=LapRewardRules(cash=9, coins=4, shards=7))
        cfg = GameConfig(rules=rules)
        state = GameState.create(cfg)
        player = state.players[0]
        engine = GameEngine(cfg, _CoinLapPolicy(), rng=random.Random(1), enable_logging=False)
        engine._strategy_stats = [{"lap_cash_choices":0,"lap_coin_choices":0,"lap_shard_choices":0,"shards_gained_lap":0} for _ in range(cfg.player_count)]
        result = engine._apply_lap_reward(state, player)
        self.assertEqual(result['coins_delta'], 4)
        self.assertEqual(player.hand_coins, cfg.rules.token.starting_hand_coins + 4)

    def test_custom_end_rules_are_injected(self):
        rules = GameRules(end=EndConditionRules(f_threshold=5.0, monopolies_to_trigger_end=0, tiles_to_trigger_end=None, alive_players_at_most=1))
        cfg = GameConfig(rules=rules)
        state = GameState.create(cfg)
        engine = GameEngine(cfg, BasePolicy(), rng=random.Random(1), enable_logging=False)
        state.f_value = 5.0
        self.assertEqual(engine._evaluate_end_rules(state), 'F_THRESHOLD')

    def test_custom_force_sale_rules_disable_refund_and_repurchase_block(self):
        rules = GameRules(force_sale=ForceSaleRules(refund_purchase_cost=False, return_tile_coins_to_original_owner=False, block_repurchase_until_next_turn=False))
        cfg = GameConfig(rules=rules)
        state = GameState.create(cfg)
        engine = GameEngine(cfg, BasePolicy(), rng=random.Random(1), enable_logging=False)
        owner = state.players[1]
        pos = state.block_tile_positions(1, land_only=True)[0]
        state.tile_owner[pos] = owner.player_id
        owner.tiles_owned = 1
        state.tile_coins[pos] = 2
        owner.score_coins_placed = 2
        out = engine._apply_force_sale(state, state.players[0], pos)
        self.assertEqual(out['purchase_refund'], 0)
        self.assertEqual(out['returned_coins'], 0)
        self.assertFalse(out['blocked_until_next_turn'])
        self.assertEqual(owner.hand_coins, cfg.rules.token.starting_hand_coins)
        self.assertEqual(state.tile_purchase_blocked_turn_index.get(pos), None)

    def test_custom_takeover_rules_allow_monopoly_takeover(self):
        rules = GameRules(takeover=TakeoverRules(blocked_by_monopoly=False, transfer_tile_coins=True))
        cfg = GameConfig(rules=rules)
        state = GameState.create(cfg)
        engine = GameEngine(cfg, BasePolicy(), rng=random.Random(1), enable_logging=False)
        p0, p1 = state.players[0], state.players[1]
        lands = state.block_tile_positions(1, land_only=True)
        for pos in lands:
            state.tile_owner[pos] = p0.player_id
            p0.tiles_owned += 1
        state.tile_coins[lands[0]] = 1
        p0.score_coins_placed = 1
        out = engine._transfer_tile(state, lands[0], p1.player_id)
        self.assertTrue(out['changed'])
        self.assertEqual(state.tile_owner[lands[0]], p1.player_id)
        self.assertEqual(p1.score_coins_placed, 1)

    def test_legacy_values_sync_from_rules(self):
        rules = GameRules(token=TokenRules(max_coins_per_tile=4), lap_reward=LapRewardRules(cash=6, coins=9, shards=2))
        cfg = GameConfig(rules=rules)
        self.assertEqual(cfg.coins.max_coins_per_tile, 4)
        self.assertEqual(cfg.coins.lap_reward_cash, 6)
        self.assertEqual(cfg.coins.lap_reward_coins, 9)
        self.assertEqual(cfg.shards.lap_reward_shards, 2)

    def test_stage3_rules_sync_economy_resources_dice_special(self):
        rules = GameRules()
        rules.economy.starting_cash = 77
        rules.resources.starting_shards = 9
        rules.dice.enabled = False
        rules.special_tiles.malicious_land_multiplier = 5
        cfg = GameConfig(rules=rules)
        self.assertEqual(cfg.economy.starting_cash, 77)
        self.assertEqual(cfg.shards.starting_shards, 9)
        self.assertFalse(cfg.dice_cards.enabled)
        self.assertEqual(cfg.board.malicious_land_multiplier, 5)


if __name__ == '__main__':
    unittest.main()
