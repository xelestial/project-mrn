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

# ---------------------------------------------------------------------------
# Timeout for waiting on browser input (seconds)
# ---------------------------------------------------------------------------
TIMEOUT_S = 300.0  # 5 minutes


class HumanHttpPolicy:
    """Policy that blocks for human input on the designated seat.

    Parameters
    ----------
    human_seat:
        player_id of the human player (0-based).
    ai_fallback:
        Policy instance used for AI players and non-interactive decisions.
    """

    def __init__(self, human_seat: int, ai_fallback: Any) -> None:
        self._seat = human_seat
        self._ai = ai_fallback
        self._lock = threading.Lock()
        self._pending: dict | None = None          # current prompt waiting for input
        self._response_queue: queue.Queue = queue.Queue(maxsize=1)

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
        if player.player_id != self._seat:
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

        prompt = {
            "type": "movement",
            "player_id": player.player_id,
            "options": options,
            "player_cash": player.cash,
            "player_position": player.position,
        }

        def _parse(r: dict):
            sel = r.get("option_id", "dice")
            for opt in options:
                if opt["id"] == sel:
                    return MovementDecision(
                        use_cards=opt["use_cards"],
                        card_values=tuple(opt["card_values"]),
                    )
            return MovementDecision(use_cards=False, card_values=())

        return self._ask(prompt, _parse, lambda: self._ai.choose_movement(state, player))

    # ------------------------------------------------------------------
    # choose_lap_reward
    # ------------------------------------------------------------------

    def choose_lap_reward(self, state: Any, player: Any) -> Any:
        if player.player_id != self._seat:
            return self._ai.choose_lap_reward(state, player)

        from ai_policy import LapRewardDecision

        rules = state.config.rules.lap_reward
        cash_pool = int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool))
        shards_pool = int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool))
        coins_pool = int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool))

        # Compute max units for each type
        budget = rules.points_budget
        max_cash = min(cash_pool, budget // max(1, rules.cash_point_cost))
        max_shards = min(shards_pool, budget // max(1, rules.shards_point_cost))
        max_coins = min(coins_pool, budget // max(1, rules.coins_point_cost))

        options = []
        if max_cash > 0:
            options.append({
                "id": "cash", "label": f"Cash (+{max_cash})",
                "choice": "cash", "cash_units": max_cash, "shard_units": 0, "coin_units": 0,
            })
        if max_shards > 0:
            options.append({
                "id": "shards", "label": f"Shards (+{max_shards})",
                "choice": "shards", "cash_units": 0, "shard_units": max_shards, "coin_units": 0,
            })
        if max_coins > 0:
            options.append({
                "id": "coins", "label": f"Coins (+{max_coins})",
                "choice": "coins", "cash_units": 0, "shard_units": 0, "coin_units": max_coins,
            })

        if not options:
            return LapRewardDecision(choice="blocked")

        prompt = {
            "type": "lap_reward",
            "player_id": player.player_id,
            "options": options,
            "budget": budget,
            "pools": {"cash": cash_pool, "shards": shards_pool, "coins": coins_pool},
        }

        def _parse(r: dict):
            sel = r.get("option_id", options[0]["id"])
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
        if player.player_id != self._seat:
            return self._ai.choose_draft_card(state, player, offered_cards)

        options = []
        for card_index in offered_cards:
            # card_index is an int index into the characters config
            char_name = _card_name(state, card_index)
            options.append({
                "id": str(card_index),
                "label": char_name,
                "card_index": card_index,
            })

        prompt = {
            "type": "draft_card",
            "player_id": player.player_id,
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id")
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
        if player.player_id != self._seat:
            return self._ai.choose_final_character(state, player, card_choices)

        options = []
        for name in card_choices:
            options.append({"id": name, "label": name})

        prompt = {
            "type": "final_character",
            "player_id": player.player_id,
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id")
            if sel in card_choices:
                return sel
            return self._ai.choose_final_character(state, player, card_choices)

        return self._ask(prompt, _parse, lambda: self._ai.choose_final_character(state, player, card_choices))

    # ------------------------------------------------------------------
    # choose_trick_to_use
    # ------------------------------------------------------------------

    def choose_trick_to_use(self, state: Any, player: Any, hand: Any) -> Any:
        if player.player_id != self._seat:
            return self._ai.choose_trick_to_use(state, player, hand)

        options = [{"id": "none", "label": "Skip (no trick)", "deck_index": None}]
        for card in hand:
            options.append({
                "id": str(card.deck_index),
                "label": card.name,
                "deck_index": card.deck_index,
            })

        prompt = {
            "type": "trick_to_use",
            "player_id": player.player_id,
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id", "none")
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
        if player.player_id != self._seat:
            return self._ai.choose_purchase_tile(state, player, pos, cell, cost, source=source)

        tile = state.tiles[pos]
        prompt = {
            "type": "purchase_tile",
            "player_id": player.player_id,
            "options": [
                {"id": "yes", "label": f"Buy tile {pos} (cost {cost})", "value": True},
                {"id": "no",  "label": "Skip purchase", "value": False},
            ],
            "tile_index": pos,
            "tile_zone": tile.zone_color,
            "cost": cost,
            "player_cash": player.cash,
            "source": source,
        }

        def _parse(r: dict):
            return r.get("option_id", "yes") == "yes"

        return self._ask(prompt, _parse, lambda: self._ai.choose_purchase_tile(state, player, pos, cell, cost, source=source))

    # ------------------------------------------------------------------
    # choose_hidden_trick_card
    # ------------------------------------------------------------------

    def choose_hidden_trick_card(self, state: Any, player: Any, hand: Any) -> Any:
        if player.player_id != self._seat:
            return self._ai.choose_hidden_trick_card(state, player, hand)

        if not hand:
            return None

        options = [{"id": "none", "label": "Hide nothing", "deck_index": None}]
        for card in hand:
            options.append({
                "id": str(card.deck_index),
                "label": card.name,
                "deck_index": card.deck_index,
            })

        prompt = {
            "type": "hidden_trick_card",
            "player_id": player.player_id,
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id", "none")
            if sel == "none":
                return None
            for card in hand:
                if str(card.deck_index) == sel:
                    return card
            return None

        return self._ask(prompt, _parse, lambda: self._ai.choose_hidden_trick_card(state, player, hand))

    # ------------------------------------------------------------------
    # choose_mark_target
    # ------------------------------------------------------------------

    def choose_mark_target(self, state: Any, player: Any, actor_name: Any) -> Any:
        if player.player_id != self._seat:
            return self._ai.choose_mark_target(state, player, actor_name)

        alive = [p for p in state.players if p.alive and p.player_id != player.player_id]
        options = [{"id": "none", "label": "No target"}]
        for p in alive:
            options.append({"id": str(p.player_id), "label": f"Player {p.player_id}"})

        prompt = {
            "type": "mark_target",
            "player_id": player.player_id,
            "actor_name": str(actor_name),
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id", "none")
            if sel == "none":
                return None
            try:
                return int(sel)
            except ValueError:
                return None

        return self._ask(prompt, _parse, lambda: self._ai.choose_mark_target(state, player, actor_name))

    # ------------------------------------------------------------------
    # choose_coin_placement_tile
    # ------------------------------------------------------------------

    def choose_coin_placement_tile(self, state: Any, player: Any) -> Any:
        if player.player_id != self._seat:
            return self._ai.choose_coin_placement_tile(state, player)

        owned = [
            idx for idx, owner in enumerate(state.tile_owner)
            if owner == player.player_id
        ]
        if not owned:
            return None

        options = [{"id": str(idx), "label": f"Tile {idx}", "tile_index": idx} for idx in owned]

        prompt = {
            "type": "coin_placement",
            "player_id": player.player_id,
            "options": options,
        }

        def _parse(r: dict):
            sel = r.get("option_id")
            if sel is not None:
                try:
                    return int(sel)
                except ValueError:
                    pass
            return self._ai.choose_coin_placement_tile(state, player)

        return self._ask(prompt, _parse, lambda: self._ai.choose_coin_placement_tile(state, player))

    # ------------------------------------------------------------------
    # Fully AI-delegated decisions
    # ------------------------------------------------------------------

    def choose_geo_bonus(self, state: Any, player: Any, char: Any) -> Any:
        return self._ai.choose_geo_bonus(state, player, char)

    def choose_doctrine_relief_target(self, state: Any, player: Any, candidates: Any) -> Any:
        return self._ai.choose_doctrine_relief_target(state, player, candidates)

    def choose_active_flip_card(self, state: Any, player: Any, flippable_cards: Any) -> Any:
        return self._ai.choose_active_flip_card(state, player, flippable_cards)

    def choose_specific_trick_reward(self, state: Any, player: Any, choices: Any) -> Any:
        return self._ai.choose_specific_trick_reward(state, player, choices)

    def choose_burden_exchange_on_supply(self, state: Any, player: Any, card: Any) -> bool:
        return self._ai.choose_burden_exchange_on_supply(state, player, card)

    def should_attempt_swindle(self, state: Any, player: Any, pos: Any, owner: Any, required_cost: Any) -> bool:
        if hasattr(self._ai, "should_attempt_swindle"):
            return self._ai.should_attempt_swindle(state, player, pos, owner, required_cost)
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ai, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_name(state: Any, card_index: int) -> str:
    """Try to resolve a character card index to a display name."""
    try:
        chars = state.config.characters
        if hasattr(chars, "card_name"):
            return chars.card_name(card_index)
        names = list(state.active_by_card.values())
        if card_index < len(names):
            return names[card_index] or f"Card {card_index}"
    except Exception:
        pass
    return f"Card {card_index}"
