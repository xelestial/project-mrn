from __future__ import annotations
"""GptPlayerAgent — wraps GPT HeuristicPolicy as an AbstractPlayerAgent.

GPT의 ai_policy는 CLAUDE와 survival_common 등 일부 모듈이 다르므로
sys.modules를 일시 교체해 GPT 버전으로 격리 로드한다.
"""

import os
import sys
from typing import Any, Optional

from .base_agent import AbstractPlayerAgent

_CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GPT_DIR = os.path.normpath(os.path.join(_CLAUDE_DIR, "..", "GPT"))

# GPT 모듈과 충돌하는 모듈 목록 (CLAUDE와 다를 수 있는 것들)
_GPT_OWN_MODULES = [
    "survival_common", "policy_groups", "policy_mark_utils",
    "policy_hooks", "ai_policy",
    # policy 패키지
    "policy", "policy.profile", "policy.profile.spec",
    "policy.profile.registry", "policy.profile.presets",
]


def _load_gpt_policy_class():
    """
    GPT의 HeuristicPolicy 클래스를 격리 로드해 반환한다.
    CLAUDE의 sys.modules를 보존하고 복원한다.
    """
    # 1. 충돌 모듈의 현재(CLAUDE) 버전 저장
    saved = {k: sys.modules.pop(k) for k in _GPT_OWN_MODULES if k in sys.modules}

    # 2. GPT 경로를 path 최상위에 삽입
    sys.path.insert(0, _GPT_DIR)
    orig_cwd = os.getcwd()
    os.chdir(_GPT_DIR)

    try:
        # 3. GPT 버전으로 새로 임포트
        import ai_policy as _gpt_ai_policy  # noqa: PLC0415
        GptPolicy = _gpt_ai_policy.HeuristicPolicy
        return GptPolicy
    finally:
        # 4. GPT 버전을 sys.modules에서 제거
        for k in _GPT_OWN_MODULES:
            sys.modules.pop(k, None)
        # 5. CLAUDE 버전 복원
        sys.modules.update(saved)
        # 6. 경로 복원
        if _GPT_DIR in sys.path:
            sys.path.remove(_GPT_DIR)
        os.chdir(orig_cwd)


# 모듈 임포트 시 한 번만 로드
_GptHeuristicPolicy = _load_gpt_policy_class()


class GptPlayerAgent(AbstractPlayerAgent):
    """GPT HeuristicPolicy를 AbstractPlayerAgent로 래핑."""

    def __init__(self, profile: str = "heuristic_v3_gpt"):
        self._policy = _GptHeuristicPolicy(
            character_policy_mode=profile,
            lap_policy_mode=profile,
        )
        self._profile = profile

    @property
    def agent_id(self) -> str:
        return f"gpt:{self._profile}"

    def set_rng(self, rng: Any) -> None:
        if hasattr(self._policy, "set_rng"):
            self._policy.set_rng(rng)

    def register_policy_hook(self, event: str, fn: Any) -> None:
        if hasattr(self._policy, "register_policy_hook"):
            self._policy.register_policy_hook(event, fn)

    def choose_movement(self, state, player):
        return self._policy.choose_movement(state, player)

    def choose_draft_card(self, state, player, offered_cards):
        return self._policy.choose_draft_card(state, player, offered_cards)

    def choose_final_character(self, state, player, card_choices):
        return self._policy.choose_final_character(state, player, card_choices)

    def choose_lap_reward(self, state, player):
        return self._policy.choose_lap_reward(state, player)

    def choose_trick_to_use(self, state, player, hand):
        return self._policy.choose_trick_to_use(state, player, hand)

    def choose_hidden_trick_card(self, state, player, hand):
        return self._policy.choose_hidden_trick_card(state, player, hand)

    def choose_mark_target(self, state, player, actor_name):
        return self._policy.choose_mark_target(state, player, actor_name)

    def choose_coin_placement_tile(self, state, player):
        return self._policy.choose_coin_placement_tile(state, player)

    def choose_geo_bonus(self, state, player, char):
        return self._policy.choose_geo_bonus(state, player, char)

    def choose_doctrine_relief_target(self, state, player, candidates):
        return self._policy.choose_doctrine_relief_target(state, player, candidates)

    def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):
        if hasattr(self._policy, "choose_purchase_tile"):
            return self._policy.choose_purchase_tile(state, player, pos, cell, cost, source=source)
        return True

    def choose_specific_trick_reward(self, state, player, choices):
        if hasattr(self._policy, "choose_specific_trick_reward"):
            return self._policy.choose_specific_trick_reward(state, player, choices)
        return None

    def choose_burden_exchange_on_supply(self, state, player, card):
        if hasattr(self._policy, "choose_burden_exchange_on_supply"):
            return self._policy.choose_burden_exchange_on_supply(state, player, card)
        return True

    def choose_active_flip_card(self, state, player, flippable_cards):
        if hasattr(self._policy, "choose_active_flip_card"):
            return self._policy.choose_active_flip_card(state, player, flippable_cards)
        return None
