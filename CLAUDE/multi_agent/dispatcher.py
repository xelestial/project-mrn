from __future__ import annotations
"""MultiAgentDispatcher — routes engine choose_* calls to per-player agents."""

import sys
import os
from typing import Any, Optional

_CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CLAUDE_DIR not in sys.path:
    sys.path.insert(0, _CLAUDE_DIR)

from ai_policy import BasePolicy
from .base_agent import AbstractPlayerAgent


class MultiAgentDispatcher(BasePolicy):
    """
    GameEngine이 보는 단일 policy 객체.
    player.player_id(0-indexed)를 보고 등록된 agent로 위임한다.

    agents: {player_id_1indexed: AbstractPlayerAgent}
    """

    def __init__(self, agents: dict[int, AbstractPlayerAgent]):
        super().__init__()
        # 1-indexed player_id → agent
        self._agents: dict[int, AbstractPlayerAgent] = {
            int(k): v for k, v in agents.items()
        }
        self.character_policy_mode = "multi_agent"
        self.lap_policy_mode = "multi_agent"

    # ── 메타 ──────────────────────────────────────────────────

    def set_rng(self, rng: Any) -> None:
        for agent in self._agents.values():
            agent.set_rng(rng)

    def agent_id_for_player(self, player_id_1indexed: int) -> str:
        agent = self._agents.get(player_id_1indexed)
        return agent.agent_id if agent else "unknown"

    def character_mode_for_player(self, player_id_0indexed: int) -> str:
        agent = self._agents.get(player_id_0indexed + 1)
        return agent.agent_id if agent else "unknown"

    # ── 라우팅 헬퍼 ───────────────────────────────────────────

    def _a(self, player: Any) -> AbstractPlayerAgent:
        """player (0-indexed player_id) → 해당 agent."""
        pid = int(player.player_id) + 1
        agent = self._agents.get(pid)
        if agent is None:
            raise KeyError(f"No agent registered for player {pid}")
        return agent

    # ── choose_* 위임 ─────────────────────────────────────────

    def choose_movement(self, state, player):
        return self._a(player).choose_movement(state, player)

    def choose_draft_card(self, state, player, offered_cards):
        return self._a(player).choose_draft_card(state, player, offered_cards)

    def choose_final_character(self, state, player, card_choices):
        return self._a(player).choose_final_character(state, player, card_choices)

    def choose_lap_reward(self, state, player):
        return self._a(player).choose_lap_reward(state, player)

    def choose_trick_to_use(self, state, player, hand):
        return self._a(player).choose_trick_to_use(state, player, hand)

    def choose_hidden_trick_card(self, state, player, hand):
        return self._a(player).choose_hidden_trick_card(state, player, hand)

    def choose_mark_target(self, state, player, actor_name):
        return self._a(player).choose_mark_target(state, player, actor_name)

    def choose_coin_placement_tile(self, state, player):
        return self._a(player).choose_coin_placement_tile(state, player)

    def choose_geo_bonus(self, state, player, char):
        return self._a(player).choose_geo_bonus(state, player, char)

    def choose_doctrine_relief_target(self, state, player, candidates):
        return self._a(player).choose_doctrine_relief_target(state, player, candidates)

    def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):
        return self._a(player).choose_purchase_tile(state, player, pos, cell, cost, source=source)

    def choose_specific_trick_reward(self, state, player, choices):
        return self._a(player).choose_specific_trick_reward(state, player, choices)

    def choose_burden_exchange_on_supply(self, state, player, card):
        return self._a(player).choose_burden_exchange_on_supply(state, player, card)

    def choose_active_flip_card(self, state, player, flippable_cards):
        return self._a(player).choose_active_flip_card(state, player, flippable_cards)
