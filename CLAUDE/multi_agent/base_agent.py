from __future__ import annotations
"""AbstractPlayerAgent — each player AI must satisfy this interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class AbstractPlayerAgent(ABC):
    """
    Per-player AI interface.
    All choose_* methods mirror the engine's policy call surface exactly.
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier, e.g. 'claude:v3_claude', 'gpt:v3_gpt'."""

    @abstractmethod
    def choose_movement(self, state: Any, player: Any) -> Any: ...

    @abstractmethod
    def choose_draft_card(self, state: Any, player: Any, offered_cards: list) -> int: ...

    @abstractmethod
    def choose_final_character(self, state: Any, player: Any, card_choices: list) -> str: ...

    @abstractmethod
    def choose_lap_reward(self, state: Any, player: Any) -> Any: ...

    @abstractmethod
    def choose_trick_to_use(self, state: Any, player: Any, hand: list) -> Any: ...

    @abstractmethod
    def choose_hidden_trick_card(self, state: Any, player: Any, hand: list) -> Any: ...

    @abstractmethod
    def choose_mark_target(self, state: Any, player: Any, actor_name: str) -> Optional[str]: ...

    @abstractmethod
    def choose_coin_placement_tile(self, state: Any, player: Any) -> Optional[int]: ...

    @abstractmethod
    def choose_geo_bonus(self, state: Any, player: Any, char: str) -> str: ...

    @abstractmethod
    def choose_doctrine_relief_target(self, state: Any, player: Any, candidates: list) -> Optional[int]: ...

    # Optional — checked via hasattr in engine/policy
    def choose_purchase_tile(self, state: Any, player: Any, pos: int, cell: Any, cost: int, *, source: str = "landing") -> bool:
        return True

    def choose_specific_trick_reward(self, state: Any, player: Any, choices: list) -> Any:
        return None

    def choose_burden_exchange_on_supply(self, state: Any, player: Any, card: Any) -> bool:
        return True

    def choose_active_flip_card(self, state: Any, player: Any, flippable_cards: list) -> Optional[int]:
        return None

    def set_rng(self, rng: Any) -> None:
        pass

    def register_policy_hook(self, event: str, fn: Any) -> None:
        pass
