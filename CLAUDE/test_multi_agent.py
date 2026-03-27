from __future__ import annotations
"""multi_agent 패키지 통합 테스트."""

import random
import pytest

from multi_agent.agent_loader import make_agent
from multi_agent.dispatcher import MultiAgentDispatcher


# ── 1. agent_loader ────────────────────────────────────────────────────────


class TestAgentLoader:

    def test_make_claude_default(self):
        a = make_agent("claude")
        assert a.agent_id.startswith("claude:")

    def test_make_claude_profile(self):
        a = make_agent("claude:v3_claude")
        assert "v3_claude" in a.agent_id

    def test_make_claude_balanced(self):
        a = make_agent("claude:balanced")
        assert "balanced" in a.agent_id

    def test_make_gpt_default(self):
        a = make_agent("gpt")
        assert a.agent_id.startswith("gpt:")

    def test_make_gpt_profile(self):
        a = make_agent("gpt:v3_gpt")
        assert "v3_gpt" in a.agent_id

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown agent source"):
            make_agent("gemini:v1")


# ── 2. MultiAgentDispatcher 구성 ──────────────────────────────────────────


class TestMultiAgentDispatcher:

    def _make_dispatcher(self):
        agents = {
            1: make_agent("claude:v3_claude"),
            2: make_agent("gpt:v3_gpt"),
            3: make_agent("claude:balanced"),
            4: make_agent("claude:balanced"),
        }
        return MultiAgentDispatcher(agents)

    def test_construction(self):
        d = self._make_dispatcher()
        assert d.character_policy_mode == "multi_agent"

    def test_agent_id_for_player(self):
        d = self._make_dispatcher()
        assert "claude" in d.agent_id_for_player(1)
        assert "gpt" in d.agent_id_for_player(2)

    def test_set_rng_propagates(self):
        d = self._make_dispatcher()
        rng = random.Random(0)
        d.set_rng(rng)  # must not raise


# ── 3. 실제 게임 1판 ────────────────────────────────────────────────────────


class TestBattleOneGame:

    def test_one_game_no_error(self):
        """Claude vs GPT 1판을 에러 없이 완주하는지 확인."""
        import random as rand
        from config import DEFAULT_CONFIG
        from engine import GameEngine
        from simulate_with_logs import result_to_dict

        agents = {
            1: make_agent("claude:v3_claude"),
            2: make_agent("gpt:v3_gpt"),
            3: make_agent("claude:balanced"),
            4: make_agent("claude:balanced"),
        }
        policy = MultiAgentDispatcher(agents)
        rng = rand.Random(777)
        engine = GameEngine(DEFAULT_CONFIG, policy, rng=rng, enable_logging=False)
        result = engine.run()
        assert result is not None
        assert result.total_turns > 0
        assert len(result.winner_ids) >= 1

    def test_result_has_agent_routing(self):
        """각 플레이어 결정이 올바른 agent로 라우팅되는지 간접 확인."""
        import random as rand
        from config import DEFAULT_CONFIG
        from engine import GameEngine

        agents = {
            1: make_agent("claude:v3_claude"),
            2: make_agent("gpt:v3_gpt"),
            3: make_agent("claude:balanced"),
            4: make_agent("claude:balanced"),
        }
        dispatcher = MultiAgentDispatcher(agents)
        # agent_id_for_player가 올바른 source를 반환하는지
        assert dispatcher.agent_id_for_player(1).startswith("claude:")
        assert dispatcher.agent_id_for_player(2).startswith("gpt:")

        rng = rand.Random(42)
        engine = GameEngine(DEFAULT_CONFIG, dispatcher, rng=rng, enable_logging=False)
        result = engine.run()
        assert result.total_turns > 0
