from __future__ import annotations

import random
import inspect
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional
import math

from ai_policy import BasePolicy, MovementDecision
from characters import CHARACTERS, CARD_TO_NAMES, randomized_active_by_card
from config import CellKind, GameConfig
from policy_mark_utils import ordered_public_mark_targets
from state import GameState, PlayerState
from fortune_cards import FortuneCard
from trick_cards import TrickCard
from weather_cards import WeatherCard, COLOR_RENT_DOUBLE_WEATHERS
from event_system import EventDispatcher
from effect_handlers import EngineEffectHandlers
from policy.character_traits import (
    is_assassin,
    is_bandit,
    is_baksu,
    is_builder,
    is_chunokkun,
    is_doctrine_character,
    is_eosa,
    is_gakju,
    is_mansin,
    is_matchmaker,
    is_pabalggun,
    is_tamgwanori,
)
from policy.environment_traits import fortune_card_id_for_name
from policy_hooks import PolicyDecisionLogHook
from rule_script_engine import RuleScriptEngine
from viewer.events import Phase, VisEvent
from viewer.public_state import build_player_public_state, build_turn_end_snapshot
from viewer.stream import VisEventStream


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
    ai_decision_log: List[dict] = field(default_factory=list)
    bankruptcy_events: List[dict] = field(default_factory=list)


@dataclass(slots=True)
class DecisionRequest:
    decision_name: str
    request_type: str
    state: GameState
    player: PlayerState
    player_id: int
    round_index: int | None
    turn_index: int | None
    public_context: dict[str, Any] = field(default_factory=dict)
    fallback_policy: str = "engine_default"
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    fallback: Callable[[], Any] | None = None


class DecisionPort:
    def __init__(self, policy: BasePolicy) -> None:
        self._policy = policy

    def request(self, request: DecisionRequest) -> Any:
        decision_fn = getattr(self._policy, request.decision_name, None)
        if decision_fn is None:
            if request.fallback is not None:
                return request.fallback()
            raise AttributeError(request.decision_name)
        return decision_fn(request.state, request.player, *request.args, **request.kwargs)


