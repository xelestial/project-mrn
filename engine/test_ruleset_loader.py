from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


import json
import unittest
from pathlib import Path

from config import GameConfig
from game_rules_loader import load_ruleset, rules_from_dict, rules_to_dict
from simulate_with_logs import _runtime_config


class RulesetLoaderTest(unittest.TestCase):
    def test_rules_roundtrip_dict(self):
        raw = {
            'rules': {
                'lap_reward': {'cash': 7, 'coins': 4, 'shards': 2},
                'start_reward': {'points_budget': 20, 'cash_point_cost': 2, 'shards_point_cost': 3, 'coins_point_cost': 3},
                'end': {'f_threshold': 9, 'tiles_to_trigger_end': 7, 'monopolies_to_trigger_end': 2, 'alive_players_at_most': 3},
            }
        }
        rules = rules_from_dict(raw['rules'])
        dumped = rules_to_dict(rules)
        self.assertEqual(dumped['rules']['lap_reward']['cash'], 7)
        self.assertEqual(dumped['rules']['start_reward']['points_budget'], 20)
        self.assertEqual(dumped['rules']['start_reward']['coins_point_cost'], 3)
        self.assertEqual(dumped['rules']['end']['tiles_to_trigger_end'], 7)

    def test_rules_roundtrip_stage3_sections(self):
        raw = {'rules': {'economy': {'starting_cash': 61}, 'resources': {'starting_shards': 8}, 'dice': {'enabled': False, 'values': [2,4]}, 'special_tiles': {'malicious_land_multiplier': 7, 'f1_shards': 3}}}
        rules = rules_from_dict(raw['rules'])
        dumped = rules_to_dict(rules)['rules']
        self.assertEqual(dumped['economy']['starting_cash'], 61)
        self.assertEqual(dumped['resources']['starting_shards'], 8)
        self.assertFalse(dumped['dice']['enabled'])
        self.assertEqual(dumped['special_tiles']['malicious_land_multiplier'], 7)

    def test_game_config_loads_ruleset_path(self):
        path = Path('tmp_ruleset_test.json')
        path.write_text(json.dumps({'rules': {'lap_reward': {'cash': 7, 'coins': 4, 'shards': 2}}}), encoding='utf-8')
        try:
            cfg = GameConfig(rules=None, ruleset_path=str(path))
            self.assertEqual(cfg.rules.lap_reward.cash, 7)
            self.assertEqual(cfg.coins.lap_reward_cash, 7)
        finally:
            if path.exists():
                path.unlink()

    def test_runtime_config_explicit_ruleset_override(self):
        path = Path('tmp_ruleset_runtime.json')
        path.write_text(json.dumps({'rules': {'token': {'starting_hand_coins': 5}, 'lap_reward': {'cash': 6, 'coins': 4, 'shards': 1}}}), encoding='utf-8')
        try:
            cfg = _runtime_config(None, None, None, None, str(path))
            self.assertEqual(cfg.rules.token.starting_hand_coins, 5)
            self.assertEqual(cfg.rules.lap_reward.cash, 6)
            self.assertEqual(cfg.coins.starting_hand_coins, 5)
        finally:
            if path.exists():
                path.unlink()


if __name__ == '__main__':
    unittest.main()
