"""Phase 4 — Human HTTP Policy.

Wraps HeuristicPolicy so that one designated player seat blocks on browser
input for key decisions.  All other players (and any unimplemented decision
types) fall back silently to the AI.

Thread-safety model
-------------------
* The game engine runs in a daemon thread (_run_game).
* Each blocking choose_* call:
    1. Puts a prompt dict into self._pending (visible to HTTP handler via GET /prompt).
    2. Blocks on self._response_queue.get(timeout=TIMEOUT_S).
    3. Parses the response; on timeout / parse error falls back to AI.
    4. Clears self._pending after reading the response.
"""
from __future__ import annotations

import queue
import threading
from itertools import combinations
from typing import Any, Optional

from viewer.prompt_contract import build_prompt_envelope, extract_choice_id

# ---------------------------------------------------------------------------
# Timeout for waiting on browser input (seconds)
# ---------------------------------------------------------------------------
TIMEOUT_S = 300.0  # 5 minutes


def _lap_reward_choice_id(cash_units: int, shard_units: int, coin_units: int) -> str:
    return f"cash-{cash_units}_shards-{shard_units}_coins-{coin_units}"


class HumanHttpPolicy:
    """Policy that blocks for human input on one or more designated seats.

    Parameters
    ----------
    human_seat / human_seats:
        player_id of the human player (0-based), or a collection of such seats.
    ai_fallback:
        Policy instance used for AI players and non-interactive decisions.
    """

    def __init__(
        self,
        human_seat: int | None,
        ai_fallback: Any,
        human_seats: list[int] | tuple[int, ...] | set[int] | None = None,
    ) -> None:
        seats = set(int(seat) for seat in (human_seats or ([] if human_seat is None else [human_seat])))
        if not seats:
            raise ValueError("HumanHttpPolicy requires at least one human seat")
        self._seats = frozenset(seats)
        self._ai = ai_fallback
        self._lock = threading.Lock()
        self._pending: dict | None = None          # current prompt waiting for input
        self._response_queue: queue.Queue = queue.Queue(maxsize=1)
        self._prompt_seq = 0
        self._active_flip_seen_cards_by_owner: dict[int, set[int]] = {}

    def _is_human_seat(self, player_id: int) -> bool:
        return player_id in self._seats

    # ------------------------------------------------------------------
    # Prompt state (read by HTTP handler)
    # ------------------------------------------------------------------

    @property
    def pending_prompt(self) -> dict | None:
        """Return current prompt or None if no decision is pending."""
        with self._lock:
            return self._pending

    def submit_response(self, response: dict) -> bool:
        """Called by HTTP handler when browser POSTs a decision.

        Returns True if response was accepted, False if no prompt pending.

        The check-and-put is performed under the same lock to prevent a
        race where a timeout clears _pending between the check and the put,
        causing the old response to be consumed by the next question.
        """
        with self._lock:
            if self._pending is None:
                return False
            try:
                self._response_queue.put_nowait(response)
                return True
            except queue.Full:
                return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ask(self, prompt: dict, parser, fallback_fn):
        """Set prompt, block for response, parse, or fall back on timeout."""
        self._prompt_seq += 1
        prompt = dict(prompt)
        prompt["prompt_instance_id"] = self._prompt_seq
        with self._lock:
            self._pending = prompt
        try:
            response = self._response_queue.get(timeout=TIMEOUT_S)
        except queue.Empty:
            response = None
        finally:
            with self._lock:
                self._pending = None

        if response is None:
            return fallback_fn()
        try:
            return parser(response)
        except Exception:
            return fallback_fn()

    @staticmethod
    def _remaining_cards(player: Any) -> list[int]:
        return [v for v in range(1, 7) if v not in player.used_dice_cards]

    # ------------------------------------------------------------------
    # choose_movement
    # ------------------------------------------------------------------

    def choose_movement(self, state: Any, player: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_movement(state, player)

        from ai_policy import MovementDecision

        remaining = self._remaining_cards(player)

        # Build the set of options the human can pick
        options = [{"id": "dice", "label": "Roll dice", "use_cards": False, "card_values": []}]
        for v in remaining:
            options.append({
                "id": f"card_{v}",
                "label": f"Use card [{v}]",
                "use_cards": True,
                "card_values": [v],
            })
        for a, b in combinations(remaining, 2):
            options.append({
                "id": f"card_{a}_{b}",
                "label": f"Use cards [{a}+{b}={a+b}]",
                "use_cards": True,
                "card_values": [a, b],
            })

        legal_choices = [
            {
                "choice_id": opt["id"],
                "label": opt["label"],
                "value": {
                    "use_cards": opt["use_cards"],
                    "card_values": list(opt["card_values"]),
                },
            }
            for opt in options
        ]
        prompt = build_prompt_envelope(
            request_type="movement",
            player_id=player.player_id + 1,
            legal_choices=legal_choices,
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
            },
            can_pass=False,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "dice")
            for opt in options:
                if opt["id"] == sel:
                    return MovementDecision(
                        use_cards=opt["use_cards"],
                        card_values=tuple(opt["card_values"]),
                    )
            return MovementDecision(use_cards=False, card_values=())

        return self._ask(prompt, _parse, lambda: self._ai.choose_movement(state, player))

    def choose_runaway_slave_step(
        self,
        state: Any,
        player: Any,
        one_short_pos: int,
        bonus_target_pos: int,
        bonus_target_kind: Any,
    ) -> bool:
        ai_fallback = getattr(self._ai, "choose_runaway_slave_step", None)
        if callable(ai_fallback):
            fallback_fn = lambda: bool(
                ai_fallback(state, player, one_short_pos, bonus_target_pos, bonus_target_kind)
            )
        else:
            fallback_fn = lambda: True
        if not self._is_human_seat(player.player_id):
            return fallback_fn()

        kind_name = getattr(bonus_target_kind, "name", str(bonus_target_kind))
        options = [
            {
                "id": "take_bonus",
                "label": f"+1 적용: {bonus_target_pos}칸({kind_name})으로 이동",
                "value": {"take_bonus": True},
            },
            {
                "id": "stay",
                "label": f"유지: {one_short_pos}칸에 정지",
                "value": {"take_bonus": False},
            },
        ]
        prompt = build_prompt_envelope(
            request_type="runaway_step_choice",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": dict(opt["value"]),
                }
                for opt in options
            ],
            public_context={
                "player_position": player.position,
                "one_short_pos": one_short_pos,
                "bonus_target_pos": bonus_target_pos,
                "bonus_target_kind": kind_name,
            },
            can_pass=False,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "take_bonus")
            for opt in options:
                if opt["id"] == sel:
                    return bool(opt["value"]["take_bonus"])
            return True

        return bool(self._ask(prompt, _parse, fallback_fn))

    # ------------------------------------------------------------------
    # choose_lap_reward
    # ------------------------------------------------------------------

    def choose_lap_reward(self, state: Any, player: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_lap_reward(state, player)

        from ai_policy import LapRewardDecision

        rules = state.config.rules.lap_reward
        cash_pool = int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool))
        shards_pool = int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool))
        coins_pool = int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool))

        budget = rules.points_budget
        max_cash = min(cash_pool, budget // max(1, rules.cash_point_cost))
        max_shards = min(shards_pool, budget // max(1, rules.shards_point_cost))
        max_coins = min(coins_pool, budget // max(1, rules.coins_point_cost))

        options = []
        for cash_units in range(0, max_cash + 1):
            cash_points = cash_units * int(rules.cash_point_cost)
            if cash_points > budget:
                break
            shard_cap = min(shards_pool, (budget - cash_points) // max(1, int(rules.shards_point_cost)))
            for shard_units in range(0, shard_cap + 1):
                spent = cash_points + shard_units * int(rules.shards_point_cost)
                coin_cap = min(coins_pool, (budget - spent) // max(1, int(rules.coins_point_cost)))
                for coin_units in range(0, coin_cap + 1):
                    total_points = spent + coin_units * int(rules.coins_point_cost)
                    if total_points <= 0 or total_points > budget:
                        continue
                    choice = "mixed"
                    if cash_units > 0 and shard_units == 0 and coin_units == 0:
                        choice = "cash"
                    elif shard_units > 0 and cash_units == 0 and coin_units == 0:
                        choice = "shards"
                    elif coin_units > 0 and cash_units == 0 and shard_units == 0:
                        choice = "coins"
                    label_parts: list[str] = []
                    if cash_units > 0:
                        label_parts.append(f"Cash +{cash_units}")
                    if shard_units > 0:
                        label_parts.append(f"Shards +{shard_units}")
                    if coin_units > 0:
                        label_parts.append(f"Coins +{coin_units}")
                    options.append(
                        {
                            "id": _lap_reward_choice_id(cash_units, shard_units, coin_units),
                            "label": " / ".join(label_parts),
                            "choice": choice,
                            "cash_units": cash_units,
                            "shard_units": shard_units,
                            "coin_units": coin_units,
                            "spent_points": total_points,
                        }
                    )
        options.sort(
            key=lambda item: (
                int(item["spent_points"]),
                int(item["cash_units"]),
                int(item["shard_units"]),
                int(item["coin_units"]),
            ),
            reverse=True,
        )

        if not options:
            return LapRewardDecision(choice="blocked")

        legal_choices = [
            {
                "choice_id": opt["id"],
                "label": opt["label"],
                "value": {
                    "choice": opt["choice"],
                    "cash_units": opt["cash_units"],
                    "shard_units": opt["shard_units"],
                    "coin_units": opt["coin_units"],
                    "spent_points": opt["spent_points"],
                    "points_budget": budget,
                },
            }
            for opt in options
        ]
        prompt = build_prompt_envelope(
            request_type="lap_reward",
            player_id=player.player_id + 1,
            legal_choices=legal_choices,
            public_context={
                "budget": budget,
                "pools": {"cash": cash_pool, "shards": shards_pool, "coins": coins_pool},
                "cash_point_cost": int(rules.cash_point_cost),
                "shards_point_cost": int(rules.shards_point_cost),
                "coins_point_cost": int(rules.coins_point_cost),
                "player_cash": player.cash,
                "player_shards": player.shards,
                "player_hand_coins": getattr(player, "hand_coins", 0),
                "player_placed_coins": getattr(player, "score_coins_placed", 0),
                "player_total_score": int(getattr(player, "hand_coins", 0) or 0) + int(getattr(player, "score_coins_placed", 0) or 0),
                "player_owned_tile_count": getattr(player, "tiles_owned", 0),
            },
            can_pass=False,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, options[0]["id"])
            for opt in options:
                if opt["id"] == sel:
                    return LapRewardDecision(
                        choice=opt["choice"],
                        cash_units=opt["cash_units"],
                        shard_units=opt["shard_units"],
                        coin_units=opt["coin_units"],
                    )
            return self._ai.choose_lap_reward(state, player)

        return self._ask(prompt, _parse, lambda: self._ai.choose_lap_reward(state, player))

    # ------------------------------------------------------------------
    # choose_draft_card
    # ------------------------------------------------------------------

    def choose_draft_card(self, state: Any, player: Any, offered_cards: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_draft_card(state, player, offered_cards)

        options = []
        for card_index in offered_cards:
            # card_index is an int index into the characters config
            char_name = _card_name(state, card_index)
            ability_text = _character_ability_text(char_name)
            options.append({
                "id": str(card_index),
                "label": char_name,
                "card_index": card_index,
                "character_name": char_name,
                "character_ability": ability_text,
            })

        prompt = build_prompt_envelope(
            request_type="draft_card",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "description": opt["character_ability"],
                    "value": {
                        "card_index": opt["card_index"],
                        "character_name": opt["character_name"],
                        "character_ability": opt["character_ability"],
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "offered_count": len(options),
                "offered_names": [opt["label"] for opt in options],
                "offered_abilities": [opt["character_ability"] for opt in options],
                "draft_phase": len(list(getattr(player, "drafted_cards", []) or [])) + 1,
                "draft_phase_label": f"draft_phase_{len(list(getattr(player, 'drafted_cards', []) or [])) + 1}",
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                for opt in options:
                    if opt["id"] == sel:
                        return opt["card_index"]
            return self._ai.choose_draft_card(state, player, offered_cards)

        return self._ask(prompt, _parse, lambda: self._ai.choose_draft_card(state, player, offered_cards))

    # ------------------------------------------------------------------
    # choose_final_character
    # ------------------------------------------------------------------

    def choose_final_character(self, state: Any, player: Any, card_choices: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_final_character(state, player, card_choices)

        options = []
        for card_index in card_choices:
            char_name = _card_name(state, card_index)
            ability_text = _character_ability_text(char_name)
            options.append({
                "id": str(card_index),
                "label": char_name,
                "card_index": card_index,
                "character_name": char_name,
                "character_ability": ability_text,
            })

        prompt = build_prompt_envelope(
            request_type="final_character",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "description": opt["character_ability"],
                    "value": {
                        "card_index": opt["card_index"],
                        "character_name": opt["character_name"],
                        "character_ability": opt["character_ability"],
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "choice_count": len(options),
                "choice_names": [opt["label"] for opt in options],
                "choice_abilities": [opt["character_ability"] for opt in options],
                "final_choice": True,
                "decision_phase_label": "final_character_confirmation",
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                for opt in options:
                    if opt["id"] == str(sel):
                        return opt["character_name"]
            return self._ai.choose_final_character(state, player, card_choices)

        return self._ask(prompt, _parse, lambda: self._ai.choose_final_character(state, player, card_choices))

    # ------------------------------------------------------------------
    # choose_trick_to_use
    # ------------------------------------------------------------------

    def choose_trick_to_use(self, state: Any, player: Any, hand: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_trick_to_use(state, player, hand)

        full_hand_cards = list(getattr(player, "trick_hand", []) or list(hand))
        # Rule alignment (2026-04): trick cards are limited to one per turn.
        trick_phase = "regular"
        usable_deck_indices = {getattr(card, "deck_index", None) for card in hand}
        hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
        full_hand_context = [
            {
                "deck_index": getattr(card, "deck_index", None),
                "name": getattr(card, "name", str(card)),
                "card_description": getattr(card, "description", ""),
                "is_hidden": (hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index),
                "is_usable": getattr(card, "deck_index", None) in usable_deck_indices,
            }
            for card in full_hand_cards
        ]

        options = [{"id": "none", "label": "이번에는 잔꾀를 사용하지 않음", "deck_index": None}]
        for card in hand:
            options.append({
                "id": str(card.deck_index),
                "label": card.name,
                "deck_index": card.deck_index,
                "card_description": getattr(card, "description", ""),
            })

        prompt = build_prompt_envelope(
            request_type="trick_to_use",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {
                        "deck_index": opt["deck_index"],
                        "card_description": opt.get("card_description", ""),
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "hand_count": len(hand),
                "usable_hand_count": len(hand),
                "total_hand_count": len(full_hand_context),
                "hidden_trick_count": sum(1 for item in full_hand_context if item.get("is_hidden")),
                "hidden_trick_deck_index": hidden_deck_index,
                "hand_names": [item["name"] for item in full_hand_context],
                "full_hand": full_hand_context,
                "trick_phase": trick_phase,
            },
            can_pass=True,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "none")
            if sel == "none":
                return None
            for card in hand:
                if str(card.deck_index) == sel:
                    return card
            return None

        return self._ask(prompt, _parse, lambda: self._ai.choose_trick_to_use(state, player, hand))

    # ------------------------------------------------------------------
    # choose_purchase_tile
    # ------------------------------------------------------------------

    def choose_purchase_tile(
        self, state: Any, player: Any, pos: Any, cell: Any, cost: Any, *, source: str = "landing"
    ) -> bool:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_purchase_tile(state, player, pos, cell, cost, source=source)

        tile = state.tiles[pos]
        prompt = build_prompt_envelope(
            request_type="purchase_tile",
            player_id=player.player_id + 1,
            legal_choices=[
                {"choice_id": "yes", "label": f"{pos}번 칸 구매 (비용 {cost})", "value": True},
                {"choice_id": "no", "label": "구매 없이 턴 종료", "value": False},
            ],
            public_context={
                "tile_index": pos,
                "tile_zone": tile.zone_color,
                "tile_kind": getattr(tile.kind, "name", None),
                "tile_purchase_cost": tile.purchase_cost,
                "tile_rent_cost": tile.rent_cost,
                "tile_score_coins": tile.score_coins,
                "cost": cost,
                "player_cash": player.cash,
                "source": source,
            },
            can_pass=True,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            return extract_choice_id(r, "yes") == "yes"

        return self._ask(prompt, _parse, lambda: self._ai.choose_purchase_tile(state, player, pos, cell, cost, source=source))

    # ------------------------------------------------------------------
    # choose_hidden_trick_card
    # ------------------------------------------------------------------

    def choose_hidden_trick_card(self, state: Any, player: Any, hand: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_hidden_trick_card(state, player, hand)

        if not hand:
            return None

        options = []
        hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
        full_hand_cards = list(getattr(player, "trick_hand", []) or list(hand))
        usable_deck_indices = {getattr(card, "deck_index", None) for card in hand}
        for card in hand:
            options.append({
                "id": str(card.deck_index),
                "label": card.name,
                "deck_index": card.deck_index,
                "card_description": getattr(card, "description", ""),
            })

        prompt = build_prompt_envelope(
            request_type="hidden_trick_card",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {
                        "deck_index": opt["deck_index"],
                        "card_description": opt.get("card_description", ""),
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "hand_count": len(hand),
                "hand_names": [getattr(card, "name", str(card)) for card in hand],
                "full_hand": [
                    {
                        "deck_index": getattr(card, "deck_index", None),
                        "name": getattr(card, "name", str(card)),
                        "card_description": getattr(card, "description", ""),
                        "is_hidden": (
                            hidden_deck_index is not None
                            and getattr(card, "deck_index", None) == hidden_deck_index
                        ),
                        "is_usable": getattr(card, "deck_index", None) in usable_deck_indices,
                    }
                    for card in full_hand_cards
                ],
                "selection_required": True,
            },
            can_pass=False,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            for card in hand:
                if str(card.deck_index) == sel:
                    return card
            return self._ai.choose_hidden_trick_card(state, player, hand)

        return self._ask(prompt, _parse, lambda: self._ai.choose_hidden_trick_card(state, player, hand))

    # ------------------------------------------------------------------
    # choose_mark_target
    # ------------------------------------------------------------------

    def choose_mark_target(self, state: Any, player: Any, actor_name: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_mark_target(state, player, actor_name)

        if _is_mark_skill_blocked_by_uhsa(state, player, actor_name):
            return None

        legal_targets = _legal_mark_target_players(state, player)
        if not legal_targets:
            return None

        options = [{"id": "none", "label": "지목 안 함", "target_character": None, "target_player_id": None}]
        for target in legal_targets:
            target_character = str(getattr(target, "current_character", "") or "")
            target_player_id = int(getattr(target, "player_id", -1))
            if not target_character or target_player_id < 0:
                continue
            options.append(
                {
                    "id": str(target_player_id),
                    "label": f"{target_character} / P{target_player_id + 1}",
                    "target_character": target_character,
                    "target_player_id": target_player_id + 1,
                }
            )

        prompt = build_prompt_envelope(
            request_type="mark_target",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": None
                    if opt["id"] == "none"
                    else {
                        "target_character": opt["target_character"],
                        "target_player_id": opt["target_player_id"],
                    },
                }
                for opt in options
            ],
            public_context={
                "actor_name": str(actor_name),
                "player_cash": player.cash,
                "player_position": player.position,
                "target_count": len(options) - 1,
                "target_pairs": [
                    {
                        "target_character": opt["target_character"],
                        "target_player_id": opt["target_player_id"],
                    }
                    for opt in options
                    if opt["id"] != "none"
                ],
            },
            can_pass=True,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "none")
            if sel == "none":
                return None
            for opt in options:
                if opt["id"] == sel:
                    return opt["target_character"]
            return None

        return self._ask(prompt, _parse, lambda: self._ai.choose_mark_target(state, player, actor_name))

    # ------------------------------------------------------------------
    # choose_coin_placement_tile
    # ------------------------------------------------------------------

    def choose_coin_placement_tile(self, state: Any, player: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_coin_placement_tile(state, player)

        owned = [
            idx for idx, owner in enumerate(state.tile_owner)
            if owner == player.player_id
        ]
        if not owned:
            return None

        options = [{"id": str(idx), "label": f"{idx}번 칸", "tile_index": idx} for idx in owned]

        prompt = build_prompt_envelope(
            request_type="coin_placement",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {"tile_index": opt["tile_index"]},
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "owned_tile_indices": list(owned),
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                try:
                    return int(sel)
                except ValueError:
                    pass
            return self._ai.choose_coin_placement_tile(state, player)

        return self._ask(prompt, _parse, lambda: self._ai.choose_coin_placement_tile(state, player))

    # ------------------------------------------------------------------
    # choose_trick_tile_target
    # ------------------------------------------------------------------

    def choose_trick_tile_target(self, state: Any, player: Any, card_name: Any, candidate_tiles: Any, target_scope: str = "any") -> Any:
        candidate_indices = [int(idx) for idx in list(candidate_tiles or []) if isinstance(idx, int)]

        def _fallback_choice():
            if not candidate_indices:
                return None
            if target_scope == "owned_lowest":
                return sorted(
                    candidate_indices,
                    key=lambda idx: (getattr(state, "tile_coins", [0] * (idx + 1))[idx], idx),
                )[0]
            return sorted(
                candidate_indices,
                key=lambda idx: (
                    state.config.rules.economy.rent_cost_for(state, idx) if getattr(state.tile_at(idx), "purchase_cost", None) is not None else 0,
                    getattr(state, "tile_coins", [0] * (idx + 1))[idx],
                    idx,
                ),
                reverse=True,
            )[0]

        if not self._is_human_seat(player.player_id):
            ai_method = getattr(self._ai, "choose_trick_tile_target", None)
            return ai_method(state, player, card_name, candidate_indices, target_scope) if callable(ai_method) else _fallback_choice()

        if not candidate_indices:
            return None

        prompt = build_prompt_envelope(
            request_type="trick_tile_target",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": str(tile_index),
                    "label": f"{tile_index + 1}번 칸",
                    "value": {"tile_index": tile_index},
                }
                for tile_index in candidate_indices
            ],
            public_context={
                "card_name": str(card_name or ""),
                "candidate_count": len(candidate_indices),
                "candidate_tiles": list(candidate_indices),
                "target_scope": str(target_scope or "any"),
                "player_cash": player.cash,
                "player_position": player.position,
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                try:
                    return int(sel)
                except ValueError:
                    pass
            return _fallback_choice()

        return self._ask(prompt, _parse, _fallback_choice)

    # ------------------------------------------------------------------
    # Fully AI-delegated decisions
    # ------------------------------------------------------------------

    def choose_geo_bonus(self, state: Any, player: Any, char: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_geo_bonus(state, player, char)

        options = [
            {"id": "cash", "label": "현금 +1", "choice": "cash"},
            {"id": "shards", "label": "조각 +1", "choice": "shards"},
            {"id": "coins", "label": "승점 +1", "choice": "coins"},
        ]

        prompt = build_prompt_envelope(
            request_type="geo_bonus",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {"choice": opt["choice"]},
                }
                for opt in options
            ],
            public_context={
                "actor_name": str(char),
                "player_cash": player.cash,
                "player_position": player.position,
                "player_shards": player.shards,
                "player_hand_coins": getattr(player, "hand_coins", 0),
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "cash")
            for opt in options:
                if opt["id"] == sel:
                    return opt["choice"]
            return self._ai.choose_geo_bonus(state, player, char)

        return self._ask(prompt, _parse, lambda: self._ai.choose_geo_bonus(state, player, char))

    def choose_pabal_dice_mode(self, state: Any, player: Any) -> str:
        ai_fallback = getattr(self._ai, "choose_pabal_dice_mode", None)
        fallback_fn = (lambda: str(ai_fallback(state, player))) if callable(ai_fallback) else (lambda: "plus_one")
        if not self._is_human_seat(player.player_id):
            return fallback_fn()

        options = [
            {
                "id": "plus_one",
                "label": "Roll three dice",
                "description": "Use the courier front-side effect and add one die this turn.",
                "value": {"dice_mode": "plus_one"},
            },
            {
                "id": "minus_one",
                "label": "Roll one die",
                "description": "Use the courier back-side effect and reduce the roll to one die this turn.",
                "value": {"dice_mode": "minus_one"},
            },
        ]

        prompt = build_prompt_envelope(
            request_type="pabal_dice_mode",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {
                        "dice_mode": opt["value"]["dice_mode"],
                        "description": opt["description"],
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "player_shards": getattr(player, "shards", 0),
            },
            can_pass=False,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "plus_one")
            for opt in options:
                if opt["id"] == sel:
                    return opt["id"]
            return "plus_one"

        return str(self._ask(prompt, _parse, fallback_fn))

    def choose_doctrine_relief_target(self, state: Any, player: Any, candidates: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_doctrine_relief_target(state, player, candidates)

        options = []
        for target in candidates:
            burden_count = sum(1 for card in getattr(target, "trick_hand", []) if getattr(card, "is_burden", False))
            options.append({
                "id": str(target.player_id),
                "label": f"P{target.player_id + 1}",
                "target_player_id": target.player_id,
                "target_position": getattr(target, "position", None),
                "target_cash": getattr(target, "cash", None),
                "burden_count": burden_count,
            })

        prompt = build_prompt_envelope(
            request_type="doctrine_relief",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {
                        "target_player_id": opt["target_player_id"] + 1,
                        "target_position": opt["target_position"],
                        "target_cash": opt["target_cash"],
                        "burden_count": opt["burden_count"],
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "candidate_count": len(options),
                "candidate_labels": [opt["label"] for opt in options],
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                for opt in options:
                    if opt["id"] == sel:
                        return opt["target_player_id"]
            return self._ai.choose_doctrine_relief_target(state, player, candidates)

        return self._ask(prompt, _parse, lambda: self._ai.choose_doctrine_relief_target(state, player, candidates))

    def choose_active_flip_card(self, state: Any, player: Any, flippable_cards: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_active_flip_card(state, player, flippable_cards)
        if not flippable_cards:
            return None
        pending_owner_id = getattr(state, "pending_marker_flip_owner_id", None)
        marker_owner_id = getattr(state, "marker_owner_id", None)
        if pending_owner_id is not None and pending_owner_id != player.player_id:
            return None
        if marker_owner_id is not None and marker_owner_id != player.player_id:
            return None
        try:
            from characters import CARD_TO_NAMES

            all_flip_cards = list(CARD_TO_NAMES.keys())
        except Exception:
            all_flip_cards = list(flippable_cards)
        owner_seen = self._active_flip_seen_cards_by_owner.setdefault(player.player_id, set())
        if len(flippable_cards) >= len(all_flip_cards):
            owner_seen.clear()
        selectable_cards = [int(card_index) for card_index in flippable_cards if int(card_index) not in owner_seen]
        if not selectable_cards:
            owner_seen.clear()
            return None

        options = []
        options.append(
            {
                "id": "none",
                "label": "뒤집기 종료",
                "card_index": None,
                "current_name": "",
                "flipped_name": "",
            }
        )
        for card_index in selectable_cards:
            current_name, flipped_name = _flip_names(state, card_index)
            options.append({
                "id": str(card_index),
                "label": f"{current_name} -> {flipped_name}",
                "card_index": card_index,
                "current_name": current_name,
                "flipped_name": flipped_name,
            })

        prompt = build_prompt_envelope(
            request_type="active_flip",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": None
                    if opt["id"] == "none"
                    else {
                        "card_index": opt["card_index"],
                        "current_name": opt["current_name"],
                        "flipped_name": opt["flipped_name"],
                    },
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "flip_count": len(selectable_cards),
                "flip_labels": [opt["label"] for opt in options if opt["id"] != "none"],
                "already_flipped_count": len(owner_seen),
                "already_flipped_cards": sorted(owner_seen),
                "flip_limit": None,
                "flip_mode": "multi",
                "flip_trigger": "marker_owner_changed",
                "marker_owner_player_id": None if marker_owner_id is None else int(marker_owner_id) + 1,
                "pending_marker_flip_owner_id": None if pending_owner_id is None else int(pending_owner_id) + 1,
            },
            can_pass=True,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "none")
            if sel == "none":
                owner_seen.clear()
                return None
            if sel is not None:
                for opt in options:
                    if opt["id"] == sel:
                        if opt["card_index"] is not None:
                            owner_seen.add(int(opt["card_index"]))
                        return opt["card_index"]
            return self._ai.choose_active_flip_card(state, player, flippable_cards)

        return self._ask(prompt, _parse, lambda: self._ai.choose_active_flip_card(state, player, flippable_cards))

    def choose_specific_trick_reward(self, state: Any, player: Any, choices: Any) -> Any:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_specific_trick_reward(state, player, choices)

        options = [
            {
                "id": str(card.deck_index),
                "label": getattr(card, "name", f"Card {card.deck_index}"),
                "deck_index": card.deck_index,
            }
            for card in choices
        ]

        prompt = build_prompt_envelope(
            request_type="specific_trick_reward",
            player_id=player.player_id + 1,
            legal_choices=[
                {
                    "choice_id": opt["id"],
                    "label": opt["label"],
                    "value": {"deck_index": opt["deck_index"]},
                }
                for opt in options
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "reward_count": len(options),
                "reward_names": [opt["label"] for opt in options],
            },
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r)
            if sel is not None:
                for card in choices:
                    if str(card.deck_index) == sel:
                        return card
            return self._ai.choose_specific_trick_reward(state, player, choices)

        return self._ask(prompt, _parse, lambda: self._ai.choose_specific_trick_reward(state, player, choices))

    def choose_burden_exchange_on_supply(self, state: Any, player: Any, card: Any) -> bool:
        if not self._is_human_seat(player.player_id):
            return self._ai.choose_burden_exchange_on_supply(state, player, card)

        next_threshold = getattr(state, "next_supply_f_threshold", None)
        supply_threshold = next_threshold - 3 if isinstance(next_threshold, int) else None
        prompt = build_prompt_envelope(
            request_type="burden_exchange",
            player_id=player.player_id + 1,
            legal_choices=[
                {"choice_id": "yes", "label": f"{getattr(card, 'burden_cost', 0)}냥 지불 후 제거", "value": True},
                {"choice_id": "no", "label": "유지", "value": False},
            ],
            public_context={
                "player_cash": player.cash,
                "player_position": player.position,
                "card_name": getattr(card, "name", "Burden"),
                "card_description": getattr(card, "description", ""),
                "burden_cost": getattr(card, "burden_cost", 0),
                "burden_card_count": sum(1 for hand_card in getattr(player, "trick_hand", []) if getattr(hand_card, "is_burden", False)),
                "decision_phase": "trick_supply",
                "decision_reason": "supply_threshold",
                "supply_threshold": supply_threshold,
                "current_f_value": getattr(state, "f_value", 0),
                "player_shards": getattr(player, "shards", 0),
                "player_hand_coins": getattr(player, "hand_coins", 0),
            },
            can_pass=True,
            timeout_ms=int(TIMEOUT_S * 1000),
        )

        def _parse(r: dict):
            sel = extract_choice_id(r, "no")
            if sel == "yes":
                return True
            if sel == "no":
                return False
            return bool(self._ai.choose_burden_exchange_on_supply(state, player, card))

        return self._ask(prompt, _parse, lambda: bool(self._ai.choose_burden_exchange_on_supply(state, player, card)))

    def should_attempt_swindle(self, state: Any, player: Any, pos: Any, owner: Any, required_cost: Any) -> bool:
        if hasattr(self._ai, "should_attempt_swindle"):
            return self._ai.should_attempt_swindle(state, player, pos, owner, required_cost)
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ai, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _character_ability_text(character_name: str) -> str:
    try:
        from characters import CHARACTERS

        found = CHARACTERS.get(str(character_name))
        if found and getattr(found, "ability_text", ""):
            return str(found.ability_text)
    except Exception:
        pass
    return f"{character_name} 능력"


def _card_name(state: Any, card_index: int) -> str:
    """Try to resolve a character card index to a display name."""
    try:
        active = getattr(state, "active_by_card", None)
        if isinstance(active, dict):
            name = active.get(card_index)
            if name:
                return str(name)
        chars = state.config.characters
        if hasattr(chars, "card_name"):
            return chars.card_name(card_index)
        names = list(state.active_by_card.values())
        if card_index < len(names):
            return names[card_index] or f"Card {card_index}"
    except Exception:
        pass
    return f"Card {card_index}"


def _flip_names(state: Any, card_index: int) -> tuple[str, str]:
    try:
        from characters import CARD_TO_NAMES

        pair = CARD_TO_NAMES.get(card_index)
        if pair:
            current = getattr(state, "active_by_card", {}).get(card_index, pair[0])
            if current == pair[0]:
                return str(pair[0]), str(pair[1])
            return str(pair[1]), str(pair[0])
    except Exception:
        pass
    name = _card_name(state, card_index)
    return name, name


def _legal_mark_target_players(state: Any, player: Any) -> list[Any]:
    """Mirror engine/AI legality for mark targeting in human prompts."""

    try:
        order = list(getattr(state, "current_round_order", []) or [])
        my_idx = order.index(player.player_id)
        allowed_pids = set(order[my_idx + 1 :])
    except ValueError:
        allowed_pids = set()
    except Exception:
        allowed_pids = None

    out: list[Any] = []
    for target in getattr(state, "players", []):
        if not getattr(target, "alive", False):
            continue
        if getattr(target, "player_id", None) == player.player_id:
            continue
        if allowed_pids is not None and getattr(target, "player_id", None) not in allowed_pids:
            continue
        if not getattr(target, "current_character", None):
            continue
        if getattr(target, "revealed_this_round", False):
            continue
        out.append(target)
    return out


def _is_mark_skill_blocked_by_uhsa(state: Any, player: Any, actor_name: Any) -> bool:
    """Defensive check: mirror engine's Uhsa suppression for 무뢰 actors."""

    try:
        from characters import CARD_TO_NAMES, CHARACTERS

        uhsa_name = CARD_TO_NAMES[1][0]
        muroe_attribute = CHARACTERS[CARD_TO_NAMES[2][0]].attribute
        actor = CHARACTERS.get(str(actor_name))
        if actor is None or actor.attribute != muroe_attribute:
            return False
        return any(
            getattr(other, "alive", False)
            and getattr(other, "player_id", None) != player.player_id
            and getattr(other, "current_character", None) == uhsa_name
            for other in getattr(state, "players", [])
        )
    except Exception:
        return False