class GameEngine:
    def __init__(
        self,
        config: GameConfig,
        policy: BasePolicy,
        rng: random.Random | None = None,
        enable_logging: bool = False,
        event_stream: VisEventStream | None = None,
        decision_port: DecisionPort | None = None,
        decision_request_factory: Callable[..., DecisionRequest] | None = None,
    ):
        self.config = config
        self.policy = policy
        self.decision_port = decision_port or DecisionPort(policy)
        self._decision_request_factory = decision_request_factory or self._default_decision_request_factory
        self.rng = rng or random.Random()
        if hasattr(self.policy, "set_rng"):
            self.policy.set_rng(self.rng)
        self.enable_logging = enable_logging
        self._action_log: List[dict] = []
        self._ai_decision_log: List[dict] = []
        self._strategy_stats: List[dict] = []
        self._weather_history: List[str] = []
        self._bankruptcy_events: List[dict] = []
        self._last_payment_attempt_by_player: dict[int, dict] = {}
        self._player_bankruptcy_info: dict[int, dict] = {}
        self._last_semantic_event_name: str | None = None
        self._vis_stream: VisEventStream | None = event_stream
        self._vis_step: int = 0
        self._vis_session_id: str = ""
        self._vis_buffer: list[tuple[str, str, int | None, dict[str, Any]]] | None = None
        self.events = EventDispatcher()
        self.events.set_trace_hook(self._trace_semantic_event)
        self.rule_scripts = RuleScriptEngine(self, getattr(config, "rule_scripts_path", None))
        self.effect_handlers = EngineEffectHandlers(self)
        self.effect_handlers.register_default_handlers(self.events)
        if hasattr(self.policy, "register_policy_hook"):
            decision_log_hook = PolicyDecisionLogHook(self)
            self.policy.register_policy_hook("policy.before_decision", decision_log_hook.before_decision)
            self.policy.register_policy_hook("policy.after_decision", decision_log_hook.after_decision)

    def _request_decision(
        self,
        decision_name: str,
        state: GameState,
        player: PlayerState,
        *args: Any,
        fallback: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        request = self._build_decision_request(
            decision_name,
            state,
            player,
            *args,
            fallback=fallback,
            **kwargs,
        )
        return self.decision_port.request(request)

    def _build_decision_request(
        self,
        decision_name: str,
        state: GameState,
        player: PlayerState,
        *args: Any,
        fallback: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> DecisionRequest:
        return self._decision_request_factory(
            decision_name,
            state,
            player,
            tuple(args),
            dict(kwargs),
            fallback,
            self,
        )

    def _default_decision_request_factory(
        self,
        decision_name: str,
        state: GameState,
        player: PlayerState,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        fallback: Callable[[], Any] | None,
        engine: GameEngine,
    ) -> DecisionRequest:
        del engine
        request_type = self._decision_request_type(decision_name)
        public_context = self._decision_public_context(decision_name, state, player, args, kwargs)
        return DecisionRequest(
            decision_name=decision_name,
            request_type=request_type,
            state=state,
            player=player,
            player_id=player.player_id,
            round_index=state.rounds_completed + 1 if hasattr(state, "rounds_completed") else None,
            turn_index=state.turn_index + 1 if hasattr(state, "turn_index") else None,
            public_context=public_context,
            fallback_policy="engine_default" if fallback is not None else "required",
            args=args,
            kwargs=kwargs,
            fallback=fallback,
        )
    def _decision_request_type(self, decision_name: str) -> str:
        request_type_map = {
            "choose_movement": "movement",
            "choose_runaway_slave_step": "runaway_step_choice",
            "choose_purchase_tile": "purchase_tile",
            "choose_coin_placement_tile": "coin_placement",
            "choose_doctrine_relief_target": "doctrine_relief",
            "choose_active_flip_card": "active_flip",
            "choose_burden_exchange_on_supply": "burden_exchange",
            "choose_trick_tile_target": "trick_tile_target",
        }
        return request_type_map.get(decision_name, decision_name.removeprefix("choose_"))

    def _decision_public_context(
        self,
        decision_name: str,
        state: GameState,
        player: PlayerState,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "round_index": state.rounds_completed + 1 if hasattr(state, "rounds_completed") else None,
            "turn_index": state.turn_index + 1 if hasattr(state, "turn_index") else None,
            "player_position": getattr(player, "position", None),
            "player_cash": getattr(player, "cash", None),
            "player_shards": getattr(player, "shards", None),
        }
        if decision_name in {"choose_draft_card", "choose_final_character"} and args:
            context["choice_count"] = len(args[0]) if isinstance(args[0], list) else None
        elif decision_name == "choose_purchase_tile" and len(args) >= 3:
            context["tile_index"] = args[0]
            context["cost"] = args[2]
            context["source"] = kwargs.get("source", "landing")
        elif decision_name == "choose_mark_target" and args:
            context["actor_name"] = args[0]
        elif decision_name == "choose_trick_to_use" and args:
            context["hand_count"] = len(args[0]) if isinstance(args[0], list) else None
        elif decision_name == "choose_active_flip_card" and args:
            context["flip_count"] = len(args[0]) if isinstance(args[0], list) else None
        elif decision_name == "choose_runaway_slave_step" and len(args) >= 3:
            context["one_short_pos"] = args[0]
            context["bonus_target_pos"] = args[1]
            context["bonus_target_kind"] = str(args[2])
        elif decision_name == "choose_specific_trick_reward" and args:
            context["reward_count"] = len(args[0]) if isinstance(args[0], list) else None
        elif decision_name == "choose_doctrine_relief_target" and args:
            context["candidate_count"] = len(args[0]) if isinstance(args[0], list) else None
        elif decision_name == "choose_coin_placement_tile":
            owned_tiles = getattr(player, "visited_owned_tile_indices", None)
            if owned_tiles is not None:
                context["owned_tile_count"] = len(list(owned_tiles))
        elif decision_name == "choose_trick_tile_target":
            if len(args) >= 3:
                context["card_name"] = args[0]
                context["candidate_count"] = len(args[1]) if isinstance(args[1], list) else None
                context["target_scope"] = str(args[2])
        return {key: value for key, value in context.items() if value is not None}

    def run(self) -> GameResult:
        self._action_log = []
        self._ai_decision_log = []
        self._weather_history = []
        self._bankruptcy_events = []
        self._last_payment_attempt_by_player = {}
        self._player_bankruptcy_info = {}
        self._last_semantic_event_name = None
        self._vis_step = 0
        self._vis_session_id = str(uuid.uuid4())
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
        self._emit_vis(
            "session_start",
            Phase.SESSION_START,
            None,
            state,
            player_count=self.config.player_count,
            active_by_card=dict(state.active_by_card),
            players=[build_player_public_state(p, state).to_dict() for p in state.players],
        )
        self._start_new_round(state, initial=True)

        while True:
            if not state.current_round_order:
                if self._check_end(state):
                    break
                self._start_new_round(state, initial=False)
                if not state.current_round_order:
                    break
            current_pid = state.current_round_order[state.turn_index % len(state.current_round_order)]
            player = state.players[current_pid]
            if player.alive:
                player.turns_taken += 1
                self._take_turn(state, player)
                if self._check_end(state):
                    break
            state.turn_index += 1
            if state.turn_index % max(1, len(state.current_round_order)) == 0:
                self._apply_round_end_marker_management(state)
                state.rounds_completed += 1
                self._start_new_round(state, initial=False)
        result = self._build_result(state)
        self._emit_vis(
            "game_end",
            Phase.GAME_END,
            None,
            state,
            winner_ids=[winner + 1 for winner in result.winner_ids],
            winner_player_id=(result.winner_ids[0] + 1) if result.winner_ids else None,
            end_reason=result.end_reason,
            reason=result.end_reason,
            total_turns=result.total_turns,
            snapshot=build_turn_end_snapshot(state),
        )
        return result

    def _log(self, row: dict) -> None:
        if self.enable_logging:
            self._action_log.append(row)

    def _record_ai_decision(
        self,
        state: GameState | None,
        player: PlayerState | None,
        decision_key: str,
        payload: dict | None,
        *,
        result: object | None = None,
        source_event: str = "",
        extra: dict | None = None,
    ) -> None:
        if player is None or payload is None:
            return
        row = {
            "event": "ai_decision",
            "decision_key": decision_key,
            "source_event": source_event,
            "player_id": player.player_id + 1,
            "character": player.current_character,
            "payload": dict(payload),
        }
        if state is not None:
            row["round_index"] = state.rounds_completed + 1
            row["turn_index"] = state.turn_index + 1
            row["turn_index_for_player"] = player.turns_taken
            row["position"] = player.position
            row["f_value"] = state.f_value
        if result is not None:
            row["result"] = result
        if extra:
            row.update(extra)
        self._ai_decision_log.append(row)

    def _emit_vis(
        self,
        event_type: str,
        public_phase: str,
        acting_player_id: int | None,
        state: GameState,
        **payload,
    ) -> None:
        if self._vis_stream is None:
            return
        if self._vis_buffer is not None:
            self._vis_buffer.append((event_type, public_phase, acting_player_id, dict(payload)))
            return
        self._vis_stream.append(
            VisEvent(
                event_type=event_type,
                session_id=self._vis_session_id,
                round_index=state.rounds_completed + 1,
                turn_index=state.turn_index + 1,
                step_index=self._vis_step,
                acting_player_id=acting_player_id,
                public_phase=public_phase,
                payload=dict(payload),
            )
        )
        self._vis_step += 1

    def _drain_buffered_vis_events(self, state: GameState) -> None:
        pending = self._vis_buffer or []
        self._vis_buffer = None
        for event_type, public_phase, acting_player_id, payload in pending:
            self._emit_vis(event_type, public_phase, acting_player_id, state, **payload)

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
            hidden_debug = self.policy.pop_debug("hide_trick", player.player_id) if hasattr(self.policy, "pop_debug") else None
            if hidden_debug is not None:
                self._record_ai_decision(
                    state,
                    player,
                    "hidden_trick",
                    hidden_debug,
                    result=None if chosen is None else {"deck_index": chosen.deck_index, "name": chosen.name},
                    source_event="hide_trick",
                )
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
            other.alive and other.player_id != player.player_id and is_eosa(other.current_character)
            for other in state.players
        )

    def _character_def(self, player: PlayerState):
        if not player.current_character:
            return None
        return CHARACTERS.get(player.current_character)

    def _character_card_no(self, player: PlayerState) -> int | None:
        char_def = self._character_def(player)
        return None if char_def is None else int(char_def.card_no)

    def _is_character_front_face(self, player: PlayerState) -> bool:
        char_def = self._character_def(player)
        return bool(char_def.starting_active) if char_def is not None else False

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

    def _apply_round_weather(self, state: GameState) -> dict:
        result = self.events.emit_first_non_none("weather.round.apply", state)
        if result is None:
            raise RuntimeError("weather.round.apply handler returned no result")
        return result

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
            p.trick_all_rent_waiver_this_turn = False
            p.trick_free_purchase_this_turn = False
            p.trick_dice_delta_this_turn = 0
            p.rolled_dice_count_this_turn = 0
            p.trick_personal_rent_half_this_turn = False
            p.trick_same_tile_cash2_this_turn = False
            p.trick_same_tile_shard_rake_this_turn = False
            p.trick_one_extra_adjacent_buy_this_turn = False
            p.trick_encounter_boost_this_turn = False
            p.trick_force_sale_landing_this_turn = False
            p.trick_obstacle_this_round = False
            p.trick_zone_chain_this_turn = False
            p.trick_reroll_budget_this_turn = 0
            p.trick_reroll_label_this_turn = ""
        state.global_rent_half_this_turn = False
        state.global_rent_double_this_turn = False
        state.tile_rent_modifiers_this_turn = {}
        state.current_weather = None
        state.current_weather_effects = set()
        self._resolve_marker_flip(state)
        alive_ids = [p.player_id + 1 for p in state.players if p.alive]
        self._emit_vis(
            "round_start",
            Phase.WEATHER,
            None,
            state,
            initial=bool(initial),
            alive_player_ids=alive_ids,
            marker_owner_player_id=state.marker_owner_id + 1,
            marker_draft_direction=("clockwise" if state.marker_draft_clockwise else "counterclockwise"),
            active_by_card=dict(state.active_by_card),
        )
        self._apply_round_weather(state)
        self._emit_vis(
            "weather_reveal",
            Phase.WEATHER,
            None,
            state,
            weather=state.current_weather.name if state.current_weather else None,
            weather_name=state.current_weather.name if state.current_weather else None,
            weather_effect=state.current_weather.effect if state.current_weather else None,
            effect_text=state.current_weather.effect if state.current_weather else None,
            description=state.current_weather.effect if state.current_weather else None,
            effects=list(state.current_weather_effects),
            active_by_card=dict(state.active_by_card),
        )
        self._run_draft(state)
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
            "marker_draft_direction": ("clockwise" if state.marker_draft_clockwise else "counterclockwise"),
            "active_by_card": dict(state.active_by_card),
        })
        self._emit_vis(
            "round_order",
            Phase.CHARACTER_SELECT,
            None,
            state,
            order=[pid + 1 for pid in state.current_round_order],
            characters={p.player_id + 1: p.current_character for p in alive},
            marker_owner_player_id=state.marker_owner_id + 1,
            marker_draft_direction=("clockwise" if state.marker_draft_clockwise else "counterclockwise"),
            active_by_card=dict(state.active_by_card),
        )

    def _alive_ids_from_marker_direction(self, state: GameState) -> list[int]:
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
        step = 1 if getattr(state, "marker_draft_clockwise", True) else -1
        ordered = []
        for i in range(self.config.player_count):
            pid = (start + (step * i)) % self.config.player_count
            if pid in alive_ids:
                ordered.append(pid)
        return ordered

    def _run_draft(self, state: GameState) -> None:
        cards = list(CARD_TO_NAMES.keys())
        self.rng.shuffle(cards)
        clockwise = self._alive_ids_from_marker_direction(state)
        reverse = list(reversed(clockwise))
        alive_count = len(clockwise)

        if alive_count == 3:
            removed = cards[0]
            phase1_pool = list(cards[1:5])
            reserve_pool = list(cards[5:8])
            self._log({"event": "draft_hidden_card", "player_count": 3, "hidden_card": removed})

            pool = list(phase1_pool)
            for pid in clockwise:
                pick = self._request_decision("choose_draft_card", state, state.players[pid], list(pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._record_ai_decision(
                    state,
                    state.players[pid],
                    "draft_card",
                    draft_debug,
                    result={"picked_card": pick, "draft_phase": 1},
                    source_event="draft_pick",
                )
                self._log({"event": "draft_pick", "phase": 1, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                self._emit_vis("draft_pick", Phase.DRAFT, pid + 1, state, draft_phase=1, picked_card=pick)
                pool.remove(pick)

            second_pool = list(reserve_pool) + list(pool)
            last_pid = clockwise[-1]
            pick = self._request_decision("choose_draft_card", state, state.players[last_pid], list(second_pool))
            state.players[last_pid].drafted_cards.append(pick)
            draft_debug = self.policy.pop_debug("draft_card", last_pid) if hasattr(self.policy, "pop_debug") else None
            self._record_ai_decision(
                state,
                state.players[last_pid],
                "draft_card",
                draft_debug,
                result={"picked_card": pick, "draft_phase": 2},
                source_event="draft_pick",
            )
            self._log({"event": "draft_pick", "phase": 2, "player": last_pid + 1, "picked_card": pick, "decision": draft_debug})
            self._emit_vis("draft_pick", Phase.DRAFT, last_pid + 1, state, draft_phase=2, picked_card=pick)
            second_pool.remove(pick)

            for pid in reverse[1:]:
                pick = self._request_decision("choose_draft_card", state, state.players[pid], list(second_pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._record_ai_decision(
                    state,
                    state.players[pid],
                    "draft_card",
                    draft_debug,
                    result={"picked_card": pick, "draft_phase": 2},
                    source_event="draft_pick",
                )
                self._log({"event": "draft_pick", "phase": 2, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                self._emit_vis("draft_pick", Phase.DRAFT, pid + 1, state, draft_phase=2, picked_card=pick)
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
                pick = self._request_decision("choose_draft_card", state, state.players[pid], list(pool))
                state.players[pid].drafted_cards.append(pick)
                draft_debug = self.policy.pop_debug("draft_card", pid) if hasattr(self.policy, "pop_debug") else None
                self._record_ai_decision(
                    state,
                    state.players[pid],
                    "draft_card",
                    draft_debug,
                    result={"picked_card": pick, "draft_phase": 1},
                    source_event="draft_pick",
                )
                self._log({"event": "draft_pick", "phase": 1, "player": pid + 1, "picked_card": pick, "decision": draft_debug})
                self._emit_vis("draft_pick", Phase.DRAFT, pid + 1, state, draft_phase=1, picked_card=pick)
                pool.remove(pick)

            pool = list(second_pool)
            self.rng.shuffle(pool)
            for pid, pick in zip(clockwise, pool):
                state.players[pid].drafted_cards.append(pick)
                self._record_ai_decision(
                    state,
                    state.players[pid],
                    "draft_card",
                    None,
                    result={"picked_card": pick, "draft_phase": 2, "random_assigned": True},
                    source_event="draft_pick",
                )
                self._log({"event": "draft_pick", "phase": 2, "player": pid + 1, "picked_card": pick, "decision": None, "random_assigned": True})
                self._emit_vis("draft_pick", Phase.DRAFT, pid + 1, state, draft_phase=2, picked_card=pick, random_assigned=True)

        for p in state.players:
            if not p.alive:
                p.current_character = ""
                self._strategy_stats[p.player_id]["character"] = ""
                self._strategy_stats[p.player_id]["draft_cards"] = []
                continue
            chosen = self._request_decision("choose_final_character", state, p, list(p.drafted_cards))
            final_debug = self.policy.pop_debug("final_character", p.player_id) if hasattr(self.policy, "pop_debug") else None
            self._record_ai_decision(
                state,
                p,
                "final_character",
                final_debug,
                result={"character": chosen},
                source_event="final_character_choice",
            )
            p.current_character = chosen
            self._strategy_stats[p.player_id]["character"] = chosen
            self._strategy_stats[p.player_id]["last_selected_character"] = chosen
            counts = self._strategy_stats[p.player_id].setdefault("character_choice_counts", {})
            counts[chosen] = counts.get(chosen, 0) + 1
            self._strategy_stats[p.player_id]["draft_cards"] = list(p.drafted_cards)
            self._strategy_stats[p.player_id]["character_policy_mode"] = (self.policy.character_mode_for_player(p.player_id) if hasattr(self.policy, "character_mode_for_player") else getattr(self.policy, "character_policy_mode", ""))
            self._log({"event": "final_character_choice", "player": p.player_id + 1, "character": chosen, "decision": final_debug})
            self._emit_vis(
                "final_character_choice",
                Phase.CHARACTER_SELECT,
                p.player_id + 1,
                state,
                character=chosen,
                drafted_cards=list(p.drafted_cards),
            )

    def _take_turn(self, state: GameState, player: PlayerState) -> None:
        start_log = {"event": "turn_start", "player": player.player_id + 1, "character": player.current_character}
        finisher_before = int(getattr(player, "control_finisher_turns", 0) or 0)
        disruption_before = self._leader_disruption_snapshot(state, player)
        if player.skipped_turn:
            player.skipped_turn = False
            self._log({**start_log, "skipped": True})
            self._emit_vis(
                "turn_start",
                Phase.TURN_START,
                player.player_id + 1,
                state,
                character=player.current_character,
                skipped=True,
            )
            self._emit_vis(
                "turn_end_snapshot",
                Phase.TURN_END,
                player.player_id + 1,
                state,
                snapshot=build_turn_end_snapshot(state),
            )
            return
        self._resolve_pending_marks(state, player)
        if not player.alive:
            return
        if self._has_weather(state, "말이 살찌는 계절"):
            player.extra_dice_count_this_turn += 1
        self._apply_character_start(state, player)
        if not player.alive:
            return
        self._emit_vis(
            "turn_start",
            Phase.TURN_START,
            player.player_id + 1,
            state,
            character=player.current_character,
            position=player.position,
        )
        self._emit_vis(
            "trick_window_open",
            Phase.TRICK_WINDOW,
            player.player_id + 1,
            state,
            hand_size=len(player.trick_hand),
            public_tricks=player.public_trick_names(),
            hidden_trick_count=player.hidden_trick_count(),
        )
        self._use_trick_phase(state, player)
        if not player.alive:
            self._emit_vis(
                "trick_window_closed",
                Phase.TRICK_WINDOW,
                player.player_id + 1,
                state,
                public_tricks=player.public_trick_names(),
                hidden_trick_count=player.hidden_trick_count(),
            )
            self._emit_vis(
                "turn_end_snapshot",
                Phase.TURN_END,
                player.player_id + 1,
                state,
                snapshot=build_turn_end_snapshot(state),
            )
            return
        self._emit_vis(
            "trick_window_closed",
            Phase.TRICK_WINDOW,
            player.player_id + 1,
            state,
            public_tricks=player.public_trick_names(),
            hidden_trick_count=player.hidden_trick_count(),
        )
        decision = self._request_decision("choose_movement", state, player)
        movement_debug = self.policy.pop_debug("movement_decision", player.player_id) if hasattr(self.policy, "pop_debug") else None
        self._record_ai_decision(
            state,
            player,
            "movement_decision",
            movement_debug,
            result={
                "use_cards": bool(getattr(decision, "use_cards", False)),
                "card_values": list(getattr(decision, "card_values", ()) or ()),
            },
            source_event="movement_choice",
        )
        move, movement_meta = self._resolve_move(state, player, decision)
        player.rolled_dice_count_this_turn = len(movement_meta.get("dice", []))
        self._emit_vis(
            "dice_roll",
            Phase.MOVEMENT,
            player.player_id + 1,
            state,
            player_id=player.player_id + 1,
            dice=movement_meta.get("dice", []),
            dice_values=movement_meta.get("dice", []),
            used_cards=movement_meta.get("used_cards", []),
            cards_used=movement_meta.get("used_cards", []),
            formula=movement_meta.get("formula", ""),
            move=move,
            total_move=move,
            move_modifier_reason=movement_meta.get("mode", "unknown"),
            runaway_choice=movement_meta.get("runaway_choice"),
            runaway_one_short_pos=movement_meta.get("runaway_one_short_pos"),
            runaway_bonus_target_pos=movement_meta.get("runaway_bonus_target_pos"),
            runaway_bonus_target_kind=movement_meta.get("runaway_bonus_target_kind"),
        )
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
        disruption_after = self._leader_disruption_snapshot(state, player)
        awarded = self._maybe_award_control_finisher_window(state, player, disruption_before, disruption_after)
        if finisher_before > 0 and not awarded:
            player.control_finisher_turns = max(0, finisher_before - 1)
            if player.control_finisher_turns == 0:
                player.control_finisher_reason = ""
        self._emit_vis(
            "turn_end_snapshot",
            Phase.TURN_END,
            player.player_id + 1,
            state,
            snapshot=build_turn_end_snapshot(state),
        )


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
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    source.player_id + 1,
                    state,
                    source_player_id=source.player_id + 1,
                    effect_type=etype,
                    target_player_id=player.player_id + 1,
                    success=True,
                    resolution={"amount": amount, **outcome},
                )
            elif etype == "hunter_pull":
                result = self._apply_forced_landing(state, player, eff["source_pos"])
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    source.player_id + 1,
                    state,
                    source_player_id=source.player_id + 1,
                    effect_type=etype,
                    target_player_id=player.player_id + 1,
                    success=True,
                    resolution=result,
                )
            elif etype == "baksu_transfer":
                self._resolve_baksu_transfer(state, source, player)
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    source.player_id + 1,
                    state,
                    source_player_id=source.player_id + 1,
                    effect_type=etype,
                    target_player_id=player.player_id + 1,
                    success=True,
                    resolution={"type": "baksu_transfer"},
                )
            elif etype == "manshin_remove_burdens":
                self._resolve_manshin_remove_burdens(state, source, player)
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    source.player_id + 1,
                    state,
                    source_player_id=source.player_id + 1,
                    effect_type=etype,
                    target_player_id=player.player_id + 1,
                    success=True,
                    resolution={"type": "manshin_remove_burdens"},
                )
            else:
                remaining.append(eff)
            if not player.alive:
                remaining = []
                break
        player.pending_marks = remaining

    def _apply_character_start(self, state: GameState, player: PlayerState) -> None:
        char = player.current_character
        card_no = self._character_card_no(player)
        is_front_face = self._is_character_front_face(player)

        def _resolve_mark_target() -> tuple[Optional[str], dict | None]:
            requested = self._request_decision("choose_mark_target", state, player, char)
            target, coerced = self._coerce_mark_target_character(state, player, requested)
            mark_debug_local = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            if mark_debug_local is not None and coerced:
                mark_debug_local = dict(mark_debug_local)
                mark_debug_local["coerced_by_engine"] = True
                mark_debug_local["coerced_target_character"] = target
            if coerced:
                self._log(
                    {
                        "event": "mark_target_coerced",
                        "player": player.player_id + 1,
                        "character": char,
                        "requested_target_character": requested,
                        "target_character": target,
                    }
                )
            return target, mark_debug_local
        if self._is_muroe_skill_blocked(state, player):
            self._log({"event": "ability_suppressed", "player": player.player_id + 1, "character": char, "reason": "어사"})
            return
        if is_assassin(char):
            target, mark_debug = _resolve_mark_target()
            target_p = self._find_mark_target_player(state, player, target)
            self._record_ai_decision(state, player, "mark_target", mark_debug, result={"target_character": target}, source_event="character_start")
            if target_p is not None:
                self._record_mark_attempt(player.player_id, "success", state)
                target_p.pending_marks.clear()
                target_p.immune_to_marks_this_round = True
                target_p.skipped_turn = True
                target_p.revealed_this_round = True
                self._strategy_stats[player.player_id]["marked_target_names"].append(target)
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    player.player_id + 1,
                    state,
                    source_player_id=player.player_id + 1,
                    target_player_id=target_p.player_id + 1,
                    target_character=target,
                    success=True,
                    effect_type="assassin_reveal",
                    resolution={"type": "assassin_reveal"},
                )
                self._log({
                    "event": "assassin_reveal",
                    "player": player.player_id + 1,
                    "target_player": target_p.player_id + 1,
                    "target_character": target,
                    "decision": mark_debug,
                })
            else:
                self._record_mark_attempt(player.player_id, "none" if not target else "missing", state)
                self._emit_vis(
                    "mark_target_none" if not target else "mark_target_missing",
                    Phase.MARK,
                    player.player_id + 1,
                    state,
                    source_player_id=player.player_id + 1,
                    actor_name=char,
                    target_character=target,
                    effect_type="assassin_reveal",
                    fallback_applied=False,
                )
                if mark_debug is not None:
                    event_name = "mark_target_none" if not target else "mark_target_missing"
                    row = {"event": event_name, "player": player.player_id + 1, "character": char, "decision": mark_debug}
                    if target:
                        row["target_character"] = target
                    self._log(row)
        elif is_bandit(char):
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(state, player, "mark_target", mark_debug, result={"target_character": target}, source_event="character_start")
            self._queue_mark(state, player.player_id, target, {"type": "bandit_tax"}, decision=mark_debug)
        elif is_chunokkun(char):
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(state, player, "mark_target", mark_debug, result={"target_character": target}, source_event="character_start")
            self._queue_mark(state, player.player_id, target, {"type": "hunter_pull", "source_pos": player.position}, decision=mark_debug)
        elif is_pabalggun(char):
            player.extra_dice_count_this_turn += 1
        elif is_baksu(char):
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(state, player, "mark_target", mark_debug, result={"target_character": target}, source_event="character_start")
            self._queue_mark(state, player.player_id, target, {"type": "baksu_transfer"}, decision=mark_debug)
        elif is_mansin(char):
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(state, player, "mark_target", mark_debug, result={"target_character": target}, source_event="character_start")
            self._queue_mark(state, player.player_id, target, {"type": "manshin_remove_burdens"}, decision=mark_debug)
        elif is_doctrine_character(char):
            self._resolve_doctrine_burden_relief(state, player)
        elif is_builder(char):
            player.free_purchase_this_turn = True

    def _apply_character_start(self, state: GameState, player: PlayerState) -> None:
        """Card-no based character-start ability flow.

        This method intentionally mirrors the original behavior, but avoids
        fragile string-literal branching and aligns updated ability1/ability2 rules.
        """
        char = player.current_character
        card_no = self._character_card_no(player)
        is_front_face = self._is_character_front_face(player)

        def _resolve_mark_target() -> tuple[Optional[str], dict | None]:
            requested = self._request_decision("choose_mark_target", state, player, char)
            target, coerced = self._coerce_mark_target_character(state, player, requested)
            mark_debug_local = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
            if mark_debug_local is not None and coerced:
                mark_debug_local = dict(mark_debug_local)
                mark_debug_local["coerced_by_engine"] = True
                mark_debug_local["coerced_target_character"] = target
            if coerced:
                self._log(
                    {
                        "event": "mark_target_coerced",
                        "player": player.player_id + 1,
                        "character": char,
                        "requested_target_character": requested,
                        "target_character": target,
                    }
                )
            return target, mark_debug_local

        if self._is_muroe_skill_blocked(state, player):
            self._log(
                {
                    "event": "ability_suppressed",
                    "player": player.player_id + 1,
                    "character": char,
                    "reason": "muroe_blocked_by_eosa",
                }
            )
            return

        # Card 2: mark branch (front=assassin, back=bandit)
        if card_no == 2 and is_front_face:
            target, mark_debug = _resolve_mark_target()
            target_p = self._find_mark_target_player(state, player, target)
            self._record_ai_decision(
                state,
                player,
                "mark_target",
                mark_debug,
                result={"target_character": target},
                source_event="character_start",
            )
            if target_p is not None:
                self._record_mark_attempt(player.player_id, "success", state)
                target_p.pending_marks.clear()
                target_p.immune_to_marks_this_round = True
                target_p.skipped_turn = True
                target_p.revealed_this_round = True
                self._strategy_stats[player.player_id]["marked_target_names"].append(target)
                self._emit_vis(
                    "mark_resolved",
                    Phase.MARK,
                    player.player_id + 1,
                    state,
                    source_player_id=player.player_id + 1,
                    target_player_id=target_p.player_id + 1,
                    target_character=target,
                    success=True,
                    effect_type="assassin_reveal",
                    resolution={"type": "assassin_reveal"},
                )
                self._log(
                    {
                        "event": "assassin_reveal",
                        "player": player.player_id + 1,
                        "target_player": target_p.player_id + 1,
                        "target_character": target,
                        "decision": mark_debug,
                    }
                )
            else:
                self._record_mark_attempt(player.player_id, "none" if not target else "missing", state)
                self._emit_vis(
                    "mark_target_none" if not target else "mark_target_missing",
                    Phase.MARK,
                    player.player_id + 1,
                    state,
                    source_player_id=player.player_id + 1,
                    actor_name=char,
                    target_character=target,
                    effect_type="assassin_reveal",
                    fallback_applied=False,
                )
                if mark_debug is not None:
                    event_name = "mark_target_none" if not target else "mark_target_missing"
                    row = {
                        "event": event_name,
                        "player": player.player_id + 1,
                        "character": char,
                        "decision": mark_debug,
                    }
                    if target:
                        row["target_character"] = target
                    self._log(row)
            return

        if card_no == 2 and not is_front_face:
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(
                state,
                player,
                "mark_target",
                mark_debug,
                result={"target_character": target},
                source_event="character_start",
            )
            self._queue_mark(
                state,
                player.player_id,
                target,
                {"type": "bandit_tax"},
                decision=mark_debug,
            )
            return

        # Card 3 front: hunter pull mark queue
        if card_no == 3 and is_front_face:
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(
                state,
                player,
                "mark_target",
                mark_debug,
                result={"target_character": target},
                source_event="character_start",
            )
            self._queue_mark(
                state,
                player.player_id,
                target,
                {"type": "hunter_pull", "source_pos": player.position},
                decision=mark_debug,
            )
            return

        # Card 4 front (courier): mandatory die mode.
        if card_no == 4 and is_front_face:
            dice_mode = "plus_one"
            ability_tier = 1
            if player.shards >= 8:
                ability_tier = 2
                chooser = getattr(self.policy, "choose_pabal_dice_mode", None)
                requested_mode = chooser(state, player) if callable(chooser) else None
                if requested_mode in {"plus_one", "minus_one"}:
                    dice_mode = requested_mode
            if dice_mode == "minus_one":
                player.trick_dice_delta_this_turn -= 1
            else:
                player.extra_dice_count_this_turn += 1
            self._log(
                {
                    "event": "character_ability_applied",
                    "player": player.player_id + 1,
                    "card_no": 4,
                    "ability_tier": ability_tier,
                    "dice_mode": dice_mode,
                    "shards": player.shards,
                }
            )
            return

        # Card 6: mark branch (front=baksu, back=manshin)
        if card_no == 6 and is_front_face:
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(
                state,
                player,
                "mark_target",
                mark_debug,
                result={"target_character": target},
                source_event="character_start",
            )
            self._queue_mark(
                state,
                player.player_id,
                target,
                {"type": "baksu_transfer"},
                decision=mark_debug,
            )
            return

        if card_no == 6 and not is_front_face:
            target, mark_debug = _resolve_mark_target()
            self._record_ai_decision(
                state,
                player,
                "mark_target",
                mark_debug,
                result={"target_character": target},
                source_event="character_start",
            )
            self._queue_mark(
                state,
                player.player_id,
                target,
                {"type": "manshin_remove_burdens"},
                decision=mark_debug,
            )
            return

        # Card 5: doctrine relief is ability2 and requires shards>=8.
        if card_no == 5:
            if player.shards >= 8:
                self._resolve_doctrine_burden_relief(state, player)
            else:
                self._log(
                    {
                        "event": "doctrine_burden_relief_skipped",
                        "player": player.player_id + 1,
                        "character": char,
                        "reason": "insufficient_shards",
                        "required_shards": 8,
                        "shards": player.shards,
                    }
                )
            return

        # Card 8 front (builder): free purchase for this turn.
        if card_no == 8 and is_front_face:
            player.free_purchase_this_turn = True

    def _queue_mark(self, state: GameState, source_pid: int, target_character: Optional[str], payload: dict, decision: dict | None = None) -> None:
        source = state.players[source_pid]
        if not target_character:
            self._record_mark_attempt(source_pid, "none", state)
            self._apply_failed_mark_fallback(state, source, payload)
            self._emit_vis(
                "mark_target_none",
                Phase.MARK,
                source_pid + 1,
                state,
                source_player_id=source_pid + 1,
                actor_name=source.current_character,
                effect_type=payload.get("type"),
                fallback_applied=True,
            )
            if decision is not None:
                self._log({"event": "mark_target_none", "player": source_pid + 1, "decision": decision})
            return
        target_p = self._find_mark_target_player(state, source, target_character)
        if target_p is None:
            self._record_mark_attempt(source_pid, "missing", state)
            self._apply_failed_mark_fallback(state, source, payload)
            self._emit_vis(
                "mark_target_missing",
                Phase.MARK,
                source_pid + 1,
                state,
                source_player_id=source_pid + 1,
                actor_name=source.current_character,
                target_character=target_character,
                effect_type=payload.get("type"),
                fallback_applied=True,
            )
            if decision is not None:
                self._log({"event": "mark_target_missing", "player": source_pid + 1, "target_character": target_character, "decision": decision})
            return
        if target_p.revealed_this_round:
            self._record_mark_attempt(source_pid, "blocked", state)
            self._apply_failed_mark_fallback(state, source, payload)
            self._emit_vis(
                "mark_blocked",
                Phase.MARK,
                source_pid + 1,
                state,
                source_player_id=source_pid + 1,
                target_player_id=target_p.player_id + 1,
                target_character=target_character,
                actor_name=source.current_character,
                reason="revealed_by_assassin",
                effect_type=payload.get("type"),
                fallback_applied=True,
            )
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
        self._emit_vis(
            "mark_queued",
            Phase.MARK,
            source_pid + 1,
            state,
            source_player_id=source_pid + 1,
            target_player_id=target_p.player_id + 1,
            target_character=target_character,
            actor_name=source.current_character,
            effect_type=payload.get("type"),
        )
        if decision is not None:
            self._log({"event": "mark_queued", "source_player": source_pid + 1, "target_player": target_p.player_id + 1, "target_character": target_character, "payload": payload, "decision": decision})

    def _apply_failed_mark_fallback(self, state: GameState, source: PlayerState, payload: dict) -> None:
        mark_type = payload.get("type")
        if mark_type == "baksu_transfer":
            threshold = 5
            actor_name = CARD_TO_NAMES[6][0]
        elif mark_type == "manshin_remove_burdens":
            threshold = 7
            actor_name = CARD_TO_NAMES[6][1]
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

    def _apply_failed_mark_fallback(self, state: GameState, source: PlayerState, payload: dict) -> None:
        mark_type = payload.get("type")
        if mark_type == "baksu_transfer":
            threshold = 6
        elif mark_type == "manshin_remove_burdens":
            threshold = 8
        else:
            return
        actor_name = source.current_character or "unknown"
        if source.shards < threshold:
            self._log(
                {
                    "event": "failed_mark_fallback_none",
                    "player": source.player_id + 1,
                    "character": actor_name,
                    "reason": "insufficient_shards",
                    "shards": source.shards,
                    "threshold": threshold,
                }
            )
            return
        burdens = sorted(
            self._burden_cards(source),
            key=lambda c: (c.burden_cost, c.deck_index),
            reverse=True,
        )
        if not burdens:
            self._log(
                {
                    "event": "failed_mark_fallback_none",
                    "player": source.player_id + 1,
                    "character": actor_name,
                    "reason": "no_burdens",
                    "shards": source.shards,
                    "threshold": threshold,
                }
            )
            return
        card = burdens[0]
        moved = self._remove_trick_from_hand(state, source, card)
        if moved is None:
            self._log(
                {
                    "event": "failed_mark_fallback_none",
                    "player": source.player_id + 1,
                    "character": actor_name,
                    "reason": "remove_failed",
                    "shards": source.shards,
                    "threshold": threshold,
                }
            )
            return
        state.trick_discard_pile.append(moved)
        source.cash += moved.burden_cost
        self._sync_trick_visibility(state, source)
        self._log(
            {
                "event": "failed_mark_fallback",
                "player": source.player_id + 1,
                "character": actor_name,
                "shards": source.shards,
                "threshold": threshold,
                "removed": [moved.name],
                "removed_count": 1,
                "cash_gained": moved.burden_cost,
                **self._public_trick_snapshot(source),
            }
        )

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

    def _ordered_mark_targets(self, state: GameState, source_pid: int) -> list[PlayerState]:
        ordered_pids: list[int] = []
        try:
            order = list(state.current_round_order or [])
            source_idx = order.index(source_pid)
            ordered_pids = [pid for pid in order[source_idx + 1 :]]
        except (ValueError, TypeError):
            ordered_pids = []
        if not ordered_pids:
            return []
        by_pid = {p.player_id: p for p in state.players}
        targets: list[PlayerState] = []
        for pid in ordered_pids:
            target = by_pid.get(pid)
            if target is None:
                continue
            if not target.alive:
                continue
            if not target.current_character:
                continue
            if target.revealed_this_round:
                continue
            targets.append(target)
        return targets

    def _coerce_mark_target_character(
        self,
        state: GameState,
        source: PlayerState,
        requested_target: Optional[str],
    ) -> tuple[Optional[str], bool]:
        public_targets = ordered_public_mark_targets(state, source)
        if not public_targets:
            return None, False
        legal_names = {
            str(target["target_character"])
            for target in public_targets
            if isinstance(target.get("target_character"), str) and target.get("target_character")
        }
        if requested_target and requested_target in legal_names:
            return requested_target, False

        # Public choices may include future priority-card faces that nobody actually drafted.
        # For fallback coercion, preserve the previous "first real future target" safety so
        # engine-side recovery does not turn an invalid/empty choice into a forced miss.
        for target in public_targets:
            card_no = target.get("card_no")
            candidate = target.get("target_character")
            if not isinstance(card_no, int) or not isinstance(candidate, str) or not candidate:
                continue
            holder = self._find_future_mark_target_holder_by_card_no(state, source, card_no)
            if holder is not None:
                return candidate, True
        return None, False

    def _find_future_mark_target_holder_by_card_no(
        self,
        state: GameState,
        source: PlayerState,
        card_no: int,
    ) -> Optional[PlayerState]:
        try:
            source_order_idx = state.current_round_order.index(source.player_id)
            allowed_pids = set(state.current_round_order[source_order_idx + 1 :])
        except ValueError:
            return None
        for player in state.players:
            if player.player_id == source.player_id:
                continue
            if not player.alive or player.player_id not in allowed_pids:
                continue
            if self._character_card_no(player) == card_no:
                return player
        return None

    def _find_mark_target_player(
        self,
        state: GameState,
        source: PlayerState,
        target_character: Optional[str],
    ) -> Optional[PlayerState]:
        if not target_character:
            return None
        for target in ordered_public_mark_targets(state, source):
            candidate = target.get("target_character")
            card_no = target.get("card_no")
            if candidate != target_character or not isinstance(card_no, int):
                continue
            return self._find_future_mark_target_holder_by_card_no(state, source, card_no)
        return None

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
            pick = self._request_decision(
                "choose_specific_trick_reward",
                state,
                source,
                list(choices),
                fallback=lambda: None,
            )
            reward_debug = self.policy.pop_debug("trick_reward", source.player_id) if hasattr(self.policy, "pop_debug") else None
            self._record_ai_decision(
                state,
                source,
                "trick_reward",
                reward_debug,
                result={"picked_card": None if pick is None else pick.name},
                source_event="baksu_transfer_reward",
            )
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
        chosen_pid = self._request_decision("choose_doctrine_relief_target", state, source, candidates)
        relief_debug = self.policy.pop_debug("doctrine_relief", source.player_id) if hasattr(self.policy, "pop_debug") else None
        self._record_ai_decision(
            state,
            source,
            "doctrine_relief",
            relief_debug,
            result={"candidate_ids": [candidate.player_id + 1 for candidate in candidates], "chosen_player_id": None if chosen_pid is None else chosen_pid + 1},
            source_event="character_start",
        )
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
                if not card.is_burden:
                    continue
                accepted = self._request_decision(
                    "choose_burden_exchange_on_supply",
                    state,
                    p,
                    card,
                    fallback=lambda: p.cash >= card.burden_cost,
                )
                burden_debug = self.policy.pop_debug("burden_exchange", p.player_id) if hasattr(self.policy, "pop_debug") else None
                self._record_ai_decision(
                    state,
                    p,
                    "burden_exchange",
                    burden_debug,
                    result={"card_name": card.name, "accepted": bool(accepted and p.cash >= card.burden_cost)},
                    source_event="trick_supply",
                )
                if accepted and p.cash >= card.burden_cost:
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
        self._emit_vis(
            "f_value_change",
            Phase.ECONOMY,
            actor_pid + 1 if actor_pid is not None else None,
            state,
            before=prev,
            delta=applied_delta,
            after=state.f_value,
            reason=reason,
        )
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
        if not self._request_decision(
            "choose_purchase_tile",
            state,
            player,
            idx,
            state.board[idx],
            cost,
            source="adjacent_extra",
            fallback=lambda: True,
        ):
            return None
        player.cash -= cost
        if shard_cost > 0:
            player.shards -= shard_cost
        state.tile_owner[idx] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[idx] = player.turns_taken
        self._emit_vis(
            "tile_purchased",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            player_id=player.player_id + 1,
            tile_index=idx,
            cost=cost,
            purchase_source="adjacent_extra",
        )
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
        return True

    def _use_trick_phase(self, state: GameState, player: PlayerState) -> None:
        if not hasattr(self.policy, "choose_trick_to_use"):
            return

        def choose_and_apply(hand: list[TrickCard], phase: str) -> bool:
            if not hand:
                return False
            card = self._request_decision("choose_trick_to_use", state, player, list(hand), fallback=lambda: None)
            debug = self.policy.pop_debug("trick_use", player.player_id) if hasattr(self.policy, "pop_debug") else None
            self._record_ai_decision(
                state,
                player,
                "trick_use",
                debug,
                result={"chosen_card": None if card is None else card.name, "phase": phase},
                source_event="trick_phase",
            )
            if card is None:
                if debug is not None:
                    self._log({"event": "trick_use_skip", "player": player.player_id + 1, "phase": phase, "decision": debug})
                return False
            resolution = self._apply_trick_card(state, player, card)
            self._discard_trick(state, player, card)
            stats = self._strategy_stats[player.player_id]
            stats["tricks_used"] += 1
            stats["regular_tricks_used"] += 1
            self._log({"event": "trick_used", "player": player.player_id + 1, "phase": phase, "character": player.current_character, "card": {"deck_index": card.deck_index, "name": card.name}, "resolution": resolution, "decision": debug})
            self._emit_vis(
                "trick_used",
                Phase.TRICK_WINDOW,
                player.player_id + 1,
                state,
                phase=phase,
                card_name=card.name,
                card_description=card.description,
                card_deck_index=card.deck_index,
                resolution=resolution,
            )
            return True

        # 규칙 정합성: 잔꾀는 매 턴 1장만 선택/사용한다.
        usable_hand = [c for c in player.trick_hand if self._is_trick_phase_usable(c)]
        choose_and_apply(usable_hand, "regular")

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
        budget = max(0, int(getattr(player, "trick_reroll_budget_this_turn", 0)))
        label = getattr(player, "trick_reroll_label_this_turn", "") or "재굴림"
        while budget > 0:
            new_dice = [self.rng.randint(1, 6) for _ in current]
            new_score = score_for(new_dice)
            if new_score <= current_score and current_score >= 0.5:
                break
            rerolls.append({"card": label, "before": list(current), "after": list(new_dice), "before_score": round(current_score,3), "after_score": round(new_score,3)})
            current = new_dice
            current_score = new_score
            budget -= 1
        return current, rerolls

    def _resolve_move(self, state: GameState, player: PlayerState, decision: MovementDecision) -> tuple[int, dict]:
        char = player.current_character
        # Continuous passive from 탐관오리 selected by someone else.
        extra_passive_die = 0
        for p in state.players:
            if (
                p.alive
                and p.player_id != player.player_id
                and is_tamgwanori(p.current_character)
                and player.attribute in {"관원", "상민"}
            ):
                if self._is_muroe_skill_blocked(state, p):
                    continue
                tribute = p.shards // 2
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
            if is_pabalggun(char) and len(set(dice)) < len(dice):
                dice.append(self.rng.randint(1, 6))
            move = sum(dice)
            mode = "dice"

        dice, rerolls = self._try_anytime_rerolls(state, player, used_cards, dice, mode)
        if mode == "card_plus_die":
            move = sum(used_cards) + sum(dice)
        elif mode == "dice":
            move = sum(dice)


        runaway_choice = None
        runaway_one_short_pos = None
        runaway_bonus_target_pos = None
        runaway_bonus_target_kind = None
        if char == CARD_TO_NAMES[3][1]:
            board_len = len(state.board)
            one_short_pos = (player.position + move) % board_len
            target_pos = (one_short_pos + 1) % board_len
            target_kind = state.board[target_pos]
            if target_kind in {CellKind.F1, CellKind.F2, CellKind.S}:
                choose_bonus = bool(
                    self._request_decision(
                        "choose_runaway_slave_step",
                        state,
                        player,
                        one_short_pos,
                        target_pos,
                        target_kind,
                        fallback=lambda: True,
                    )
                )
                if choose_bonus:
                    move += 1
                    runaway_choice = "take_bonus"
                else:
                    runaway_choice = "stay"
                runaway_one_short_pos = one_short_pos
                runaway_bonus_target_pos = target_pos
                runaway_bonus_target_kind = target_kind.name

        player.extra_dice_count_this_turn = 0
        player.trick_dice_delta_this_turn = 0
        meta = {"used_cards": used_cards, "dice": dice, "formula": "+".join(map(str, used_cards + dice)) if (used_cards or dice) else "0", "mode": mode}
        if runaway_choice is not None:
            meta["runaway_choice"] = runaway_choice
            meta["runaway_one_short_pos"] = runaway_one_short_pos
            meta["runaway_bonus_target_pos"] = runaway_bonus_target_pos
            meta["runaway_bonus_target_kind"] = runaway_bonus_target_kind
        if rerolls:
            meta["rerolls"] = rerolls
        player.trick_reroll_budget_this_turn = 0
        player.trick_reroll_label_this_turn = ""
        return move, meta

    def _apply_obstacle_slowdown(
        self,
        state: GameState,
        player: PlayerState,
        *,
        start_pos: int,
        planned_move: int,
    ) -> tuple[int, dict | None]:
        if planned_move <= 0:
            return planned_move, None
        blockers_by_pos: dict[int, list[int]] = {}
        for op in state.players:
            if not op.alive or op.player_id == player.player_id:
                continue
            if not getattr(op, "trick_obstacle_this_round", False):
                continue
            blockers_by_pos.setdefault(op.position, []).append(op.player_id + 1)
        if not blockers_by_pos:
            return planned_move, None

        board_len = len(state.board)
        remaining_pips = planned_move
        current_pos = start_pos
        effective_move = 0
        hits: list[dict] = []
        while remaining_pips > 0:
            next_pos = (current_pos + 1) % board_len
            owners = blockers_by_pos.get(next_pos)
            step_cost = 2 if owners else 1
            if remaining_pips < step_cost:
                break
            remaining_pips -= step_cost
            current_pos = next_pos
            effective_move += 1
            if owners:
                hits.append({"pos": next_pos, "owners": owners})

        if effective_move == planned_move:
            return planned_move, None
        return effective_move, {
            "planned_move": planned_move,
            "effective_move": effective_move,
            "reduced_by": planned_move - effective_move,
            "hits": hits,
        }

    def _advance_player(self, state: GameState, player: PlayerState, move: int, movement_meta: dict) -> None:
        board_len = len(state.board)
        old_pos = player.position
        old_cash = player.cash
        old_hand = player.hand_coins
        old_shards = player.shards
        old_f = state.f_value
        old_tiles = player.tiles_owned
        old_alive = player.alive
        previous_vis_buffer = self._vis_buffer
        self._vis_buffer = []

        try:
            total_move = move
            encounter_event = None
            obstacle_event = None
            total_move, obstacle_event = self._apply_obstacle_slowdown(
                state,
                player,
                start_pos=old_pos,
                planned_move=total_move,
            )
            if player.trick_encounter_boost_this_turn and total_move > 0:
                seen = False
                cur = old_pos
                for step in range(1, total_move):
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
                    if is_gakju(player.current_character):
                        geo_result = self._apply_geo_bonus(player, lap_events[-1])
                        self._record_ai_decision(
                            state,
                            player,
                            "geo_bonus",
                            None,
                            result=geo_result,
                            source_event="lap_reward",
                        )
                        lap_events.append(geo_result)

                landing_event = self._resolve_landing(state, player)
                buffered_landing_events = list(self._vis_buffer or [])
                self._vis_buffer = []
                self._emit_vis(
                    "landing_resolved",
                    Phase.LANDING,
                    player.player_id + 1,
                    state,
                    position=player.position,
                    landing=landing_event,
                )
                self._vis_buffer.extend(buffered_landing_events)
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
            if obstacle_event is not None:
                log_row["obstacle_slowdown"] = obstacle_event
            if len(chain_segments) > 1:
                log_row["chain_segments"] = chain_segments
            self._log(log_row)
            laps_gained = sum(seg["laps_gained"] for seg in chain_segments)
            path: list[int] = []
            cursor = old_pos
            for seg in chain_segments:
                seg_move = int(seg.get("move", 0) or 0)
                for _ in range(max(0, seg_move)):
                    cursor = (cursor + 1) % board_len
                    path.append(cursor)
            movement_source = movement_meta.get("mode", "unknown")
            pending_vis_events = list(self._vis_buffer or [])
            self._vis_buffer = previous_vis_buffer
            self._emit_vis(
                "player_move",
                Phase.MOVEMENT,
                player.player_id + 1,
                state,
                player_id=player.player_id + 1,
                from_tile=old_pos,
                from_tile_index=old_pos,
                to_tile=player.position,
                to_tile_index=player.position,
                move=total_move,
                crossed_start=laps_gained > 0,
                formula=movement_meta.get("formula", ""),
                path=path,
                movement_source=movement_source,
            )
            if pending_vis_events:
                if self._vis_buffer is None:
                    self._vis_buffer = pending_vis_events
                    self._drain_buffered_vis_events(state)
                else:
                    self._vis_buffer.extend(pending_vis_events)
        except Exception:
            self._vis_buffer = previous_vis_buffer
            raise

    def _apply_geo_bonus(self, player: PlayerState, lap_result: dict) -> dict:
        """Apply geo character bonus by selected lap-reward categories.

        Updated rule alignment: geo gets +1 for each resource category selected.
        """
        cash_bonus = 1 if int(lap_result.get("cash_delta", 0) or 0) > 0 else 0
        shard_bonus = 1 if int(lap_result.get("shards_delta", 0) or 0) > 0 else 0
        coin_bonus = 1 if int(lap_result.get("coins_delta", 0) or 0) > 0 else 0
        if cash_bonus:
            player.cash += cash_bonus
        if shard_bonus:
            player.shards += shard_bonus
        if coin_bonus:
            player.hand_coins += coin_bonus
        return {
            "choice": "geo_multi_bonus",
            "cash_delta": cash_bonus,
            "shards_delta": shard_bonus,
            "coins_delta": coin_bonus,
        }

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
                    p.alive and p.player_id != player.player_id and is_tamgwanori(p.current_character)
                    and player.attribute in {"관원", "상민"}
                ):
                    if self._is_muroe_skill_blocked(state, p):
                        continue
                    tribute = p.shards // 2
                    if tribute > 0:
                        self._pay_or_bankrupt(state, player, tribute, p.player_id)
                    extra_passive_die += 1
        return 2 + player.extra_dice_count_this_turn + extra_passive_die + self._weather_extra_dice(state), extra_passive_die

    def _roll_standard_move(self, state: GameState, player: PlayerState, explicit_dice_count: int | None = None) -> dict:
        if explicit_dice_count is None:
            dice_count, extra_passive_die = self._current_turn_dice_count(state, player, apply_passives=True)
            dice = [self.rng.randint(1, 6) for _ in range(dice_count)]
            if is_pabalggun(player.current_character) and len(set(dice)) < len(dice):
                dice.append(self.rng.randint(1, 6))
            return {"dice": dice, "move": sum(dice), "extra_passive_die": extra_passive_die, "mode": "fortune_turn_dice"}
        dice = [self.rng.randint(1, 6) for _ in range(explicit_dice_count)]
        if self.config.rules.dice.enabled:
            remaining = [v for v in self.config.rules.dice.values if v not in player.used_dice_cards]
            max_cards = min(self.config.rules.dice.max_cards_per_turn, len(remaining), explicit_dice_count)
            chosen_cards: list[int] = []
            if (
                max_cards > 0
                and (is_gakju(player.current_character) or is_pabalggun(player.current_character) or is_builder(player.current_character) or is_matchmaker(player.current_character))
                and explicit_dice_count == 2
            ):
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
        self._emit_vis(
            "landing_resolved",
            Phase.LANDING,
            player.player_id + 1,
            state,
            position=player.position,
            landing=landing,
            trigger=trigger,
            card_name=card_name,
        )
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
        dice_count = max(1, int(getattr(player, "rolled_dice_count_this_turn", 0) or 0))
        dice = [self.rng.randint(1, 6) for _ in range(dice_count)]
        dice, rerolls = self._try_anytime_rerolls(state, player, [], dice, "dice")
        meta = {"mode": "dice_chain", "dice": dice, "formula": "+".join(map(str, dice))}
        if rerolls:
            meta["rerolls"] = rerolls
        return sum(dice), meta
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
        self._emit_vis(
            "fortune_drawn",
            Phase.FORTUNE,
            player.player_id + 1,
            state,
            card_name=card.name,
            deck_index=card.deck_index,
        )
        event = self._apply_fortune_card(state, player, card)
        self._emit_vis(
            "fortune_resolved",
            Phase.FORTUNE,
            player.player_id + 1,
            state,
            card_name=card.name,
            resolution=event,
        )
        state.fortune_discard_pile.append(card)
        return {"type": "FORTUNE", "card": {"deck_index": card.deck_index, "name": card.name, "effect": card.effect}, "resolution": event}

    def _apply_fortune_card_impl(self, state: GameState, player: PlayerState, card: FortuneCard) -> dict:
        name = card.name.strip()
        card_id = fortune_card_id_for_name(name)
        board_len = len(state.board)
        attr = player.attribute
        res: dict = {"name": name}
        if card_id == 30:
            return self._fortune_burden_cleanup(state, [player], multiplier=2, payout=True, name=name)
        if card_id == 31:
            targets = [p for p in state.players if p.alive and p.attribute != "무뢰"]
            return self._fortune_burden_cleanup(state, targets, multiplier=2, payout=True, name=name)
        if card_id == 32:
            return self._fortune_burden_cleanup(state, [player], multiplier=1, payout=False, name=name)
        if card_id == 33:
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
            affected = 0
            for op in state.players:
                if op.alive and op.player_id != player.player_id:
                    op.cash += 4
                    affected += 1
            return {"type": "OTHERS_GAIN", "amount": 4, "affected_players": affected}
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

        if cell in {CellKind.T2, CellKind.T3, CellKind.MALICIOUS} and owns_block and player.trick_zone_chain_this_turn:
            player.trick_zone_chain_this_turn = False
            extra_move, chain_meta = self._roll_standard_dice_only(state, player)
            return {"type": "ZONE_CHAIN", "via_card": "뇌절왕", "tile_kind": cell.name, "block_id": block_id, "extra_move": extra_move, "movement": chain_meta, "landing_treated_as_move": True}

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
        if owner is not None and player.trick_force_sale_landing_this_turn:
            player.trick_force_sale_landing_this_turn = False
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
        default_idx = candidates[0]
        idx = default_idx
        if len(candidates) > 1:
            selected_idx = self._request_decision(
                "choose_trick_tile_target",
                state,
                player,
                "인접 토지 추가 구매",
                list(candidates),
                "adjacent_purchase",
                fallback=lambda: default_idx,
            )
            if selected_idx is None:
                return None
            if selected_idx in candidates:
                idx = selected_idx
        base_cost = state.config.rules.economy.purchase_cost_for(state, idx)
        multiplier = 1 if player.shards >= 8 else 2
        cost = int(base_cost * multiplier)
        if player.cash < cost:
            return None
        if not self._request_decision(
            "choose_purchase_tile",
            state,
            player,
            idx,
            state.board[idx],
            cost,
            source="matchmaker_adjacent",
            fallback=lambda: True,
        ):
            return None
        player.cash -= cost
        state.tile_owner[idx] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[idx] = player.turns_taken
        self._emit_vis(
            "tile_purchased",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            player_id=player.player_id + 1,
            tile_index=idx,
            cost=cost,
            purchase_source="matchmaker_adjacent",
            purchase_multiplier=multiplier,
            base_cost=base_cost,
        )
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
        target = self._request_decision("choose_coin_placement_tile", state, player)
        coin_debug = self.policy.pop_debug("coin_placement", player.player_id) if hasattr(self.policy, "pop_debug") else None
        self._record_ai_decision(
            state,
            player,
            "coin_placement",
            coin_debug,
            result={"target_tile": None if target is None else target + 1},
            source_event="coin_placement",
        )
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
        self._emit_vis(
            "bankruptcy",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            player_state=build_player_public_state(player, state).to_dict(),
        )
        self.events.emit_first_non_none("bankruptcy.resolve", state, player)

    def _apply_marker_management(self, state: GameState, player: PlayerState) -> None:
        self.events.emit_first_non_none("marker.management.apply", state, player)

    def _apply_round_end_marker_management(self, state: GameState) -> None:
        # Rule alignment: doctrine marker transfer happens at round end, not per-turn.
        if not state.current_round_order:
            return
        doctrine_pids = [
            pid
            for pid in state.current_round_order
            if state.players[pid].alive and is_doctrine_character(state.players[pid].current_character)
        ]
        if not doctrine_pids:
            return
        chosen_pid = doctrine_pids[-1]
        chosen = state.players[chosen_pid]
        self._log(
            {
                "event": "round_end_marker_management",
                "round_index": state.rounds_completed + 1,
                "candidates": [pid + 1 for pid in doctrine_pids],
                "chosen_player": chosen.player_id + 1,
                "character": chosen.current_character,
            }
        )
        self._apply_marker_management(state, chosen)

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
            ai_decision_log=list(self._ai_decision_log),
            bankruptcy_events=list(self._bankruptcy_events),
        )
