from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

import json
import tempfile
import unittest
from pathlib import Path

from ai_policy import HeuristicPolicy, LapRewardDecision
from config import DEFAULT_CONFIG, GameConfig
from engine import GameEngine
from state import GameState
from test_event_effects import DummyPolicy


class PolicyHookTests(unittest.TestCase):
    def test_policy_hooks_capture_before_and_after_decisions(self):
        policy = HeuristicPolicy(character_policy_mode="heuristic_v1", lap_policy_mode="heuristic_v1")
        seen = []
        policy.register_policy_hook("policy.before_decision", lambda policy, decision_name, state, player, args, kwargs: seen.append(("before", decision_name, player.player_id)))
        policy.register_policy_hook("policy.after_decision", lambda policy, decision_name, state, player, result, args, kwargs: seen.append(("after", decision_name, player.player_id, result.choice if hasattr(result, 'choice') else None)))
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        result = policy.choose_lap_reward(state, player)
        self.assertIsInstance(result, LapRewardDecision)
        self.assertEqual(seen[0][:3], ("before", "choose_lap_reward", 0))
        self.assertEqual(seen[1][:3], ("after", "choose_lap_reward", 0))

    def test_engine_attaches_ai_decision_log_hook(self):
        engine = GameEngine(DEFAULT_CONFIG, HeuristicPolicy(), enable_logging=True)
        state = GameState.create(DEFAULT_CONFIG)
        player = state.players[0]
        engine.policy.choose_lap_reward(state, player)
        events = [row["event"] for row in engine._action_log]
        self.assertIn("ai_decision_before", events)
        self.assertIn("ai_decision_after", events)


class RuleScriptTests(unittest.TestCase):
    def test_custom_rule_script_can_override_f1_landing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rules.json"
            path.write_text(json.dumps({
                "events": {
                    "landing.f.resolve": [
                        {
                            "when": {"cell": "F1"},
                            "actions": [
                                {"type": "change_f", "amount": 7},
                                {"type": "change_shards", "target": "player", "amount": 3},
                                {"type": "set_result", "value": {"type": "F1_CUSTOM", "f_delta": 7, "shards": 3}},
                                {"type": "apply_same_tile_bonus"}
                            ],
                            "return": "result"
                        }
                    ]
                }
            }, ensure_ascii=False), encoding="utf-8")
            cfg = GameConfig(rule_scripts_path=str(path))
            engine = GameEngine(cfg, DummyPolicy(), enable_logging=False)
            state = GameState.create(cfg)
            player = state.players[0]
            f1_pos = next(i for i, cell in enumerate(state.board) if str(cell.name) == "F1")
            player.position = f1_pos
            result = engine._resolve_landing(state, player)
            self.assertEqual(result["type"], "F1_CUSTOM")
            self.assertEqual(result["f_delta"], 7)
            self.assertGreaterEqual(player.shards, 3)

    def test_default_rule_scripts_loaded(self):
        engine = GameEngine(DEFAULT_CONFIG, DummyPolicy(), enable_logging=False)
        self.assertIn("landing.f.resolve", engine.rule_scripts.scripts)
        self.assertIn("game.end.evaluate", engine.rule_scripts.scripts)


if __name__ == "__main__":
    unittest.main()
