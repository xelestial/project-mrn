from __future__ import annotations

import random
from pathlib import Path

import pytest

from battle import run_battle
from config import DEFAULT_CONFIG
from engine import GameEngine
from multi_agent.agent_loader import make_agent
from multi_agent.dispatcher import MultiAgentDispatcher
from multi_agent.gpt_agent import _GPT_RUNTIME
from multi_agent.claude_agent import _CLAUDE_RUNTIME


class TestAgentLoader:
    def test_make_claude_default(self):
        agent = make_agent("claude")
        assert agent.agent_id.startswith("claude:")

    def test_make_claude_profile(self):
        agent = make_agent("claude:v3_claude")
        assert "v3_claude" in agent.agent_id

    def test_make_gpt_default(self):
        agent = make_agent("gpt")
        assert agent.agent_id.startswith("gpt:")

    def test_make_gpt_profile(self):
        agent = make_agent("gpt:v3_gpt")
        assert "v3_gpt" in agent.agent_id

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown agent source"):
            make_agent("gemini:v1")

    def test_runtime_loader_keeps_host_survival_common(self):
        import survival_common as host_survival_common

        assert hasattr(host_survival_common, "CleanupStrategyContext")
        make_agent("claude:v3_claude")

        import survival_common as host_survival_common_after

        assert host_survival_common_after is host_survival_common
        assert hasattr(host_survival_common_after, "CleanupStrategyContext")

    def test_runtime_modules_are_isolated(self):
        assert _CLAUDE_RUNTIME.alias_modules["ai_policy"] != _GPT_RUNTIME.alias_modules["ai_policy"]
        assert _CLAUDE_RUNTIME.heuristic_policy_cls.__module__.startswith("_isolated_claude_")
        assert _GPT_RUNTIME.heuristic_policy_cls.__module__.startswith("_isolated_gpt_")


class TestMultiAgentDispatcher:
    def _make_dispatcher(self):
        return MultiAgentDispatcher(
            {
                1: make_agent("claude:v3_claude"),
                2: make_agent("gpt:v3_gpt"),
                3: make_agent("gpt:v3_gpt"),
                4: make_agent("gpt:v3_gpt"),
            }
        )

    def test_construction(self):
        dispatcher = self._make_dispatcher()
        assert dispatcher.character_policy_mode == "multi_agent"

    def test_agent_id_for_player(self):
        dispatcher = self._make_dispatcher()
        assert dispatcher.agent_id_for_player(1).startswith("claude:")
        assert dispatcher.agent_id_for_player(2).startswith("gpt:")

    def test_set_rng_propagates(self):
        dispatcher = self._make_dispatcher()
        dispatcher.set_rng(random.Random(0))


class TestBattleSmoke:
    def test_one_game_no_error(self):
        dispatcher = MultiAgentDispatcher(
            {
                1: make_agent("claude:v3_claude"),
                2: make_agent("gpt:v3_gpt"),
                3: make_agent("gpt:v3_gpt"),
                4: make_agent("gpt:v3_gpt"),
            }
        )
        engine = GameEngine(DEFAULT_CONFIG, dispatcher, rng=random.Random(777), enable_logging=False)
        result = engine.run()
        assert result is not None
        assert result.total_turns > 0
        assert len(result.winner_ids) >= 1

    def test_run_battle_writes_lineup(self):
        output_dir = Path("GPT/_codex_runs/test_multi_agent_smoke")
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = run_battle(
            player_specs={
                1: "claude:v3_claude",
                2: "gpt:v3_gpt",
                3: "gpt:v3_gpt",
                4: "gpt:v3_gpt",
            },
            simulations=1,
            seed=42,
            output_dir=str(output_dir),
        )
        assert summary["policy_mode"] == "multi_agent"
        assert summary["agent_lineup"][1].startswith("claude:")
        assert summary["agent_lineup"][2].startswith("gpt:")
