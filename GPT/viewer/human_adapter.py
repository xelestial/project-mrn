from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_policy import HeuristicPolicy, LapRewardDecision, MovementDecision
from base_policy import BasePolicy
from characters import CARD_TO_NAMES
from config import CellKind
from state import GameState, PlayerState
from trick_cards import TrickCard

from .prompting import (
    PromptFileChannel,
    PromptResponseProvider,
    RuntimePromptChoice,
    RuntimePromptResponse,
    new_prompt,
)


class CLIResponseProvider:
    def get_response(self, prompt):
        print(f"\n[Human Prompt] P{prompt.player_id} {prompt.decision_type}")
        for choice in prompt.choices:
            print(f"  {choice.key}. {choice.label}")
        suffix = " (Enter=pass)" if prompt.can_pass else ""
        while True:
            raw = input(f"choice{suffix}> ").strip()
            if raw == "" and prompt.can_pass:
                return RuntimePromptResponse(prompt.prompt_id, None)
            valid = {choice.key for choice in prompt.choices}
            if raw in valid:
                return RuntimePromptResponse(prompt.prompt_id, raw)
            print(f"valid: {', '.join(sorted(valid))}")


@dataclass(slots=True)
class HumanAdapterConfig:
    human_players: set[int]


class HumanDecisionAdapter(BasePolicy):
    """BasePolicy implementation that opens RuntimePrompt objects for human seats.

    Non-human seats delegate to the wrapped AI policy.
    Trick-related decisions stay delegated for now because trick UI is still out of
    first playable scope.
    """

    def __init__(
        self,
        *,
        human_players: set[int],
        response_provider: PromptResponseProvider,
        prompt_channel: PromptFileChannel,
        ai_policy: BasePolicy | None = None,
    ) -> None:
        self.human_players = set(human_players)
        self.response_provider = response_provider
        self.prompt_channel = prompt_channel
        self.ai_policy = ai_policy or HeuristicPolicy(
            character_policy_mode="heuristic_v1",
            lap_policy_mode="heuristic_v1",
        )

    def _is_human(self, player: PlayerState) -> bool:
        return player.player_id + 1 in self.human_players

    def _delegate(self, method_name: str, *args, **kwargs):
        return getattr(self.ai_policy, method_name)(*args, **kwargs)

    def _resolve_prompt(self, prompt, *, allow_none: bool = False):
        self.prompt_channel.open_prompt(prompt)
        response = self.response_provider.get_response(prompt)
        self.prompt_channel.close_prompt(prompt, response)
        if response.choice_key is None and allow_none:
            return None
        choices_by_key = {choice.key: choice.value for choice in prompt.choices}
        return choices_by_key[response.choice_key]

    def choose_trick_to_use(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        return self._delegate("choose_trick_to_use", state, player, hand)

    def choose_specific_trick_reward(self, state: GameState, player: PlayerState, choices: list[TrickCard]) -> TrickCard | None:
        return self._delegate("choose_specific_trick_reward", state, player, choices)

    def choose_burden_exchange_on_supply(self, state: GameState, player: PlayerState, card: TrickCard) -> bool:
        if not self._is_human(player):
            return self._delegate("choose_burden_exchange_on_supply", state, player, card)
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="burden_exchange",
            choices=[
                RuntimePromptChoice("yes", f"exchange burden for {card.name}", True),
                RuntimePromptChoice("no", "skip exchange", False),
            ],
            public_context={"card_name": card.name, "burden_cost": card.burden_cost},
        )
        return self._resolve_prompt(prompt)

    def choose_hidden_trick_card(self, state: GameState, player: PlayerState, hand: list[TrickCard]) -> TrickCard | None:
        return self._delegate("choose_hidden_trick_card", state, player, hand)

    def choose_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, cost: int, *, source: str = "landing") -> bool:
        if not self._is_human(player):
            return self._delegate("choose_purchase_tile", state, player, pos, cell, cost, source=source)
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="purchase_decision",
            choices=[
                RuntimePromptChoice("yes", f"buy tile {pos} for {cost}", True),
                RuntimePromptChoice("no", "skip purchase", False),
            ],
            public_context={
                "tile_index": pos,
                "cell_kind": cell.name,
                "cost": cost,
                "cash": player.cash,
                "source": source,
            },
        )
        return self._resolve_prompt(prompt)

    def choose_movement(self, state: GameState, player: PlayerState) -> MovementDecision:
        if not self._is_human(player):
            return self._delegate("choose_movement", state, player)
        remaining = [v for v in state.config.dice_cards.values if v not in player.used_dice_cards]
        choices = [RuntimePromptChoice("0", "normal dice roll", MovementDecision(use_cards=False))]
        if remaining:
            for value in remaining:
                choices.append(
                    RuntimePromptChoice(
                        f"single:{value}",
                        f"use one card value {value}",
                        MovementDecision(use_cards=True, card_values=(value,)),
                    )
                )
        if len(remaining) >= 2:
            seen_pairs: set[tuple[int, int]] = set()
            for first in remaining:
                for second in remaining:
                    if second == first:
                        continue
                    pair = tuple(sorted((first, second)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    choices.append(
                        RuntimePromptChoice(
                            f"pair:{pair[0]}:{pair[1]}",
                            f"use pair cards {pair[0]} + {pair[1]}",
                            MovementDecision(use_cards=True, card_values=pair),
                        )
                    )
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="movement",
            choices=choices,
            public_context={
                "position": player.position,
                "available_dice_cards": remaining,
            },
        )
        return self._resolve_prompt(prompt)

    def choose_lap_reward(self, state: GameState, player: PlayerState) -> LapRewardDecision:
        if not self._is_human(player):
            return self._delegate("choose_lap_reward", state, player)
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="lap_reward",
            choices=[
                RuntimePromptChoice("cash", f"cash +{state.config.coins.lap_reward_cash}", LapRewardDecision(choice="cash")),
                RuntimePromptChoice("shards", f"shards +{state.config.shards.lap_reward_shards}", LapRewardDecision(choice="shards")),
                RuntimePromptChoice("coins", f"coins +{state.config.coins.lap_reward_coins}", LapRewardDecision(choice="coins")),
            ],
            public_context={"cash": player.cash, "shards": player.shards},
        )
        return self._resolve_prompt(prompt)

    def choose_coin_placement_tile(self, state: GameState, player: PlayerState) -> Optional[int]:
        if not self._is_human(player):
            return self._delegate("choose_coin_placement_tile", state, player)
        candidates = [
            idx
            for idx, owner in enumerate(state.tile_owner)
            if owner == player.player_id and state.tile_coins[idx] < state.config.coins.max_coins_per_tile
        ]
        choices = [RuntimePromptChoice(str(idx), f"tile {idx}", idx) for idx in candidates]
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="coin_placement",
            choices=choices,
            can_pass=True,
            public_context={"candidates": candidates},
        )
        return self._resolve_prompt(prompt, allow_none=True)

    def choose_draft_card(self, state: GameState, player: PlayerState, offered_cards: list[int]) -> int:
        if not self._is_human(player):
            return self._delegate("choose_draft_card", state, player, offered_cards)
        choices = [
            RuntimePromptChoice(str(idx), f"card {card_no}: {CARD_TO_NAMES[card_no][0]} / {CARD_TO_NAMES[card_no][1]}", card_no)
            for idx, card_no in enumerate(offered_cards, 1)
        ]
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="draft_choice",
            choices=choices,
            public_context={"offered_cards": offered_cards},
        )
        return self._resolve_prompt(prompt)

    def choose_final_character(self, state: GameState, player: PlayerState, card_choices: list[int]) -> str:
        if not self._is_human(player):
            return self._delegate("choose_final_character", state, player, card_choices)
        choices: list[RuntimePromptChoice] = []
        key_index = 1
        for card_no in card_choices:
            for name in CARD_TO_NAMES[card_no]:
                choices.append(
                    RuntimePromptChoice(
                        str(key_index),
                        f"{name} (card {card_no})",
                        name,
                    )
                )
                key_index += 1
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="character_choice",
            choices=choices,
            public_context={"drafted_cards": card_choices},
        )
        return self._resolve_prompt(prompt)

    def choose_mark_target(self, state: GameState, player: PlayerState, actor_name: str) -> Optional[str]:
        if not self._is_human(player):
            return self._delegate("choose_mark_target", state, player, actor_name)
        choices = []
        try:
            source_idx = state.current_round_order.index(player.player_id)
            future_ids = set(state.current_round_order[source_idx + 1 :])
        except ValueError:
            future_ids = set()
        for idx, candidate in enumerate(state.players, 1):
            if candidate.alive and candidate.player_id in future_ids:
                choices.append(
                    RuntimePromptChoice(
                        str(idx),
                        f"P{candidate.player_id + 1} {candidate.current_character}",
                        candidate.current_character,
                    )
                )
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="mark_target",
            choices=choices,
            can_pass=True,
            public_context={"actor_name": actor_name},
        )
        return self._resolve_prompt(prompt, allow_none=True)

    def choose_doctrine_relief_target(self, state: GameState, player: PlayerState, candidates: list[PlayerState]) -> Optional[int]:
        if not self._is_human(player):
            return self._delegate("choose_doctrine_relief_target", state, player, candidates)
        choices = [
            RuntimePromptChoice(
                str(candidate.player_id + 1),
                f"P{candidate.player_id + 1} {candidate.current_character or '-'}",
                candidate.player_id,
            )
            for candidate in candidates
        ]
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="doctrine_relief",
            choices=choices,
            can_pass=True,
            public_context={"candidate_ids": [candidate.player_id + 1 for candidate in candidates]},
        )
        return self._resolve_prompt(prompt, allow_none=True)

    def choose_geo_bonus(self, state: GameState, player: PlayerState, actor_name: str) -> str:
        if not self._is_human(player):
            return self._delegate("choose_geo_bonus", state, player, actor_name)
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="geo_bonus",
            choices=[
                RuntimePromptChoice("cash", "cash", "cash"),
                RuntimePromptChoice("shards", "shards", "shards"),
                RuntimePromptChoice("coins", "coins", "coins"),
            ],
            public_context={"actor_name": actor_name},
        )
        return self._resolve_prompt(prompt)

    def choose_active_flip_card(self, state: GameState, player: PlayerState, flippable_cards: list[int]) -> Optional[int]:
        if not self._is_human(player):
            return self._delegate("choose_active_flip_card", state, player, flippable_cards)
        choices = [
            RuntimePromptChoice(
                str(card_no),
                f"card {card_no}: {CARD_TO_NAMES[card_no][0]} / {CARD_TO_NAMES[card_no][1]}",
                card_no,
            )
            for card_no in flippable_cards
        ]
        prompt = new_prompt(
            player_id=player.player_id + 1,
            decision_type="active_flip",
            choices=choices,
            can_pass=True,
            public_context={"flippable_cards": flippable_cards},
        )
        return self._resolve_prompt(prompt, allow_none=True)
