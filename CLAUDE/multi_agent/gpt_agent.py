from __future__ import annotations
"""GptPlayerAgent — wraps GPT HeuristicPolicy as an AbstractPlayerAgent."""

import os
from typing import Any

from .base_agent import AbstractPlayerAgent
from .runtime_loader import load_policy_runtime

_CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GPT_DIR = os.path.normpath(os.path.join(_CLAUDE_DIR, "..", "GPT"))
_GPT_RUNTIME_MODULES = (
    "survival_common",
    "policy_groups",
    "policy_mark_utils",
    "policy_hooks",
    "ai_policy",
)
_GPT_RUNTIME = load_policy_runtime(
    runtime_id="gpt",
    root_dir=_GPT_DIR,
    isolated_modules=_GPT_RUNTIME_MODULES,
)


class GptPlayerAgent(AbstractPlayerAgent):
    """GPT HeuristicPolicy를 AbstractPlayerAgent로 래핑."""

    def __init__(self, profile: str = "heuristic_v3_gpt"):
        with _GPT_RUNTIME.activated():
            self._policy = _GPT_RUNTIME.heuristic_policy_cls(
                character_policy_mode=profile,
                lap_policy_mode=profile,
            )
        self._profile = profile

    @property
    def agent_id(self) -> str:
        return f"gpt:{self._profile}"

    def _call(self, fn, *args, **kwargs):
        with _GPT_RUNTIME.activated():
            return fn(*args, **kwargs)

    def set_rng(self, rng: Any) -> None:
        if hasattr(self._policy, "set_rng"):
            self._call(self._policy.set_rng, rng)

    def register_policy_hook(self, event: str, fn: Any) -> None:
        if hasattr(self._policy, "register_policy_hook"):
            self._call(self._policy.register_policy_hook, event, fn)

    def choose_movement(self, state, player):
        return self._call(self._policy.choose_movement, state, player)

    def choose_draft_card(self, state, player, offered_cards):
        return self._call(self._policy.choose_draft_card, state, player, offered_cards)

    def choose_final_character(self, state, player, card_choices):
        return self._call(self._policy.choose_final_character, state, player, card_choices)

    def choose_lap_reward(self, state, player):
        return self._call(self._policy.choose_lap_reward, state, player)

    def choose_trick_to_use(self, state, player, hand):
        return self._call(self._policy.choose_trick_to_use, state, player, hand)

    def choose_hidden_trick_card(self, state, player, hand):
        return self._call(self._policy.choose_hidden_trick_card, state, player, hand)

    def choose_mark_target(self, state, player, actor_name):
        return self._call(self._policy.choose_mark_target, state, player, actor_name)

    def choose_coin_placement_tile(self, state, player):
        return self._call(self._policy.choose_coin_placement_tile, state, player)

    def choose_geo_bonus(self, state, player, char):
        return self._call(self._policy.choose_geo_bonus, state, player, char)

    def choose_doctrine_relief_target(self, state, player, candidates):
        return self._call(self._policy.choose_doctrine_relief_target, state, player, candidates)

    def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):
        if hasattr(self._policy, "choose_purchase_tile"):
            return self._call(self._policy.choose_purchase_tile, state, player, pos, cell, cost, source=source)
        return True

    def choose_specific_trick_reward(self, state, player, choices):
        if hasattr(self._policy, "choose_specific_trick_reward"):
            return self._call(self._policy.choose_specific_trick_reward, state, player, choices)
        return None

    def choose_burden_exchange_on_supply(self, state, player, card):
        if hasattr(self._policy, "choose_burden_exchange_on_supply"):
            return self._call(self._policy.choose_burden_exchange_on_supply, state, player, card)
        return True

    def choose_active_flip_card(self, state, player, flippable_cards):
        if hasattr(self._policy, "choose_active_flip_card"):
            return self._call(self._policy.choose_active_flip_card, state, player, flippable_cards)
        return None
