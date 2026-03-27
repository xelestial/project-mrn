from __future__ import annotations

import random
import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import math

from ai_policy import BasePolicy, MovementDecision
from characters import CHARACTERS, CARD_TO_NAMES, randomized_active_by_card
from config import CellKind, GameConfig
from state import GameState, PlayerState
from fortune_cards import FortuneCard
from trick_cards import TrickCard
from weather_cards import WeatherCard, COLOR_RENT_DOUBLE_WEATHERS
from event_system import EventDispatcher
from effect_handlers import EngineEffectHandlers
from policy_hooks import PolicyDecisionLogHook
from rule_script_engine import RuleScriptEngine


@dataclass(slots=True)
class GameResult:
    winner_ids: List[int]
    end_reason: str
    total_turns: int
    rounds_completed: int
    alive_count: int
    bankrupt_players: int
    final_f_value: float
    total_placed_coins: int
    player_summary: List[dict] = field(default_factory=list)
    strategy_summary: List[dict] = field(default_factory=list)
    weather_history: List[str] = field(default_factory=list)
    action_log: List[dict] = field(default_factory=list)
    bankruptcy_events: List[dict] = field(default_factory=list)


class GameEngine:
    def __init__(self, config: GameConfig, policy: BasePolicy, rng: random.Random | None = None, enable_logging: bool = False):
        self.config = config
        self.policy = policy
        self.rng = rng or random.Random()
        if hasattr(self.policy, "set_rng"):
            self.policy.set_rng(self.rng)
        self.enable_logging = enable_logging
        self._action_log: List[dict] = []
        self._strategy_stats: List[dict] = []
        self._weather_history: List[str] = []
        self._bankruptcy_events: List[dict] = []
        self._last_payment_attempt_by_player: dict[int, dict] = {}
        self._player_bankruptcy_info: dict[int, dict] = {}
        self._last_semantic_event_name: str | None = None
        self.events = EventDispatcher()
        self.events.set_trace_hook(self._trace_semantic_event)
        self.rule_scripts = RuleScriptEngine(self, getattr(config, "rule_scripts_path", None))
        self.effect_handlers = EngineEffectHandlers(self)
        self.effect_handlers.register_default_handlers(self.events)
        if hasattr(self.policy, "register_policy_hook"):
            decision_log_hook = PolicyDecisionLogHook(self)
            self.policy.register_policy_hook("policy.before_decision", decision_log_hook.before_decision)
            self.policy.register_policy_hook("policy.after_decision", decision_log_hook.after_decision)

    def run(self) -> GameResult:
        self._action_log = []
        self._weather_history = []
        self._bankruptcy_events = []
        self._last_payment_attempt_by_player = {}
        self._player_bankruptcy_info = {}
        self._last_semantic_event_name = None
        self._strategy_stats = [
            {
                "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                "rent_paid": 0, "own_tile_visits": 0,
                "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                "malicious_visits": 0, "bankruptcies": 0,
                "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                "tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0,
                "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                "coins_gained_own_tile": 0, "coins_placed": 0,
                "mark_attempts": 0, "mark_successes": 0,
                "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                "character": "", "shards_gained_f": 0, "shards_gained_lap": 0, "shard_income_cash": 0,
                "draft_cards": [], "marked_target_names": [],
            }
            for _ in range(self.config.player_count)
        ]
        state = GameState.create(self.config)
        self._initialize_active_faces(state)
        self.rng.shuffle(state.fortune_draw_pile)
        self.rng.shuffle(state.trick_draw_pile)
        self.rng.shuffle(state.weather_draw_pile)
        for p in state.players:
            self._draw_tricks(state, p, 5)
        self._log({
            "event": "initial_public_tricks",
            "players": [
                {"player": p.player_id + 1, "public_tricks": p.public_trick_names(), "hidden_trick_count": p.hidden_trick_count()}
                for p in state.players
            ],
        })
        self._start_new_round(state, initial=True)

        while True:
            current_pid = state.current_round_order[state.turn_index % len(state.current_round_order)]
            player = state.players[current_pid]
            if player.alive:
                player.turns_taken += 1
                self._take_turn(state, player)
                if self._check_end(state):
                    break
            state.turn_index += 1
            if state.turn_index % max(1, len(state.current_round_order)) == 0:
                state.rounds_completed += 1
                self._start_new_round(state, initial=False)
        return self._build_result(state)

    def _log(self, row: dict) -> None:
        if self.enable_logging:
            self._action_log.append(row)

    def _trace_semantic_event(self, event_name: str, args: tuple, kwargs: dict, results: list, mode: str) -> None:
        self._last_semantic_event_name = event_name
        if not self.enable_logging:
            return
        state = self._extract_state_from_event(args, kwargs)
        row = {
            "event": event_name,
            "event_kind": "semantic_event",
            "dispatch_mode": mode,
            "handler_count": len(results),
            "returned_non_none": any(result is not None for result in results),
            "args": [self._summarize_for_log(arg) for arg in args],
            "kwargs": {key: self._summarize_for_log(value) for key, value in kwargs.items()},
            "results": [self._summarize_for_log(result) for result in results],
        }
        if state is not None:
            row["round_index"] = state.rounds_completed + 1
            row["turn_index"] = state.turn_index
            row["f_value"] = state.f_value
        self._log(row)

    def _extract_state_from_event(self, args: tuple, kwargs: dict):
        for value in list(args) + list(kwargs.values()):
            if isinstance(value, GameState):
                return value
        return None

    def _summarize_for_log(self, value, depth: int = 0):
        if depth >= 2:
            if isinstance(value, (list, tuple, set, dict)):
                return f"<{type(value).__name__} len={len(value)}>"
            return repr(value)
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, Enum):
            return value.name
        if isinstance(value, GameState):
            return {
                "type": "GameState",
                "round_index": value.rounds_completed + 1,
                "turn_index": value.turn_index,
                "f_value": value.f_value,
                "current_weather": None if value.current_weather is None else value.current_weather.name,
            }
        if isinstance(value, PlayerState):
            return {
                "type": "PlayerState",
                "player": value.player_id + 1,
                "position": value.position,
                "cash": value.cash,
                "shards": value.shards,
                "alive": value.alive,
                "character": value.current_character,
            }
        if isinstance(value, (FortuneCard, TrickCard, WeatherCard)):
            return {
                "type": type(value).__name__,
                "name": value.name,
                "deck_index": value.deck_index,
            }
        if isinstance(value, dict):
            return {str(key): self._summarize_for_log(val, depth + 1) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            items = [self._summarize_for_log(item, depth + 1) for item in list(value)[:8]]
            if len(value) > 8:
                items.append(f"... (+{len(value) - 8} more)")
            return items
        if isinstance(value, set):
            seq = list(value)
            items = [self._summarize_for_log(item, depth + 1) for item in seq[:8]]
            if len(seq) > 8:
                items.append(f"... (+{len(seq) - 8} more)")
            return {"type": "set", "items": items}
        kind = getattr(value, "kind", None)
        if isinstance(kind, CellKind):
            return {
                "type": type(value).__name__,
                "index": getattr(value, "index", None),
                "kind": kind.name,
                "owner_id": getattr(value, "owner_id", None),
            }
        return repr(value)

    def _sync_trick_visibility(self, state: GameState, player: PlayerState) -> None:
        if not player.trick_hand:
            player.hidden_trick_deck_index = None
            return
        if any(c.deck_index == player.hidden_trick_deck_index for c in player.trick_hand):
            return
        chosen = None
        if hasattr(self.policy, "choose_hidden_trick_card"):
            chosen = self.policy.choose_hidden_trick_card(state, player, list(player.trick_hand))
        if chosen is not None and any(c.deck_index == chosen.deck_index for c in player.trick_hand):
            player.hidden_trick_deck_index = chosen.deck_index
            return
        player.hidden_trick_deck_index = self.rng.choice(player.trick_hand).deck_index

    def _public_trick_snapshot(self, player: PlayerState) -> dict:
        return {
            "public_tricks": player.public_trick_names(),
            "hidden_trick_count": player.hidden_trick_count(),
        }

    def _initialize_active_faces(self, state: GameState) -> None:
        if self.config.characters.randomize_starting_active_by_card:
            state.active_by_card = randomized_active_by_card(self.rng)
        else:
            state.active_by_card = dict(self.config.characters.starting_active_by_card)
        self._log({
            "event": "initial_active_faces",
            "randomized": self.config.characters.randomize_starting_active_by_card,
            "active_by_card": dict(state.active_by_card),
        })

    def _is_muroe_skill_blocked(self, state: GameState, player: PlayerState) -> bool:
        if player.attribute != "무뢰":
            return False
        return any(
            other.alive and other.player_id != player.player_id and other.current_character == "어사"
            for other in state.players
        )

    def _apply_forced_landing(self, state: GameState, player: PlayerState, source_pos: int) -> dict:
        old_pos = player.position
        player.position = source_pos
        landing = self._resolve_landing(state, player)
        event = {
            "event": "forced_move",
            "player": player.player_id + 1,
            "character": player.current_character,
            "start_pos": old_pos,
            "end_pos": player.position,
            "no_lap_credit": True,
            "landing": landing,
        }
        self._log(event)
        return landing

    def _resolve_marker_flip(self, state: GameState) -> None:
        self.events.emit_first_non_none("marker.flip.resolve", state)

    def _draw_weather_card(self, state: GameState) -> WeatherCard:
        if not state.weather_draw_pile:
            state.weather_draw_pile = list(state.weather_discard_pile)
            state.weather_discard_pile = []
            self.rng.shuffle(state.weather_draw_pile)
            self._log({"event": "weather_reshuffle", "draw_pile": len(state.weather_draw_pile)})
        return state.weather_draw_pile.pop()

    def _has_weather(self, state: GameState, name: str) -> bool:
        return name in state.current_weather_effects

    def _weather_extra_dice(self, state: GameState) -> int:
        return 1 if self._has_weather(state, "말이 살찌는 계절") else 0

    def _weather_marker_owner(self, state: GameState) -> PlayerState | None:
        if not state.players:
            return None
        owner = state.players[state.marker_owner_id]
        return owner if owner.alive else None

    def _weather_gain_tricks(self, state: GameState, target: PlayerState, count: int, redraw: bool = False) -> dict:
        discarded = []
        if redraw and count > 0:
            keep = list(target.trick_hand[: max(0, len(target.trick_hand) - count)])
            for card in target.trick_hand[len(keep):]:
                discarded.append(card.name)
                self._discard_trick(state, target, card)
        before = len(target.trick_hand)
        self._draw_tricks(state, target, count)
        return {"player": target.player_id + 1, "count": len(target.trick_hand) - before, "discarded": discarded}

    def _apply_round_weather(self, state: GameState) -> None:
        card = self._draw_weather_card(state)
        self._weather_history.append(card.name)
        state.current_weather = card
        state.current_weather_effects = {card.name}
        state.weather_discard_pile.append(card)
        event = {"event": "weather_round", "round_index": state.rounds_completed + 1, "weather": card.name, "effect": card.effect}
        details = []

        if card.name == "외세의 침략":
            for p in state.players:
                if p.alive:
                    out = self._pay_or_bankrupt(state, p, 2, None)
                    details.append({"player": p.player_id + 1, **out})
        elif card.name == "솔선 수범":
            owner = self._weather_marker_owner(state)
            if owner is not None:
                details.append({"player": owner.player_id + 1, **self._pay_or_bankrupt(state, owner, 3, None)})
        elif card.name == "기우제":
            owner = self._weather_marker_owner(state)
            if owner is not None:
                owner.shards += 1
                self._strategy_stats[owner.player_id]["shards_gained_lap"] += 1
                self._change_f(state, -1, reason="weather_effect", source="기우제")
                details.append({"player": owner.player_id + 1, "shards_delta": 1, "f_delta": -1})
        elif card.name == "구휼의 상징":
            owner = self._weather_marker_owner(state)
            if owner is not None:
                owner.cash += 4
                details.append({"player": owner.player_id + 1, "cash_delta": 4})
        elif card.name == "잔꾀 부리기":
            for p in state.players:
                if p.alive:
                    details.append(self._weather_gain_tricks(state, p, 1, redraw=False))
        elif card.name == "전략 변경":
            for p in state.players:
                if p.alive:
                    need = max(0, 5 - len(p.trick_hand))
                    details.append(self._weather_gain_tricks(state, p, need, redraw=False))
        elif card.name == "모든 것을 자원으로":
            details.append(self._fortune_burden_cleanup(state, [p for p in state.players if p.alive], multiplier=2, payout=True, name=card.name))
        elif card.name == "긴급 피난":
            details.append(self._fortune_burden_cleanup(state, [p for p in state.players if p.alive], multiplier=2, payout=False, name=card.name))
        elif card.name == "밤인데 낮처럼 밝아요":
            self._change_f(state, -3, reason="weather_effect", source="밤인데 낮처럼 밝아요")
            details.append({"f_delta": -3})
        elif card.name == "길고 긴 겨울":
            self._change_f(state, -1, reason="weather_effect", source="길고 긴 겨울")
            details.append({"f_delta": -1})
        elif card.name == "맑고 포근한 하루":
            ordered = self._alive_ids_clockwise_from_marker(state)
            for pid in ordered:
                p = state.players[pid]
                used = sorted(p.used_dice_cards)
                if not used:
                    details.append({"player": p.player_id + 1, "recovered": None})
                    continue
                recovered = used[0]
                p.used_dice_cards.discard(recovered)
                details.append({"player": p.player_id + 1, "recovered": recovered})

        if details:
            event["details"] = details
        self._log(event)

    def _apply_weather_same_tile_bonus(self, state: GameState, player: PlayerState, event: dict) -> dict:
        co = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == player.position]
        if self._has_weather(state, "사랑과 우정") and co:
            gain = 4 * len(co)
            player.cash += gain
            event["weather_same_tile_cash_gain"] = gain
            event["weather_same_tile_with"] = [p.player_id + 1 for p in co]
        return event

    def _start_new_round(self, state: GameState, initial: bool) -> None:
        for p in state.players:
            p.immune_to_marks_this_round = False
            p.skipped_turn = False
            p.free_purchase_this_turn = False
            p.extra_dice_count_this_turn = 0
            p.block_start_reward_this_turn = False
            p.drafted_cards = []
            p.revealed_this_round = False
            p.extra_shard_gain_this_turn = 0
            p.rent_waiver_count_this_turn = 0
            p.trick_free_purchase_this_turn = False
            p.trick_dice_delta_this_turn = 0
            p.trick_personal_rent_half_this_turn = False
            p.trick_same_tile_cash2_this_turn = False
            p.trick_same_tile_shard_rake_this_turn = False
            p.trick_one_extra_adjacent_buy_this_turn = False
            p.trick_encounter_boost_this_turn = False
            p.trick_force_sale_landing_this_turn = False
            p.trick_zone_chain_this_turn = False
        state.global_rent_half_this_turn = False
        state.global_rent_double_this_turn = False
        state.tile_rent_modifiers_this_turn = {}
        state.current_weather = None
        state.current_weather_effects = set()
        self._resolve_marker_flip(state)
        self._run_draft(state)
        self._apply_round_weather(state)
        alive = [p for p in state.players if p.alive]
        alive.sort(key=lambda p: (CHARACTERS[p.current_character].priority, p.player_id))
        state.current_round_order = [p.player_id for p in alive]
        self._log({
            "event": "round_order",
            "round_index": state.rounds_completed + 1,
            "initial": initial,
            "order": [pid + 1 for pid in state.current_round_order],
            "characters": {p.player_id + 1: p.current_character for p in alive},
            "marker_owner": state.marker_owner_id + 1,
            "active_by_card": dict(state.active_by_card),
        })

    def _alive_ids_clockwise_from_marker(self, state: GameState) -> list[int]:
        alive_ids = {p.player_id for p in state.players if p.alive}
        if not alive_ids:
            return []
        start = state.marker_owner_id
        if start not in alive_ids:
            for i in range(1, self.config.player_count + 1):
                cand = (state.marker_owner_id + i) % self.config.player_count
                if cand in alive_ids:
                    start = cand
                    break
        ordered = []
        for i in range(self.config.player_count):
            pid = (start + i) % self.config.player_count
            if pid in alive_ids:
                ordered.append(pid)
        return ordered

    def _run_draft(self, state: GameState) -> None:
        cards = list(CARD_TO_NAMES.keys())
        self.rng.shuffle(cards)
        clockwise = self._alive_ids_clockwise_from_marker(state)
        reverse = list(reversed(clockwise))
        alive_count = len(clockwise)

        if alive_count == 3:
            removed = cards[0]
            phase1_pool = list(cards[1:5])
            reserve_pool = list(cards[5:8])
            self._log({"event": "draft_hidden_card", "player_count": 3, "hidden_card": removed})

            pool = list(phase1_pool)
            for pid in clockwise:
                pick = self.policy.choose_draft_card(state, state.players[pid], list(pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._log({"event": "draft_pick", "phase": 1, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                pool.remove(pick)

            second_pool = list(reserve_pool) + list(pool)
            last_pid = clockwise[-1]
            pick = self.policy.choose_draft_card(state, state.players[last_pid], list(second_pool))
            state.players[last_pid].drafted_cards.append(pick)
            draft_debug = self.policy.pop_debug("draft_card", last_pid) if hasattr(self.policy, "pop_debug") else None
            self._log({"event": "draft_pick", "phase": 2, "player": last_pid + 1, "picked_card": pick, "decision": draft_debug})
            second_pool.remove(pick)

            for pid in reverse[1:]:
                pick = self.policy.choose_draft_card(state, state.players[pid], list(second_pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._log({"event": "draft_pick", "phase": 2, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                second_pool.remove(pick)

        else:
            first_pack_size = alive_count
            second_pack_size = alive_count
            first_pool = list(cards[:first_pack_size])
            second_pool = list(cards[first_pack_size:first_pack_size + second_pack_size])
            hidden = cards[first_pack_size + second_pack_size:]
            if hidden:
                self._log({"event": "draft_hidden_cards", "player_count": alive_count, "hidden_cards": list(hidden)})

            pool = list(first_pool)
            for pid in clockwise:
                pick = self.policy.choose_draft_card(state, state.players[pid], list(pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._log({"event": "draft_pick", "phase": 1, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                pool.remove(pick)

            pool = list(second_pool)
            for pid in reverse:
                pick = self.policy.choose_draft_card(state, state.players[pid], list(pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._log({"event": "draft_pick", "phase": 2, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                pool.remove(pick)

        for p in state.players:
            if not p.alive:
                p.current_character = ""
                self._strategy_stats[p.player_id]["character"] = ""
                self._strategy_stats[p.player_id]["draft_cards"] = []
                continue
            chosen = self.policy.choose_final_character(state, p, list(p.drafted_cards))
            final_debug = self.policy.pop_debug("final_character", p.player_id) if hasattr(self.policy, "pop_debug") else None
            p.current_character = chosen
            self._strategy_stats[p.player_id]["character"] = chosen
            self._strategy_stats[p.player_id]["last_selected_character"] = chosen
            counts = self._strategy_stats[p.player_id].setdefault("character_choice_counts", {})
            counts[chosen] = counts.get(chosen, 0) + 1
            self._strategy_stats[p.player_id]["draft_cards"] = list(p.drafted_cards)
            self._strategy_stats[p.player_id]["character_policy_mode"] = (self.policy.character_mode_for_player(p.player_id) if hasattr(self.policy, "character_mode_for_player") else getattr(self.policy, "character_policy_mode", ""))
            self._log({"event": "final_character_choice", "player": p.player_id + 1, "character": chosen, "decision": final_debug})

    def _take_turn(self, state: GameState, player: PlayerState) -> None:
        start_log = {"event": "turn_start", "player": player.player_id + 1, "character": player.current_character}
        finisher_before = int(getattr(player, "control_finisher_turns", 0) or 0)
        disruption_before = self._leader_disruption_snapshot(state, player)
        if player.skipped_turn:
            player.skipped_turn = False
            self._log({**start_log, "skipped": True})
            self._apply_marker_management(state, player)
            return
        self._resolve_pending_marks(state, player)
        if not player.alive:
            return
        if self._has_weather(state, "말이 살찌는 계절"):
            player.extra_dice_count_this_turn += 1
        self._apply_character_start(state, player)
        if not player.alive:
            return
        self._use_trick_phase(state, player)
        if not player.alive:
            return
        decision = self.policy.choose_movement(state, player)
        move, movement_meta = self._resolve_move(state, player, decision)
        if len(self._strategy_stats) <= player.player_id:
            self._strategy_stats = [
                {
                    "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                    "rent_paid": 0, "own_tile_visits": 0,
                    "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                    "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                    "malicious_visits": 0, "bankruptcies": 0,
                    "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                    "tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0,
                    "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                    "coins_gained_own_tile": 0, "coins_placed": 0,
                    "mark_attempts": 0, "mark_successes": 0,
                    "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                    "character": "", "shards_gained_f": 0, "shards_gained_lap": 0, "shard_income_cash": 0,
                    "draft_cards": [], "marked_target_names": [],
                }
                for _ in range(state.config.player_count)
            ]
        stats = self._strategy_stats[player.player_id]
        used_cards = movement_meta.get("used_cards", [])
        if used_cards:
            stats["card_turns"] += 1
            stats["cards_used"] += len(used_cards)
            if len(used_cards) == 1:
                stats["single_card_turns"] += 1
            elif len(used_cards) == 2:
                stats["pair_card_turns"] += 1
        self._advance_player(state, player, move, movement_meta)
        self._apply_marker_management(state, player)
        disruption_after = self._leader_disruption_snapshot(state, player)
        awarded = self._maybe_award_control_finisher_window(state, player, disruption_before, disruption_after)
        if finisher_before > 0 and not awarded:
            player.control_finisher_turns = max(0, finisher_before - 1)
            if player.control_finisher_turns == 0:
                player.control_finisher_reason = ""


    def _player_lap_mode(self, player: PlayerState) -> str:
        if hasattr(self.policy, "lap_mode_for_player"):
            return self.policy.lap_mode_for_player(player.player_id)
        return getattr(self.policy, "lap_policy_mode", "")

    def _leader_disruption_snapshot(self, state: GameState, actor: PlayerState) -> dict:
        alive = [p for p in state.players if p.alive and p.player_id != actor.player_id]
        if not alive:
            return {"leader_id": None, "leader_tiles": 0, "leader_cash": 0, "leader_score": 0, "solo": False, "alive_count": state.alive_count()}
        scores = [(state.total_score(p.player_id), p.tiles_owned, p.cash, p.player_id) for p in alive]
        scores.sort(reverse=True)
        top = scores[0]
        solo = len(scores) == 1 or top[:3] > scores[1][:3]
        return {
            "leader_id": top[3],
            "leader_tiles": top[1],
            "leader_cash": top[2],
            "leader_score": top[0],
            "solo": solo,
            "alive_count": state.alive_count(),
        }

    def _maybe_award_control_finisher_window(self, state: GameState, actor: PlayerState, before: dict, after: dict) -> bool:
        if self._player_lap_mode(actor) != "heuristic_v2_control":
            return False
        leader_id = before.get("leader_id")
        if leader_id is None:
            return False
        triggered: list[str] = []
        if before.get("solo") and (after.get("leader_id") != leader_id or not after.get("solo", False)):
            triggered.append("solo_leader_broken")
        leader_before = state.players[leader_id] if 0 <= leader_id < len(state.players) else None
        if leader_before is not None:
            if not leader_before.alive:
                triggered.append("leader_bankrupt")
            if after.get("leader_id") == leader_id:
                if float(after.get("leader_tiles", 0)) < float(before.get("leader_tiles", 0)):
                    triggered.append("leader_tiles_cut")
                if float(before.get("leader_cash", 0)) - float(after.get("leader_cash", 0)) >= 5.0:
                    triggered.append("leader_cash_cut")
                if float(after.get("leader_score", 0)) + 1.0 < float(before.get("leader_score", 0)):
                    triggered.append("leader_score_cut")
        if not triggered:
            return False
        actor.control_finisher_turns = 2
        actor.control_finisher_reason = ",".join(triggered[:2])
        self._log({
            "event": "control_finisher_window",
            "player": actor.player_id + 1,
            "turns": actor.control_finisher_turns,
            "reason": actor.control_finisher_reason,
            "before": before,
            "after": after,
        })
        return True

    def _resolve_pending_marks(self, state: GameState, player: PlayerState) -> None:
        remaining = []
        for eff in player.pending_marks:
            if player.immune_to_marks_this_round:
                continue
            etype = eff["type"]
            source = state.players[eff["source_pid"]]
            if etype == "bandit_tax":
                amount = source.shards
                outcome = self._pay_or_bankrupt(state, player, amount, source.player_id)
                self._strategy_stats[source.player_id]["shard_income_cash"] += amount if outcome.get("paid") else 0
                self._log({"event": "bandit_tax", "source_player": source.player_id + 1, "target_player": player.player_id + 1, "amount": amount, **outcome})
            elif etype == "hunter_pull":
                self._apply_forced_landing(state, player, eff["source_pos"])
            elif etype == "baksu_transfer":
                self._resolve_baksu_transfer(state, source, player)
            elif etype == "manshin_remove_burdens":
                self._resolve_manshin_remove_burdens(state, source, player)
            else:
                remaining.append(eff)
            if not player.alive:
                remaining = []
                break
        player.pending_marks = remaining

    def _apply_character_start(self, state: GameState, player: PlayerState) -> None:
        char = player.current_character
        if self._is_muroe_skill_blocked(state, player):
            self._log({"event": "ability_suppressed", "player": player.player_id + 1, "character": char, "reason": "어사"})
            return
        if char == "자객":
            target = self.policy.choose_mark_target(state, player, char)
            target_p = self._find_player_by_character(state, target, exclude=player.player_id, source_pid=player.player_id, future_only=True)
            mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            if target_p is not None:
                self._record_mark_attempt(player.player_id, "success", state)
                target_p.pending_marks.clear()
                target_p.immune_to_marks_this_round = True
                target_p.skipped_turn = True
                target_p.revealed_this_round = True
                self._strategy_stats[player.player_id]["marked_target_names"].append(target)
                self._log({
                    "event": "assassin_reveal",
                    "player": player.player_id + 1,
                    "target_player": target_p.player_id + 1,
                    "target_character": target,
                    "decision": mark_debug,
                })
            else:
                self._record_mark_attempt(player.player_id, "none" if not target else "missing", state)
                if mark_debug is not None:
                    event_name = "mark_target_none" if not target else "mark_target_missing"
                    row = {"event": event_name, "player": player.player_id + 1, "character": char, "decision": mark_debug}
                    if target:
                        row["target_character"] = target
                    self._log(row)
        elif char == "산적":
            target = self.policy.choose_mark_target(state, player, char)
            mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            self._queue_mark(state, player.player_id, target, {"type": "bandit_tax"}, decision=mark_debug)
        elif char == "추노꾼":
            target = self.policy.choose_mark_target(state, player, char)
            mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            self._queue_mark(state, player.player_id, target, {"type": "hunter_pull", "source_pos": player.position}, decision=mark_debug)
        elif char == "파발꾼":
            player.extra_dice_count_this_turn += 1
        elif char == "박수":
            target = self.policy.choose_mark_target(state, player, char)
            mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            self._queue_mark(state, player.player_id, target, {"type": "baksu_transfer"}, decision=mark_debug)
        elif char == "만신":
            target = self.policy.choose_mark_target(state, player, char)
            mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            self._queue_mark(state, player.player_id, target, {"type": "manshin_remove_burdens"}, decision=mark_debug)
        elif char in {"교리 연구관", "교리 감독관"}:
            self._resolve_doctrine_burden_relief(state, player)
        elif char == "건설업자":
            player.free_purchase_this_turn = True

    def _queue_mark(self, state: GameState, source_pid: int, target_character: Optional[str], payload: dict, decision: dict | None = None) -> None:
        source = state.players[source_pid]
        if not target_character:
            self._record_mark_attempt(source_pid, "none", state)
            self._apply_failed_mark_fallback(state, source, payload)
            if decision is not None:
                self._log({"event": "mark_target_none", "player": source_pid + 1, "decision": decision})
            return
        target_p = self._find_player_by_character(state, target_character, exclude=source_pid, source_pid=source_pid, future_only=True)
        if target_p is None:
            self._record_mark_attempt(source_pid, "missing", state)
            self._apply_failed_mark_fallback(state, source, payload)
            if decision is not None:
                self._log({"event": "mark_target_missing", "player": source_pid + 1, "target_character": target_character, "decision": decision})
            return
        if target_p.revealed_this_round:
            self._record_mark_attempt(source_pid, "blocked", state)
            self._apply_failed_mark_fallback(state, source, payload)
            self._log({
                "event": "mark_blocked",
                "source_player": source_pid + 1,
                "target_player": target_p.player_id + 1,
                "target_character": target_character,
                "reason": "revealed_by_assassin",
                "decision": decision,
            })
            return
        self._record_mark_attempt(source_pid, "success", state)
        mark = {"source_pid": source_pid, **payload}
        target_p.pending_marks.append(mark)
        self._strategy_stats[source_pid]["marked_target_names"].append(target_character)
        if decision is not None:
            self._log({"event": "mark_queued", "source_player": source_pid + 1, "target_player": target_p.player_id + 1, "target_character": target_character, "payload": payload, "decision": decision})

    def _apply_failed_mark_fallback(self, state: GameState, source: PlayerState, payload: dict) -> None:
        mark_type = payload.get("type")
        if mark_type == "baksu_transfer":
            threshold = 5
            actor_name = "박수"
        elif mark_type == "manshin_remove_burdens":
            threshold = 7
            actor_name = "만신"
        else:
            return
        removable = source.shards // threshold
        if removable <= 0:
            self._log({
                "event": "failed_mark_fallback_none",
                "player": source.player_id + 1,
                "character": actor_name,
                "reason": "insufficient_shards",
                "shards": source.shards,
                "threshold": threshold,
            })
            return
        burdens = sorted(self._burden_cards(source), key=lambda c: (c.burden_cost, c.deck_index), reverse=True)
        if not burdens:
            self._log({
                "event": "failed_mark_fallback_none",
                "player": source.player_id + 1,
                "character": actor_name,
                "reason": "no_burdens",
                "shards": source.shards,
                "threshold": threshold,
            })
            return
        removed = []
        payout = 0
        for card in burdens[:removable]:
            moved = self._remove_trick_from_hand(state, source, card)
            if moved is None:
                continue
            state.trick_discard_pile.append(moved)
            removed.append(moved)
            payout += moved.burden_cost
        if not removed:
            self._log({
                "event": "failed_mark_fallback_none",
                "player": source.player_id + 1,
                "character": actor_name,
                "reason": "remove_failed",
                "shards": source.shards,
                "threshold": threshold,
            })
            return
        source.cash += payout
        self._sync_trick_visibility(state, source)
        self._log({
            "event": "failed_mark_fallback",
            "player": source.player_id + 1,
            "character": actor_name,
            "shards": source.shards,
            "threshold": threshold,
            "removed": [c.name for c in removed],
            "removed_count": len(removed),
            "cash_gained": payout,
            **self._public_trick_snapshot(source),
        })

    def _record_mark_attempt(self, source_pid: int, outcome: str, state: GameState | None = None) -> None:
        stats = self._strategy_stats[source_pid]
        stats["mark_attempts"] = stats.get("mark_attempts", 0) + 1
        if outcome == "success":
            stats["mark_successes"] = stats.get("mark_successes", 0) + 1
            if state is not None and self._has_weather(state, "사냥의 계절"):
                source = state.players[source_pid]
                if source.attribute == "무뢰" and source.alive:
                    source.cash += 4
                    self._log({"event": "weather_hunt_bonus", "player": source.player_id + 1, "cash_delta": 4})
        elif outcome == "none":
            stats["mark_fail_no_target"] = stats.get("mark_fail_no_target", 0) + 1
        elif outcome == "missing":
            stats["mark_fail_missing"] = stats.get("mark_fail_missing", 0) + 1
        elif outcome == "blocked":
            stats["mark_fail_blocked"] = stats.get("mark_fail_blocked", 0) + 1

    def _find_player_by_character(self, state: GameState, character_name: Optional[str], exclude: Optional[int] = None, source_pid: Optional[int] = None, future_only: bool = False) -> Optional[PlayerState]:
        if not character_name:
            return None
        allowed_pids: set[int] | None = None
        if future_only and source_pid is not None:
            try:
                source_order_idx = state.current_round_order.index(source_pid)
                allowed_pids = set(state.current_round_order[source_order_idx + 1 :])
            except ValueError:
                allowed_pids = set()
        for p in state.players:
            if exclude is not None and p.player_id == exclude:
                continue
            if allowed_pids is not None and p.player_id not in allowed_pids:
                continue
            if p.alive and p.current_character == character_name:
                return p
        return None


    def _draw_tricks(self, state: GameState, player: PlayerState, count: int) -> list[TrickCard]:
        drawn: list[TrickCard] = []
        for _ in range(count):
            if not state.trick_draw_pile:
                state.trick_draw_pile = list(state.trick_discard_pile)
                state.trick_discard_pile = []
                self.rng.shuffle(state.trick_draw_pile)
                self._log({"event": "trick_reshuffle", "draw_pile": len(state.trick_draw_pile)})
            if not state.trick_draw_pile:
                break
            card = state.trick_draw_pile.pop()
            player.trick_hand.append(card)
            drawn.append(card)
        self._sync_trick_visibility(state, player)
        return drawn

    def _remove_trick_from_hand(self, state: GameState, player: PlayerState, card: TrickCard) -> TrickCard | None:
        for i, held in enumerate(player.trick_hand):
            if held.deck_index == card.deck_index:
                removed = player.trick_hand.pop(i)
                self._sync_trick_visibility(state, player)
                return removed
        return None

    def _discard_trick(self, state: GameState, player: PlayerState, card: TrickCard) -> None:
        held = self._remove_trick_from_hand(state, player, card)
        if held is not None:
            state.trick_discard_pile.append(held)

    def _consume_trick_by_name(self, state: GameState, player: PlayerState, name: str) -> TrickCard | None:
        for card in list(player.trick_hand):
            if card.name == name:
                held = self._remove_trick_from_hand(state, player, card)
                if held is not None:
                    state.trick_discard_pile.append(held)
                    return held
        return None

    def _has_trick(self, player: PlayerState, name: str) -> bool:
        return any(card.name == name for card in player.trick_hand)

    def _burden_cards(self, player: PlayerState) -> list[TrickCard]:
        return [c for c in player.trick_hand if c.is_burden]

    def _resolve_baksu_transfer(self, state: GameState, source: PlayerState, target: PlayerState) -> None:
        burdens = list(self._burden_cards(source))
        if not burdens:
            self._log({"event": "baksu_transfer_none", "player": source.player_id + 1, "target_player": target.player_id + 1})
            return
        for card in burdens:
            moved = self._remove_trick_from_hand(state, source, card)
            if moved is not None:
                target.trick_hand.append(moved)
        self._sync_trick_visibility(state, target)
        rewards = []
        for _ in range(len(burdens)):
            choices = state.trick_draw_pile[-8:] if state.trick_draw_pile else []
            pick = self.policy.choose_specific_trick_reward(state, source, list(choices)) if hasattr(self.policy, "choose_specific_trick_reward") else None
            if pick is None and state.trick_draw_pile:
                pick = state.trick_draw_pile[-1]
            if pick is None:
                break
            # remove chosen from draw pile by deck index
            for i in range(len(state.trick_draw_pile)-1, -1, -1):
                if state.trick_draw_pile[i].deck_index == pick.deck_index:
                    chosen = state.trick_draw_pile.pop(i)
                    source.trick_hand.append(chosen)
                    rewards.append(chosen.name)
                    break
        self._sync_trick_visibility(state, source)
        self._sync_trick_visibility(state, target)
        self._log({"event": "baksu_transfer", "player": source.player_id + 1, "target_player": target.player_id + 1, "moved": [c.name for c in burdens], "rewarded": rewards, **self._public_trick_snapshot(source), "target_public_tricks": target.public_trick_names(), "target_hidden_trick_count": target.hidden_trick_count()})

    def _resolve_manshin_remove_burdens(self, state: GameState, source: PlayerState, target: PlayerState) -> None:
        burdens = list(self._burden_cards(target))
        cost = sum(c.burden_cost for c in burdens)
        for card in burdens:
            self._discard_trick(state, target, card)
        outcome = self._pay_or_bankrupt(state, target, cost, source.player_id) if cost > 0 else {"cost": 0, "paid": True, "bankrupt": False, "receiver": source.player_id + 1}
        self._sync_trick_visibility(state, target)
        self._log({"event": "manshin_burden_clear", "player": source.player_id + 1, "target_player": target.player_id + 1, "removed": [c.name for c in burdens], **outcome, "target_public_tricks": target.public_trick_names(), "target_hidden_trick_count": target.hidden_trick_count()})

    def _eligible_doctrine_relief_targets(self, state: GameState, player: PlayerState) -> list[PlayerState]:
        player_team = getattr(player, "team_id", None)
        candidates: list[PlayerState] = []
        for target in state.players:
            if not target.alive:
                continue
            if not self._burden_cards(target):
                continue
            if player_team is None:
                if target.player_id != player.player_id:
                    continue
            else:
                target_team = getattr(target, "team_id", None)
                if target_team != player_team:
                    continue
            candidates.append(target)
        return candidates

    def _resolve_doctrine_burden_relief(self, state: GameState, source: PlayerState) -> None:
        candidates = self._eligible_doctrine_relief_targets(state, source)
        if not candidates:
            self._log({
                "event": "doctrine_burden_relief",
                "player": source.player_id + 1,
                "character": source.current_character,
                "target_player": None,
                "removed": None,
                "reason": "no_eligible_target",
            })
            return
        chosen_pid = self.policy.choose_doctrine_relief_target(state, source, candidates)
        relief_debug = self.policy.pop_debug("doctrine_relief", source.player_id) if hasattr(self.policy, "pop_debug") else None
        target = next((p for p in candidates if p.player_id == chosen_pid), None)
        if target is None:
            target = next((p for p in candidates if p.player_id == source.player_id), candidates[0])
        burdens = sorted(self._burden_cards(target), key=lambda c: (c.burden_cost, c.name), reverse=True)
        if not burdens:
            self._log({
                "event": "doctrine_burden_relief",
                "player": source.player_id + 1,
                "character": source.current_character,
                "target_player": target.player_id + 1,
                "removed": None,
                "reason": "target_has_no_burden",
                "decision": relief_debug,
            })
            return
        removed = burdens[0]
        self._discard_trick(state, target, removed)
        self._sync_trick_visibility(state, target)
        self._log({
            "event": "doctrine_burden_relief",
            "player": source.player_id + 1,
            "character": source.current_character,
            "target_player": target.player_id + 1,
            "removed": removed.name,
            "removed_cost": removed.burden_cost,
            "target_public_tricks": target.public_trick_names(),
            "target_hidden_trick_count": target.hidden_trick_count(),
            "decision": relief_debug,
        })

    def _handle_supply_thresholds(self, state: GameState, prev_f: float) -> None:
        while prev_f < state.next_supply_f_threshold <= state.f_value:
            threshold = state.next_supply_f_threshold
            state.next_supply_f_threshold += 3
            self._run_supply(state, threshold)

    def _run_supply(self, state: GameState, threshold: int) -> None:
        event = {"event": "trick_supply", "threshold": threshold, "players": []}
        for p in state.players:
            if not p.alive:
                continue
            exchanged = []
            for card in list(p.trick_hand):
                if card.is_burden and getattr(self.policy, "choose_burden_exchange_on_supply", lambda s, pl, c: pl.cash >= c.burden_cost)(state, p, card) and p.cash >= card.burden_cost:
                    p.cash -= card.burden_cost
                    self._discard_trick(state, p, card)
                    exchanged.append({"name": card.name, "cost": card.burden_cost})
                    self._draw_tricks(state, p, 1)
            before = len(p.trick_hand)
            self._draw_tricks(state, p, max(0, 5 - len(p.trick_hand)))
            event["players"].append({"player": p.player_id + 1, "before": before, "after": len(p.trick_hand), "exchanged": exchanged, "hand": [c.name for c in p.trick_hand], "public_hand": p.public_trick_names(), "hidden_trick_count": p.hidden_trick_count()})
        self._log(event)

    def _change_f(
        self,
        state: GameState,
        delta: float,
        *,
        reason: str = "",
        source: str = "",
        actor_pid: int | None = None,
        extra: dict | None = None,
    ) -> None:
        prev = state.f_value
        requested_delta = delta
        unclamped_after = prev + requested_delta
        state.f_value = max(0.0, unclamped_after)
        applied_delta = state.f_value - prev
        payload = {
            "event": "resource_f_change",
            "before": prev,
            "requested_delta": requested_delta,
            "delta": applied_delta,
            "after": state.f_value,
            "clamped": state.f_value != unclamped_after,
            "reason": reason,
            "source": source,
        }
        if actor_pid is not None:
            payload["actor_player"] = actor_pid + 1
        if extra:
            payload.update(extra)
        self._log(payload)
        self._handle_supply_thresholds(state, prev)

    def _buy_one_adjacent_same_block(self, state: GameState, player: PlayerState, pos: int) -> int | None:
        block_id = state.block_ids[pos]
        if block_id < 0:
            return None
        candidates = [
            idx for idx, bid in enumerate(state.block_ids)
            if bid == block_id and idx != pos and state.tile_owner[idx] is None and state.board[idx] in (CellKind.T2, CellKind.T3)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda i: (state.config.rules.economy.purchase_cost_for(state, i), i), reverse=True)
        idx = candidates[0]
        cost = state.config.rules.economy.purchase_cost_for(state, idx)
        shard_cost = 0
        if player.cash < cost:
            return None
        if shard_cost > 0 and player.shards < shard_cost:
            return None
        if not getattr(self.policy, "choose_purchase_tile", lambda *args, **kwargs: True)(state, player, idx, state.board[idx], cost, source="adjacent_extra"):
            return None
        player.cash -= cost
        if shard_cost > 0:
            player.shards -= shard_cost
        state.tile_owner[idx] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[idx] = player.turns_taken
        return idx

    def _effective_rent(self, state: GameState, pos: int, payer: PlayerState, owner_player_id: int | None) -> int:
        cell = state.board[pos]
        base = state.config.rules.economy.rent_cost_for(state, pos)
        mod = state.tile_rent_modifiers_this_turn.get(pos, 1)
        block_id = state.block_ids[pos]
        tile_color = state.block_color_map.get(block_id)
        if tile_color is not None and any(COLOR_RENT_DOUBLE_WEATHERS.get(name) == tile_color for name in state.current_weather_effects):
            mod *= 2
        if mod == 0:
            return 0
        rent = base * mod
        if state.global_rent_double_permanent:
            rent *= 2
        if state.global_rent_double_this_turn:
            rent *= 2
        if state.global_rent_half_this_turn:
            rent = math.ceil(rent / 2)
        if payer.trick_personal_rent_half_this_turn:
            rent = rent // 2
        if owner_player_id is not None and state.players[owner_player_id].trick_personal_rent_half_this_turn:
            rent = rent // 2
        return max(0, rent)

    def _is_trick_phase_usable(self, card: TrickCard) -> bool:
        return card.name not in {"강제 매각", "뭘리권", "뭔칙휜", "호객꾼"}

    def _use_trick_phase(self, state: GameState, player: PlayerState) -> None:
        if not hasattr(self.policy, "choose_trick_to_use"):
            return

        def choose_and_apply(hand: list[TrickCard], phase: str) -> bool:
            if not hand:
                return False
            card = self.policy.choose_trick_to_use(state, player, list(hand))
            debug = self.policy.pop_debug("trick_use", player.player_id) if hasattr(self.policy, "pop_debug") else None
            if card is None:
                if debug is not None:
                    self._log({"event": "trick_use_skip", "player": player.player_id + 1, "phase": phase, "decision": debug})
                return False
            resolution = self._apply_trick_card(state, player, card)
            self._discard_trick(state, player, card)
            stats = self._strategy_stats[player.player_id]
            stats["tricks_used"] += 1
            if phase == "anytime":
                stats["anytime_tricks_used"] += 1
            elif phase == "regular":
                stats["regular_tricks_used"] += 1
            self._log({"event": "trick_used", "player": player.player_id + 1, "phase": phase, "character": player.current_character, "card": {"deck_index": card.deck_index, "name": card.name}, "resolution": resolution, "decision": debug})
            return True

        # 언제나 사용할 수 있는 잔꾀는 자신의 턴 잔꾀 단계에서 먼저 여러 장 사용할 수 있다.
        while True:
            anytime_hand = [c for c in player.trick_hand if c.is_anytime and self._is_trick_phase_usable(c)]
            if not choose_and_apply(anytime_hand, "anytime"):
                break

        # 일반 잔꾀는 자신의 턴에 1장만 사용 가능.
        regular_hand = [c for c in player.trick_hand if (not c.is_anytime) and self._is_trick_phase_usable(c)]
        choose_and_apply(regular_hand, "regular")

    def _apply_trick_card(self, state: GameState, player: PlayerState, card: TrickCard) -> dict:
        result = self.events.emit_first_non_none("trick.card.resolve", state, player, card)
        return result if result is not None else {"type": "NOT_YET_IMPLEMENTED", "name": card.name}

    def _apply_flash_trade(self, state: GameState, player: PlayerState) -> dict:
        others = [p for p in state.players if p.alive and p.player_id != player.player_id and p.trick_hand]
        if not others or not player.trick_hand:
            return {"type": "NO_EFFECT", "reason": "missing_trade_target"}
        def my_value(card: TrickCard) -> int:
            return -10 if card.is_burden else 10 - card.burden_cost
        def their_value(card: TrickCard) -> int:
            return 20 if card.is_burden else 10 + (2 if card.name in {"무료 증정", "우대권", "성물 수집가"} else 0)
        def visible_cards(op: PlayerState) -> list[TrickCard]:
            cards = list(op.public_trick_cards())
            return cards if cards else list(op.trick_hand)
        best_target = max(others, key=lambda op: max(their_value(c) for c in visible_cards(op)))
        offer = min(player.trick_hand, key=my_value)
        receive = max(visible_cards(best_target), key=their_value)
        self._remove_trick_from_hand(state, player, offer)
        self._remove_trick_from_hand(state, best_target, receive)
        player.trick_hand.append(receive)
        best_target.trick_hand.append(offer)
        self._sync_trick_visibility(state, player)
        self._sync_trick_visibility(state, best_target)
        return {"type": "TRICK_EXCHANGE", "target_player": best_target.player_id + 1, "count": 1, "sent": [offer.name], "received": [receive.name], "target_public_tricks": best_target.public_trick_names(), "target_hidden_trick_count": best_target.hidden_trick_count()}

    def _try_anytime_rerolls(self, state: GameState, player: PlayerState, used_cards: list[int], dice: list[int], mode: str) -> tuple[list[int], list[dict]]:
        if mode == "card_pair_fixed" or not dice:
            return dice, []
        rerolls: list[dict] = []
        def score_for(curr_dice: list[int]) -> float:
            if mode == "card_plus_die":
                move = sum(used_cards) + sum(curr_dice)
            else:
                move = sum(curr_dice)
            pos = (player.position + move) % len(state.board)
            return self.policy._landing_score(state, player, pos) if hasattr(self.policy, '_landing_score') else 0.0
        current = list(dice)
        current_score = score_for(current)
        budget = 0
        if self._has_trick(player, "뭔칙휜"):
            budget += 2
        elif self._has_trick(player, "뭘리권"):
            budget += 1
        used_names: list[str] = []
        while budget > 0:
            new_dice = [self.rng.randint(1, 6) for _ in current]
            new_score = score_for(new_dice)
            if new_score <= current_score and current_score >= 0.5:
                break
            card_name = "뭔칙휜" if self._has_trick(player, "뭔칙휜") else "뭘리권"
            consumed = self._consume_trick_by_name(state, player, card_name)
            if consumed is None:
                break
            used_names.append(card_name)
            rerolls.append({"card": card_name, "before": list(current), "after": list(new_dice), "before_score": round(current_score,3), "after_score": round(new_score,3)})
            current = new_dice
            current_score = new_score
            budget -= 1
            if card_name == "뭘리권":
                break
        return current, rerolls

    def _resolve_move(self, state: GameState, player: PlayerState, decision: MovementDecision) -> tuple[int, dict]:
        char = player.current_character
        # Continuous passive from 탐관오리 selected by someone else.
        extra_passive_die = 0
        for p in state.players:
            if (
                p.alive
                and p.player_id != player.player_id
                and p.current_character == "탐관오리"
                and not self._is_muroe_skill_blocked(state, p)
                and player.attribute in {"관원", "상민"}
            ):
                tribute = player.shards // 2
                if tribute > 0:
                    self._pay_or_bankrupt(state, player, tribute, p.player_id)
                extra_passive_die += 1

        used_cards = list(decision.card_values) if decision.use_cards else []
        for c in used_cards:
            player.used_dice_cards.add(c)

        dice: List[int] = []
        if used_cards:
            if len(used_cards) == 1:
                dice.append(self.rng.randint(1, 6))
                move = used_cards[0] + dice[0]
                mode = "card_plus_die"
            else:
                move = sum(used_cards)
                mode = "card_pair_fixed"
        else:
            base_dice = max(1, 2 + player.extra_dice_count_this_turn + extra_passive_die + player.trick_dice_delta_this_turn + self._weather_extra_dice(state))
            dice = [self.rng.randint(1, 6) for _ in range(base_dice)]
            if char == "파발꾼" and len(set(dice)) < len(dice):
                dice.append(self.rng.randint(1, 6))
            move = sum(dice)
            mode = "dice"

        dice, rerolls = self._try_anytime_rerolls(state, player, used_cards, dice, mode)
        if mode == "card_plus_die":
            move = sum(used_cards) + sum(dice)
        elif mode == "dice":
            move = sum(dice)

        if char == "탈출 노비":
            board_len = len(state.board)
            one_short_pos = (player.position + move) % board_len
            target_pos = (one_short_pos + 1) % board_len
            if state.board[target_pos] in {CellKind.F1, CellKind.F2, CellKind.S}:
                move += 1

        player.extra_dice_count_this_turn = 0
        player.trick_dice_delta_this_turn = 0
        meta = {"used_cards": used_cards, "dice": dice, "formula": "+".join(map(str, used_cards + dice)) if (used_cards or dice) else "0", "mode": mode}
        if rerolls:
            meta["rerolls"] = rerolls
        return move, meta

    def _advance_player(self, state: GameState, player: PlayerState, move: int, movement_meta: dict) -> None:
        board_len = len(state.board)
        old_pos = player.position
        old_cash = player.cash
        old_hand = player.hand_coins
        old_shards = player.shards
        old_f = state.f_value
        old_tiles = player.tiles_owned
        old_alive = player.alive

        total_move = move
        encounter_event = None
        if player.trick_encounter_boost_this_turn and move > 0:
            seen = False
            cur = old_pos
            for step in range(1, move):
                cur = (cur + 1) % board_len
                if any(op.alive and op.player_id != player.player_id and op.position == cur for op in state.players):
                    extra = [self.rng.randint(1, 6), self.rng.randint(1, 6)]
                    total_move += sum(extra)
                    encounter_event = {"met_at": cur, "step": step, "extra_dice": extra, "extra_move": sum(extra)}
                    seen = True
                    break
            player.trick_encounter_boost_this_turn = False

        chain_segments: list[dict] = []
        current_start = old_pos
        current_move = total_move
        while True:
            new_total_steps = player.total_steps + current_move
            old_laps = player.total_steps // board_len
            new_laps = new_total_steps // board_len
            player.total_steps = new_total_steps
            player.position = (current_start + current_move) % board_len

            lap_events: List[dict] = []
            for _ in range(new_laps - old_laps):
                lap_events.append(self._apply_lap_reward(state, player))
                if player.current_character == "객주":
                    bonus = self.policy.choose_geo_bonus(state, player, player.current_character)
                    lap_events.append(self._apply_geo_bonus(player, bonus))

            landing_event = self._resolve_landing(state, player)
            chain_segments.append({
                "start_pos": current_start,
                "end_pos": player.position,
                "move": current_move,
                "laps_gained": new_laps - old_laps,
                "lap_events": lap_events,
                "landing": landing_event,
            })
            if not (isinstance(landing_event, dict) and landing_event.get("type") == "ZONE_CHAIN"):
                break
            current_start = player.position
            current_move = landing_event.get("extra_move", 0)
            if current_move <= 0:
                break

        final_segment = chain_segments[-1]
        log_row = {
            "event": "turn",
            "round_index": state.rounds_completed + 1,
            "turn_index_global": state.turn_index + 1,
            "player": player.player_id + 1,
            "character": player.current_character,
            "turn_number_for_player": player.turns_taken,
            "start_pos": old_pos,
            "end_pos": player.position,
            "cell": state.board[player.position].name,
            "move": total_move,
            "movement": movement_meta,
            "laps_gained": sum(seg["laps_gained"] for seg in chain_segments),
            "lap_events": final_segment["lap_events"],
            "landing": final_segment["landing"],
            "cash_before": old_cash, "cash_after": player.cash,
            "hand_coins_before": old_hand, "hand_coins_after": player.hand_coins,
            "shards_before": old_shards, "shards_after": player.shards,
            "tiles_before": old_tiles, "tiles_after": player.tiles_owned,
            "f_before": old_f, "f_after": state.f_value,
            "alive_before": old_alive, "alive_after": player.alive,
        }
        if encounter_event is not None:
            log_row["encounter_bonus"] = encounter_event
        if len(chain_segments) > 1:
            log_row["chain_segments"] = chain_segments
        self._log(log_row)

    def _apply_geo_bonus(self, player: PlayerState, choice: str) -> dict:
        if choice == "cash":
            player.cash += 1
            return {"choice": "geo_cash", "cash_delta": 1}
        if choice == "shards":
            player.shards += 1
            return {"choice": "geo_shards", "shards_delta": 1}
        player.hand_coins += 1
        return {"choice": "geo_coins", "coins_delta": 1}

    def _apply_lap_reward(self, state: GameState, player: PlayerState) -> dict:
        result = self.events.emit_first_non_none("lap.reward.resolve", state, player)
        return result if result is not None else {"choice": "blocked"}

    def _draw_fortune_card(self, state: GameState) -> FortuneCard:
        if not state.fortune_draw_pile:
            state.fortune_draw_pile = list(state.fortune_discard_pile)
            state.fortune_discard_pile = []
            self.rng.shuffle(state.fortune_draw_pile)
            self._log({"event": "fortune_reshuffle", "draw_pile": len(state.fortune_draw_pile)})
        return state.fortune_draw_pile.pop()

    def _is_muroe(self, player: PlayerState) -> bool:
        return player.attribute == "무뢰"

    def _is_japin_or_muroe(self, player: PlayerState) -> bool:
        return player.attribute in {"무뢰", "잡인"}

    def _current_turn_dice_count(self, state: GameState, player: PlayerState, apply_passives: bool = True) -> tuple[int, int]:
        extra_passive_die = 0
        if apply_passives:
            for p in state.players:
                if (
                    p.alive and p.player_id != player.player_id and p.current_character == "탐관오리"
                    and not self._is_muroe_skill_blocked(state, p) and player.attribute in {"관원", "상민"}
                ):
                    tribute = player.shards // 2
                    if tribute > 0:
                        self._pay_or_bankrupt(state, player, tribute, p.player_id)
                    extra_passive_die += 1
        return 2 + player.extra_dice_count_this_turn + extra_passive_die + self._weather_extra_dice(state), extra_passive_die

    def _roll_standard_move(self, state: GameState, player: PlayerState, explicit_dice_count: int | None = None) -> dict:
        if explicit_dice_count is None:
            dice_count, extra_passive_die = self._current_turn_dice_count(state, player, apply_passives=True)
            dice = [self.rng.randint(1, 6) for _ in range(dice_count)]
            if player.current_character == "파발꾼" and len(set(dice)) < len(dice):
                dice.append(self.rng.randint(1, 6))
            return {"dice": dice, "move": sum(dice), "extra_passive_die": extra_passive_die, "mode": "fortune_turn_dice"}
        dice = [self.rng.randint(1, 6) for _ in range(explicit_dice_count)]
        if self.config.rules.dice.enabled:
            remaining = [v for v in self.config.rules.dice.values if v not in player.used_dice_cards]
            max_cards = min(self.config.rules.dice.max_cards_per_turn, len(remaining), explicit_dice_count)
            chosen_cards: list[int] = []
            if max_cards > 0 and player.current_character in {"객주", "파발꾼", "건설업자", "중매꾼"} and explicit_dice_count == 2:
                chosen_cards = sorted(remaining, reverse=True)[:max_cards]
            elif max_cards > 0 and player.cash < 6:
                chosen_cards = sorted(remaining)[:1]
            for c in chosen_cards:
                player.used_dice_cards.add(c)
            if chosen_cards:
                repl = chosen_cards[:explicit_dice_count]
                dice = repl + dice[len(repl):]
        return {"dice": dice, "move": sum(dice), "mode": f"fortune_fixed_{explicit_dice_count}d"}

    def _apply_fortune_arrival_impl(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        old_pos = player.position
        player.position = target_pos % len(state.board)
        landing = self._resolve_landing(state, player)
        return {"type": "ARRIVAL", "trigger": trigger, "card_name": card_name, "start_pos": old_pos, "end_pos": player.position, "landing": landing, "no_lap_credit": True}

    def _apply_fortune_move_only_impl(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        old_pos = player.position
        player.position = target_pos % len(state.board)
        return {"type": "MOVE_ONLY", "trigger": trigger, "card_name": card_name, "start_pos": old_pos, "end_pos": player.position, "no_lap_credit": True}

    def _apply_fortune_arrival(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        result = self.events.emit_first_non_none("fortune.movement.resolve", state, player, target_pos, trigger, card_name, "arrival")
        return result if result is not None else self._apply_fortune_arrival_impl(state, player, target_pos, trigger, card_name)

    def _apply_fortune_move_only(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        result = self.events.emit_first_non_none("fortune.movement.resolve", state, player, target_pos, trigger, card_name, "move_only")
        return result if result is not None else self._apply_fortune_move_only_impl(state, player, target_pos, trigger, card_name)

    def _apply_fortune_card(self, state: GameState, player: PlayerState, card: FortuneCard) -> dict:
        result = self.events.emit_first_non_none("fortune.card.apply", state, player, card)
        return result if result is not None else self._apply_fortune_card_impl(state, player, card)

    def _tile_indices_owned_by(self, state: GameState, owner_id: int) -> list[int]:
        return [i for i, owner in enumerate(state.tile_owner) if owner == owner_id]

    def _select_owned_tile(self, state: GameState, owner_id: int, *, highest: bool = True) -> Optional[int]:
        tiles = self._tile_indices_owned_by(state, owner_id)
        if not tiles:
            return None
        return sorted(tiles, key=lambda i: (state.tile_coins[i], state.board[i] == CellKind.T3, i), reverse=highest)[0]

    def _select_other_player_tile(self, state: GameState, player: PlayerState, *, highest: bool = True) -> Optional[int]:
        tiles = [i for i, owner in enumerate(state.tile_owner) if owner is not None and owner != player.player_id]
        if not tiles:
            return None
        return sorted(tiles, key=lambda i: (state.config.rules.economy.rent_cost_for(state, i) if state.tile_at(i).purchase_cost is not None else 0, state.tile_coins[i], i), reverse=highest)[0]

    def _select_empty_block_tile(self, state: GameState, highest_cost: bool = True) -> Optional[int]:
        candidate_blocks = []
        for block_id in sorted({b for b in state.block_ids if b > 0}):
            idxs = [i for i, b in enumerate(state.block_ids) if b == block_id]
            if not idxs:
                continue
            # "빈 구역"은 구역 전체가 아직 구매되지 않은 일반 토지(T2/T3)로만 구성되어 있어야 한다.
            # 악성 토지, 운수, F칸 등이 섞여 있거나 소유자가 하나라도 있으면 후보가 아니다.
            if all(state.board[i] in {CellKind.T2, CellKind.T3} and state.tile_owner[i] is None for i in idxs):
                candidate_blocks.append(idxs)
        if not candidate_blocks:
            return None
        all_tiles = [i for idxs in candidate_blocks for i in idxs]
        return sorted(all_tiles, key=lambda i: (state.board[i] == CellKind.T3, i), reverse=highest_cost)[0]

    def _roll_standard_dice_only(self, state: GameState, player: PlayerState) -> tuple[int, dict]:
        extra_passive_die = 0
        for p in state.players:
            if (
                p.alive and p.player_id != player.player_id and p.current_character == "탐관오리"
                and not self._is_muroe_skill_blocked(state, p) and player.attribute in {"관원", "상민"}
            ):
                tribute = player.shards // 2
                if tribute > 0:
                    self._pay_or_bankrupt(state, player, tribute, p.player_id)
                extra_passive_die += 1
        base = 2 + (1 if player.current_character == "파발꾼" else 0) + extra_passive_die
        dice = [self.rng.randint(1, 6) for _ in range(max(1, base))]
        if player.current_character == "파발꾼" and len(set(dice)) < len(dice):
            dice.append(self.rng.randint(1, 6))
        dice, rerolls = self._try_anytime_rerolls(state, player, [], dice, "dice")
        meta = {"mode": "dice_chain", "dice": dice, "formula": "+".join(map(str, dice))}
        if rerolls:
            meta["rerolls"] = rerolls
        return sum(dice), meta

    def _is_monopoly_tile(self, state: GameState, pos: int) -> bool:
        owner = state.tile_owner[pos]
        if owner is None:
            return False
        block_id = state.block_ids[pos]
        if block_id < 0:
            return False
        idxs = [i for i, b in enumerate(state.block_ids) if b == block_id]
        if not idxs:
            return False
        return all(state.tile_owner[i] == owner for i in idxs)

    def _takeover_blocked(self, state: GameState, pos: int, new_owner: Optional[int]) -> bool:
        prev_owner = state.tile_owner[pos]
        if prev_owner is None or new_owner is None or prev_owner == new_owner:
            return False
        return state.config.rules.takeover.is_takeover_blocked(self, state, pos, new_owner)

    def _count_monopolies_owned(self, state: GameState, player_id: int) -> int:
        count = 0
        for block_id in sorted({b for b in state.block_ids if b > 0}):
            idxs = [i for i, b in enumerate(state.block_ids) if b == block_id]
            if idxs and all(state.tile_owner[i] == player_id for i in idxs):
                count += 1
        return count

    def _apply_force_sale(self, state: GameState, player: PlayerState, pos: int) -> dict:
        owner = state.tile_owner[pos]
        cell = state.board[pos]
        if owner is None or cell == CellKind.MALICIOUS:
            return {"type": "NO_EFFECT", "reason": "invalid_force_sale"}
        self._consume_trick_by_name(state, player, "강제 매각")
        purchase_refund = state.config.rules.economy.purchase_cost_for(state, pos) if (state.tile_at(pos).purchase_cost is not None and state.config.rules.force_sale.refund_purchase_cost) else 0
        returned_coins = state.tile_coins[pos] if state.config.rules.force_sale.return_tile_coins_to_original_owner else 0
        original_owner = state.players[owner]
        original_owner.cash += purchase_refund
        original_owner.hand_coins += returned_coins
        original_owner.score_coins_placed -= returned_coins
        state.tile_coins[pos] = 0
        state.tile_owner[pos] = None
        original_owner.tiles_owned -= 1
        if state.config.rules.force_sale.block_repurchase_until_next_turn:
            state.tile_purchase_blocked_turn_index[pos] = state.turn_index
        return {"type": "FORCE_SALE", "owner": owner + 1, "tile_kind": cell.name, "purchase_refund": purchase_refund, "returned_coins": returned_coins, "blocked_until_next_turn": state.config.rules.force_sale.block_repurchase_until_next_turn}

    def _transfer_tile(self, state: GameState, pos: int, new_owner: Optional[int]) -> dict:
        prev_owner = state.tile_owner[pos]
        if prev_owner == new_owner:
            return {"pos": pos, "from": None if prev_owner is None else prev_owner + 1, "to": None if new_owner is None else new_owner + 1, "changed": False}
        if self._takeover_blocked(state, pos, new_owner):
            return {"pos": pos, "from": None if prev_owner is None else prev_owner + 1, "to": None if new_owner is None else new_owner + 1, "changed": False, "blocked_by_monopoly": True}
        if prev_owner is not None:
            state.players[prev_owner].tiles_owned -= 1
            state.players[prev_owner].score_coins_placed -= state.tile_coins[pos] if state.config.rules.takeover.transfer_tile_coins else 0
        state.tile_owner[pos] = new_owner
        if new_owner is not None:
            state.players[new_owner].tiles_owned += 1
            state.players[new_owner].score_coins_placed += state.tile_coins[pos] if state.config.rules.takeover.transfer_tile_coins else 0
        return {"pos": pos, "from": None if prev_owner is None else prev_owner + 1, "to": None if new_owner is None else new_owner + 1, "coins": state.tile_coins[pos], "changed": True}

    def _distance_abs(self, a: int, b: int) -> int:
        return abs(a - b)

    def _find_extreme_player_position(self, state: GameState, player: PlayerState, *, nearest: bool) -> Optional[int]:
        others = [p for p in state.players if p.alive and p.player_id != player.player_id]
        if not others:
            return None
        return sorted(others, key=lambda op: (self._distance_abs(player.position, op.position), op.player_id), reverse=not nearest)[0].position

    def _find_extreme_owned_tile(self, state: GameState, player: PlayerState, *, nearest: bool) -> Optional[int]:
        owned = self._tile_indices_owned_by(state, player.player_id)
        if not owned:
            return None
        return sorted(owned, key=lambda pos: (self._distance_abs(player.position, pos), pos), reverse=not nearest)[0]

    def _resolve_fortune_tile(self, state: GameState, player: PlayerState) -> dict:
        result = self.events.emit_first_non_none("fortune.draw.resolve", state, player)
        if result is not None:
            return result
        card = self._draw_fortune_card(state)
        event = self._apply_fortune_card(state, player, card)
        state.fortune_discard_pile.append(card)
        return {"type": "FORTUNE", "card": {"deck_index": card.deck_index, "name": card.name, "effect": card.effect}, "resolution": event}

    def _apply_fortune_card_impl(self, state: GameState, player: PlayerState, card: FortuneCard) -> dict:
        name = card.name.strip()
        board_len = len(state.board)
        attr = player.attribute
        res: dict = {"name": name}
        if name == "자원 재활용":
            return self._fortune_burden_cleanup(state, [player], multiplier=2, payout=True, name=name)
        if name == "모두의 재활용":
            targets = [p for p in state.players if p.alive and p.attribute != "무뢰"]
            return self._fortune_burden_cleanup(state, targets, multiplier=2, payout=True, name=name)
        if name == "화재 발생":
            return self._fortune_burden_cleanup(state, [player], multiplier=1, payout=False, name=name)
        if name == "산불 발생":
            return self._fortune_burden_cleanup(state, [p for p in state.players if p.alive], multiplier=2, payout=False, name=name)
        if name == "이사가세요 - 2":
            return self._apply_fortune_arrival(state, player, player.position - 2, "backward_2", name)
        if name == "이사가세요 - 3":
            return self._apply_fortune_arrival(state, player, player.position - 3, "backward_3", name)
        if name == "인수하세요 - 2":
            return self._fortune_takeover_backward(state, player, 2, name)
        if name == "인수하세요 - 3":
            return self._fortune_takeover_backward(state, player, 3, name)
        if name == "성과금":
            gain = player.shards
            player.cash += gain
            self._strategy_stats[player.player_id]["shard_income_cash"] += gain
            return {"type": "CASH_GAIN", "cash_delta": gain, "formula": "shards*1"}
        if name == "높은 성과금":
            gain = player.shards * 2
            player.cash += gain
            self._strategy_stats[player.player_id]["shard_income_cash"] += gain
            return {"type": "CASH_GAIN", "cash_delta": gain, "formula": "shards*2"}
        if name == "신호 위반":
            cost = 6 + (2 if self._is_muroe(player) else 0)
            return {"type": "BANK_PAY", **self._pay_or_bankrupt(state, player, cost, None)}
        if name == "음주 승마":
            return {"type": "BANK_PAY", **self._pay_or_bankrupt(state, player, 10, None)}
        if name == "청약 당첨":
            pos = self._select_empty_block_tile(state)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_empty_block"}
            return {"type": "SUBSCRIPTION", "selection": pos, "purchase": self._try_purchase_tile(state, player, pos, state.board[pos])}
        if name == "부실 공사":
            pos = self._select_owned_tile(state, player.player_id, highest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            return {"type": "LOSE_TILE", "transfer": self._transfer_tile(state, pos, None)}
        if name == "땅 도둑":
            if self._is_muroe(player):
                pos = self._select_owned_tile(state, player.player_id, highest=False)
                if pos is None:
                    return {"type": "NO_EFFECT", "reason": "muroe_no_owned_tile"}
                return {"type": "MUROE_GIVE_TILE", "transfer": self._transfer_tile(state, pos, state.marker_owner_id)}
            pos = self._select_other_player_tile(state, player, highest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_tile"}
            tr = self._transfer_tile(state, pos, player.player_id)
            if tr.get("blocked_by_monopoly"):
                return {"type": "NO_EFFECT", "reason": "monopoly_protected", "attempt": "steal_tile", "pos": pos}
            return {"type": "STEAL_TILE", "transfer": tr}
        if name == "기부천사":
            pos = self._select_owned_tile(state, player.player_id, highest=False)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            tr = self._transfer_tile(state, pos, state.marker_owner_id)
            if tr.get("blocked_by_monopoly"):
                return {"type": "NO_EFFECT", "reason": "monopoly_protected", "attempt": "give_tile", "pos": pos}
            return {"type": "GIVE_TILE", "transfer": tr}
        if name == "화려한 잔치":
            return self._fortune_party(state, player, amount=2, reverse=self._is_muroe(player), name=name)
        if name == "수상한 음료":
            roll = self._roll_standard_move(state, player, explicit_dice_count=None)
            return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._apply_fortune_arrival(state, player, player.position + roll["move"], "suspicious_drink", name)}
        if name == "아주 수상한 음료":
            roll = self._roll_standard_move(state, player, explicit_dice_count=2)
            return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._apply_fortune_arrival(state, player, player.position + roll["move"], "very_suspicious_drink", name)}
        if name == "반액대매출":
            pos = self._select_owned_tile(state, player.player_id, highest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            sale = math.ceil(state.config.rules.economy.purchase_cost_for(state, pos) / 2)
            player.cash += sale
            tr = self._transfer_tile(state, pos, None)
            state.tile_coins[pos] = 0
            return {"type": "SELL_HALF", "cash_delta": sale, "transfer": tr}
        if name == "축복 주사위":
            d1, d2 = self.rng.randint(1,6), self.rng.randint(1,6)
            total = d1 + d2
            gain = 18 if total == 12 else total
            player.cash += gain
            return {"type": "BLESS_DICE", "dice": [d1,d2], "cash_delta": gain}
        if name == "저주 주사위":
            d1, d2 = self.rng.randint(1,6), self.rng.randint(1,6)
            total = d1 + d2
            cost = 18 if total == 2 else total
            return {"type": "CURSE_DICE", "dice": [d1,d2], **self._pay_or_bankrupt(state, player, cost, None)}
        if name == "남 좋은 일":
            for op in state.players:
                if op.alive and op.player_id != player.player_id:
                    op.cash += 4
            return {"type": "OTHERS_GAIN", "amount": 4}
        if name == "배가 아픈 일":
            marker_owner = state.players[state.marker_owner_id]
            if marker_owner.turns_taken >= state.rounds_completed + 1:
                return {"type": "NO_EFFECT", "reason": "marker_owner_turn_passed"}
            marker_owner.free_purchase_this_turn = True
            return {"type": "MARKER_FREE_PURCHASE", "target_player": marker_owner.player_id + 1}
        if name == "참을 수 없는 미소":
            for op in state.players:
                if not op.alive or op.player_id == player.player_id:
                    continue
                mult = 2 if op.attribute == "무뢰" else 1
                out = self._pay_or_bankrupt(state, op, 3 * mult, None)
                if not op.alive:
                    return {"type": "OTHERS_BANK_PAY", "failed_player": op.player_id + 1, "amount": 3 * mult}
            return {"type": "OTHERS_BANK_PAY", "amount": 3}
        if name == "거절할 수 없는 거래":
            own = self._select_owned_tile(state, player.player_id, highest=False)
            other = self._select_other_player_tile(state, player, highest=True)
            if own is None or other is None:
                return {"type": "NO_EFFECT", "reason": "missing_trade_target"}
            other_owner = state.tile_owner[other]
            extra = 0
            if player.attribute in {"무뢰", "상민"}:
                extra = state.config.rules.economy.rent_cost_for(state, other)
                out = self._pay_or_bankrupt(state, player, extra, other_owner)
                if not out.get("paid"):
                    return {"type": "TRADE_FAIL", "reason": "extra_payment_bankrupt", **out}
            t1 = self._transfer_tile(state, own, other_owner)
            t2 = self._transfer_tile(state, other, player.player_id)
            if t1.get("blocked_by_monopoly") or t2.get("blocked_by_monopoly"):
                return {"type": "TRADE_FAIL", "reason": "monopoly_protected", "own_to_other": t1, "other_to_self": t2}
            return {"type": "FORCED_TRADE", "extra_payment": extra, "own_to_other": t1, "other_to_self": t2}
        if name == "경건한 징표":
            if state.marker_owner_id == player.player_id:
                pos = self._select_empty_block_tile(state)
                if pos is None:
                    return {"type": "NO_EFFECT", "reason": "no_empty_block"}
                state.tile_owner[pos] = player.player_id
                player.tiles_owned += 1
                return {"type": "PIOUS_MARKER_GAIN_TILE", "pos": pos}
            return {"type": "PAY_MARKER_OWNER", **self._pay_or_bankrupt(state, player, 4, state.marker_owner_id)}
        if name == "야수의 심장":
            return self._fortune_beast_heart(state, player)
        if name == "짧은 여행":
            pos = self._find_extreme_player_position(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            return self._apply_fortune_arrival(state, player, pos, "nearest_player", name)
        if name == "끼어들기":
            pos = self._find_extreme_player_position(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            if self._is_japin_or_muroe(player):
                return self._apply_fortune_arrival(state, player, pos, "nearest_player_arrival", name)
            return self._apply_fortune_move_only(state, player, pos, "nearest_player_move", name)
        if name == "긴 여행":
            pos = self._find_extreme_player_position(state, player, nearest=False)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            return self._apply_fortune_arrival(state, player, pos, "furthest_player", name)
        if name in {"휴게소", "휴게소 ", " 휴게소"}:
            pos = self._find_extreme_owned_tile(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tiles"}
            if self._is_japin_or_muroe(player):
                pos = (pos + 1) % board_len
            return self._apply_fortune_arrival(state, player, pos, "nearest_owned_tile", name)
        if name == "안전 이동":
            pos = self._find_extreme_owned_tile(state, player, nearest=False)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tiles"}
            if self._is_japin_or_muroe(player):
                pos = (pos + 1) % board_len
            return self._apply_fortune_arrival(state, player, pos, "furthest_owned_tile", name)
        if name == "운석 낙하":
            self._change_f(state, 2, reason="fortune_effect", source="운석 낙하", actor_pid=player.player_id)
            player.shards += 2
            return {"type": "METEOR", "f_delta": 2, "shards_delta": 2}
        if name == "돼지 꿈":
            remaining = [v for v in self.config.rules.dice.values if v not in player.used_dice_cards]
            gained = []
            for _ in range(2):
                if not remaining:
                    break
                pick = self.rng.choice(remaining)
                remaining.remove(pick)
                player.used_dice_cards.discard(pick)
                gained.append(pick)
            return {"type": "GAIN_DICE_CARDS", "cards": gained}
        return {"type": "UNIMPLEMENTED", "name": name}

    def _default_fortune_burden_cleanup(self, state: GameState, targets: list[PlayerState], multiplier: int, payout: bool, name: str) -> dict:
        affected = []
        total_amount = 0
        for target in targets:
            burdens = list(self._burden_cards(target))
            if not burdens:
                continue
            cost = sum(c.burden_cost for c in burdens) * multiplier
            for card in burdens:
                self._discard_trick(state, target, card)
            if payout:
                target.cash += cost
                paid = True
                bankrupt = False
            else:
                out = self._pay_or_bankrupt(state, target, cost, None)
                paid = out.get("paid", False)
                bankrupt = out.get("bankrupt", False)
            total_amount += cost if paid else 0
            affected.append({"player": target.player_id + 1, "removed": [c.name for c in burdens], "amount": cost, "payout": payout, "bankrupt": bankrupt})
        return {"type": "BURDEN_CLEANUP", "fortune": name, "affected": affected, "total_amount": total_amount, "payout": payout}

    def _fortune_burden_cleanup(self, state: GameState, targets: list[PlayerState], multiplier: int, payout: bool, name: str) -> dict:
        self._log({"event": "fortune_cleanup_before", "fortune": name, "multiplier": multiplier, "payout": payout, "targets": [t.player_id + 1 for t in targets if t.alive]})
        result = self.events.emit_first_non_none("fortune.cleanup.resolve", state, targets, multiplier, payout, name)
        if result is None:
            result = self._default_fortune_burden_cleanup(state, targets, multiplier, payout, name)
        self._log({"event": "fortune_cleanup_after", "fortune": name, "result_type": result.get("type"), "affected": len(result.get("affected", []))})
        return result

    def _fortune_takeover_backward(self, state: GameState, player: PlayerState, steps: int, card_name: str) -> dict:
        pos = (player.position - steps) % len(state.board)
        owner = state.tile_owner[pos]
        cell = state.board[pos]
        if cell in {CellKind.F1, CellKind.F2, CellKind.S}:
            player.position = pos
            return {"type": "NO_EFFECT", "reason": "special_tile", "end_pos": pos}
        if owner is None:
            player.position = pos
            return {"type": "NO_EFFECT", "reason": "unowned_tile", "end_pos": pos}
        if owner == player.player_id:
            player.position = pos
            tr = self._transfer_tile(state, pos, state.marker_owner_id)
            if tr.get("blocked_by_monopoly"):
                return {"type": "NO_EFFECT", "reason": "monopoly_protected", "end_pos": pos}
            return {"type": "TRANSFER_TO_MARKER", "end_pos": pos, "transfer": tr}
        player.position = pos
        tr = self._transfer_tile(state, pos, player.player_id)
        if tr.get("blocked_by_monopoly"):
            return {"type": "NO_EFFECT", "reason": "monopoly_protected", "end_pos": pos}
        return {"type": "FORCED_TAKEOVER", "end_pos": pos, "transfer": tr}

    def _fortune_party(self, state: GameState, player: PlayerState, amount: int, reverse: bool, name: str) -> dict:
        if reverse:
            total = 0
            for op in state.players:
                if op.alive and op.player_id != player.player_id:
                    out = self._pay_or_bankrupt(state, op, amount, player.player_id)
                    total += amount if out.get("paid") else 0
            return {"type": "REVERSE_PARTY", "amount": amount, "total_received": total}
        paid_to = []
        for op in state.players:
            if op.alive and op.player_id != player.player_id:
                out = self._pay_or_bankrupt(state, player, amount, op.player_id)
                paid_to.append({"player": op.player_id + 1, **out})
                if not player.alive:
                    break
        return {"type": "PARTY_PAY", "amount": amount, "paid_to": paid_to}

    def _fortune_beast_heart(self, state: GameState, player: PlayerState) -> dict:
        rolls = {}
        def roll_until_unique(exclude: set[int]):
            while True:
                v = self.rng.randint(1, 6)
                if v not in exclude:
                    return v
        used = set()
        self_roll = roll_until_unique(used)
        used.add(self_roll)
        rolls[player.player_id + 1] = self_roll
        lower = []
        higher = []
        for op in state.players:
            if not op.alive or op.player_id == player.player_id:
                continue
            v = roll_until_unique(used)
            used.add(v)
            rolls[op.player_id + 1] = v
            if v < self_roll:
                lower.append(op.player_id)
            else:
                higher.append(op.player_id)
        if lower:
            total = 0
            for pid in lower:
                out = self._pay_or_bankrupt(state, state.players[pid], 4, player.player_id)
                total += 4 if out.get("paid") else 0
            return {"type": "BEAST_HEART_WIN", "rolls": rolls, "total_received": total}
        total_paid = []
        for pid in higher:
            out = self._pay_or_bankrupt(state, player, 5, pid)
            total_paid.append({"player": pid + 1, **out})
            if not player.alive:
                break
        return {"type": "BEAST_HEART_LOSE", "rolls": rolls, "payments": total_paid}

    def _resolve_landing(self, state: GameState, player: PlayerState) -> dict:
        pos = player.position
        cell = state.board[pos]
        if len(self._strategy_stats) <= player.player_id:
            self._strategy_stats = [
                {
                    "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                    "rent_paid": 0, "own_tile_visits": 0,
                    "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                    "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                    "malicious_visits": 0, "bankruptcies": 0,
                    "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                    "tricks_used": 0, "anytime_tricks_used": 0, "regular_tricks_used": 0,
                    "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                    "coins_gained_own_tile": 0, "coins_placed": 0,
                    "mark_attempts": 0, "mark_successes": 0,
                    "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                    "character": "", "shards_gained_f": 0, "shards_gained_lap": 0, "shard_income_cash": 0,
                    "draft_cards": [], "marked_target_names": [],
                }
                for _ in range(state.config.player_count)
            ]
        stats = self._strategy_stats[player.player_id]
        block_id = state.block_ids[pos]
        owns_block = block_id > 0 and any(state.tile_owner[i] == player.player_id for i, b in enumerate(state.block_ids) if b == block_id)

        if cell in {CellKind.T2, CellKind.T3, CellKind.MALICIOUS} and owns_block and self._has_trick(player, "뇌절왕"):
            consumed = self._consume_trick_by_name(state, player, "뇌절왕")
            extra_move, chain_meta = self._roll_standard_dice_only(state, player)
            return {"type": "ZONE_CHAIN", "via_card": None if consumed is None else consumed.name, "tile_kind": cell.name, "block_id": block_id, "extra_move": extra_move, "movement": chain_meta, "landing_treated_as_move": True}

        if cell in {CellKind.F1, CellKind.F2}:
            result = self.events.emit_first_non_none("landing.f.resolve", state, player, pos, cell)
            if result is not None:
                return result
        if cell == CellKind.S:
            result = self.events.emit_first_non_none("landing.s.resolve", state, player, pos)
            if result is not None:
                return result
        if cell == CellKind.MALICIOUS:
            result = self.events.emit_first_non_none("landing.malicious.resolve", state, player, pos)
            if result is not None:
                return result

        owner = state.tile_owner[pos]
        if owner is not None and self._has_trick(player, "강제 매각"):
            result = self.events.emit_first_non_none("landing.force_sale.resolve", state, player, pos, cell)
            if result is not None:
                return result

        character_effect = self.events.emit_first_non_none("tile.character.effect", state, player, pos, owner)
        if character_effect is not None:
            return character_effect

        if owner is None:
            result = self.events.emit_first_non_none("landing.unowned.resolve", state, player, pos, cell)
            if result is not None:
                return result
            return self._apply_weather_same_tile_bonus(state, player, {"type": "UNOWNED_FAILSAFE", "tile_kind": cell.name})

        if owner == player.player_id:
            result = self.events.emit_first_non_none("landing.own_tile.resolve", state, player, pos, cell)
            if result is not None:
                return result
            return self._apply_weather_same_tile_bonus(state, player, {"type": "OWN_TILE_FAILSAFE", "tile_kind": cell.name})

        rent_result = self.events.emit_first_non_none("rent.payment.resolve", state, player, pos, owner)
        if rent_result is not None:
            return rent_result
        return self._apply_weather_same_tile_bonus(state, player, {"type": "RENT_FAILSAFE", "tile_kind": cell.name, "owner": owner + 1})

    def _matchmaker_buy_adjacent(self, state: GameState, player: PlayerState, pos: int) -> Optional[int]:
        block_id = state.block_ids[pos]
        if block_id < 0 or state.board[pos] not in (CellKind.T2, CellKind.T3):
            return None
        candidates: list[int] = []
        for idx, bid in enumerate(state.block_ids):
            if bid != block_id or idx == pos:
                continue
            if state.board[idx] not in (CellKind.T2, CellKind.T3) or state.tile_owner[idx] is not None:
                continue
            if abs(idx - pos) == 1:
                candidates.append(idx)
        if not candidates:
            return None
        candidates.sort(key=lambda i: (state.config.rules.economy.purchase_cost_for(state, i), i))
        idx = candidates[0]
        cost = state.config.rules.economy.purchase_cost_for(state, idx)
        shard_cost = 1 if player.current_character == "중매꾼" else 0
        if player.cash < cost:
            return None
        if shard_cost > 0 and player.shards < shard_cost:
            return None
        if not getattr(self.policy, "choose_purchase_tile", lambda *args, **kwargs: True)(state, player, idx, state.board[idx], cost, source="matchmaker_adjacent"):
            return None
        player.cash -= cost
        if shard_cost > 0:
            player.shards -= shard_cost
        state.tile_owner[idx] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[idx] = player.turns_taken
        return idx

    def _try_purchase_tile(self, state: GameState, player: PlayerState, pos: int, cell: CellKind) -> dict:
        result = self.events.emit_first_non_none("tile.purchase.attempt", state, player, pos, cell)
        if result is not None:
            return result
        return {"type": "PURCHASE_FAIL", "tile_kind": cell.name, "reason": "no_purchase_handler"}

    def _place_hand_coins_on_tile(self, state: GameState, player: PlayerState, target: int, *, max_place: Optional[int] = None, source: str = "visit") -> Optional[dict]:
        if player.hand_coins <= 0:
            return None
        room = state.config.rules.token.tile_capacity(state, target) - state.tile_coins[target]
        limit = state.config.rules.token.max_place_per_visit if max_place is None else max_place
        amount = min(player.hand_coins, room, limit)
        if amount <= 0:
            return None
        state.tile_coins[target] += amount
        player.hand_coins -= amount
        player.score_coins_placed += amount
        self._strategy_stats[player.player_id]["coins_placed"] += amount
        return {"target": target, "amount": amount, "tile_total_after": state.tile_coins[target], "source": source}

    def _place_hand_coins_if_possible(self, state: GameState, player: PlayerState) -> Optional[dict]:
        if player.hand_coins <= 0:
            return None
        target = self.policy.choose_coin_placement_tile(state, player)
        if target is None:
            return None
        return self._place_hand_coins_on_tile(state, player, target, source="visit")

    def _pay_or_bankrupt(self, state: GameState, player: PlayerState, cost: int, receiver: int | None) -> dict:
        frame = inspect.currentframe()
        caller_frame = frame.f_back if frame is not None else None
        caller_function = caller_frame.f_code.co_name if caller_frame is not None else None
        active_pid = None
        if state.current_round_order:
            active_pid = state.current_round_order[state.turn_index % max(1, len(state.current_round_order))] + 1
        payment_attempt = {
            "player_id": player.player_id + 1,
            "required_cost": cost,
            "receiver_player_id": None if receiver is None else receiver + 1,
            "cash_before": player.cash,
            "position": player.position,
            "character": player.current_character,
            "turn_index": state.turn_index,
            "round_index": state.rounds_completed + 1,
            "caller_function": caller_function,
            "last_semantic_event": self._last_semantic_event_name,
            "active_player_id": active_pid,
            "is_offturn_payment": active_pid is not None and active_pid != (player.player_id + 1),
            "tile_kind": state.tile_at(player.position).kind.name if 0 <= player.position < len(state.tiles) else None,
        }
        self._last_payment_attempt_by_player[player.player_id] = dict(payment_attempt)
        result = self.events.emit_first_non_none("payment.resolve", state, player, cost, receiver)
        if result is None:
            result = {"cost": cost, "receiver": None if receiver is None else receiver + 1, "paid": True, "bankrupt": False}
        if result.get("bankrupt"):
            result["forensic_payment"] = dict(payment_attempt)
        return result

    def _bankrupt(self, state: GameState, player: PlayerState) -> None:
        self.events.emit_first_non_none("bankruptcy.resolve", state, player)

    def _apply_marker_management(self, state: GameState, player: PlayerState) -> None:
        self.events.emit_first_non_none("marker.management.apply", state, player)

    def _check_end(self, state: GameState) -> bool:
        result = self.events.emit_first_non_none("game.end.evaluate", state)
        return bool(result) if result is not None else False

    def _evaluate_end_rules(self, state: GameState) -> str | None:
        return state.config.rules.end.evaluate_end_reason(self, state)

    def _determine_winners(self, state: GameState) -> List[int]:
        ranking = []
        for p in state.players:
            ranking.append((state.total_score(p.player_id), p.tiles_owned, p.cash, p.player_id))
        ranking.sort(reverse=True)
        best = ranking[0][:3]
        return [pid for score, tiles, cash, pid in ranking if (score, tiles, cash) == best]

    def _build_result(self, state: GameState) -> GameResult:
        summary = []
        board_len = len(state.board)
        for p in state.players:
            laps_completed = p.total_steps // board_len
            lap_rewards_received = (
                self._strategy_stats[p.player_id].get("lap_cash_choices", 0)
                + self._strategy_stats[p.player_id].get("lap_coin_choices", 0)
                + self._strategy_stats[p.player_id].get("lap_shard_choices", 0)
            )
            summary.append({
                "player_id": p.player_id,
                "alive": p.alive,
                "cash": p.cash,
                "tiles_owned": p.tiles_owned,
                "placed_score_coins": p.score_coins_placed,
                "hand_coins": p.hand_coins,
                "shards": p.shards,
                "turns_taken": p.turns_taken,
                "used_cards": sorted(p.used_dice_cards),
                "character": self._strategy_stats[p.player_id].get("last_selected_character", p.current_character),
                "tricks": [c.name for c in p.trick_hand],
                "public_tricks": p.public_trick_names(),
                "hidden_trick_count": p.hidden_trick_count(),
                "score": state.total_score(p.player_id),
                "laps_completed": laps_completed,
                "lap_rewards_received": lap_rewards_received,
                "bankruptcy_info": self._player_bankruptcy_info.get(p.player_id),
            })
        strategy_summary = []
        for p in state.players:
            row = dict(self._strategy_stats[p.player_id])
            attempts = row.get("mark_attempts", 0)
            successes = row.get("mark_successes", 0)
            last_selected_character = self._strategy_stats[p.player_id].get("last_selected_character", p.current_character)
            row.update({
                "player_id": p.player_id,
                "score": state.total_score(p.player_id),
                "tiles_owned": p.tiles_owned,
                "placed_score_coins": p.score_coins_placed,
                "hand_coins": p.hand_coins,
                "shards": p.shards,
                "cash": p.cash,
                "alive": p.alive,
                "turns_taken": p.turns_taken,
                "character": last_selected_character,
                "last_selected_character": last_selected_character,
                "final_character_choice_counts": dict(row.get("character_choice_counts", {})),
                "laps_completed": p.total_steps // board_len,
                "lap_rewards_received": (
                    row.get("lap_cash_choices", 0)
                    + row.get("lap_coin_choices", 0)
                    + row.get("lap_shard_choices", 0)
                ),
                "mark_success_rate": (successes / attempts) if attempts else 0.0,
            })
            strategy_summary.append(row)
        return GameResult(
            winner_ids=state.winner_ids,
            end_reason=state.end_reason,
            total_turns=sum(p.turns_taken for p in state.players),
            rounds_completed=state.rounds_completed,
            alive_count=state.alive_count(),
            bankrupt_players=state.bankrupt_players,
            final_f_value=state.f_value,
            total_placed_coins=sum(state.tile_coins),
            player_summary=summary,
            strategy_summary=strategy_summary,
            weather_history=list(self._weather_history),
            action_log=list(self._action_log),
            bankruptcy_events=list(self._bankruptcy_events),
        )
