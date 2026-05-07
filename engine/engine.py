from __future__ import annotations

import base64
import json
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
from state import ActionEnvelope, GameState, PlayerState
from tile_effects import (
    build_purchase_context,
    build_rent_context,
    build_score_token_placement_context,
    consume_purchase_one_shots,
    consume_rent_one_shots,
)
from fortune_cards import FortuneCard
from trick_cards import (
    TRICK_FREE_GIFT_ID,
    TRICK_PREFERENTIAL_PASS_ID,
    TRICK_RELIC_COLLECTOR_ID,
    TrickCard,
    trick_card_id_for_name,
)
from weather_cards import WeatherCard
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
from policy.environment_traits import (
    FORTUNE_BLESSED_DICE_ID,
    FORTUNE_BITTER_ENVY_ID,
    FORTUNE_CURSED_DICE_ID,
    FORTUNE_DONATION_ANGEL_ID,
    FORTUNE_DRUNK_RIDING_ID,
    FORTUNE_GOOD_FOR_OTHERS_ID,
    FORTUNE_HALF_PRICE_SALE_ID,
    FORTUNE_HIGH_PERFORMANCE_BONUS_ID,
    FORTUNE_IRRESISTIBLE_DEAL_ID,
    FORTUNE_LAND_THIEF_ID,
    FORTUNE_LONG_TRIP_ID,
    FORTUNE_METEOR_FALL_ID,
    FORTUNE_MOVE_BACK_2_ID,
    FORTUNE_MOVE_BACK_3_ID,
    FORTUNE_PARTY_ID,
    FORTUNE_PERFORMANCE_BONUS_ID,
    FORTUNE_PIG_DREAM_ID,
    FORTUNE_PIOUS_MARKER_ID,
    FORTUNE_POOR_CONSTRUCTION_ID,
    FORTUNE_REST_STOP_ID,
    FORTUNE_SAFE_MOVE_ID,
    FORTUNE_SHORT_TRIP_ID,
    FORTUNE_SUBSCRIPTION_WIN_ID,
    FORTUNE_SUSPICIOUS_DRINK_ID,
    FORTUNE_TAKEOVER_BACK_2_ID,
    FORTUNE_TAKEOVER_BACK_3_ID,
    FORTUNE_TRAFFIC_VIOLATION_ID,
    FORTUNE_UNBEARABLE_SMILE_ID,
    FORTUNE_VERY_SUSPICIOUS_DRINK_ID,
    FORTUNE_BEAST_HEART_ID,
    FORTUNE_CUT_IN_LINE_ID,
    WEATHER_FATTENED_HORSES_ID,
    WEATHER_FORTUNE_LUCKY_DAY_ID,
    WEATHER_HUNTING_SEASON_ID,
    WEATHER_LOVE_AND_FRIENDSHIP_ID,
    WEATHER_MASS_UPRISING_ID,
    fortune_card_id_for_name,
    has_weather_id,
)
from runtime_modules.event_metadata import runtime_module_for_event
from runtime_modules.modifiers import character_skill_suppression_modifier, seed_character_start_modifiers
from runtime_modules.runner import ModuleRunner
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


@dataclass(frozen=True, slots=True)
class EngineDecisionResume:
    request_id: str
    player_id: int
    request_type: str
    choice_id: str
    choice_payload: dict
    resume_token: str
    frame_id: str
    module_id: str
    module_type: str
    module_cursor: str
    batch_id: str = ""


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
        self._vis_session_id_override: str = ""
        self._emitted_vis_idempotency_keys: set[str] = set()
        self._vis_buffer: list[tuple[str, str, int | None, dict[str, Any]]] | None = None
        self._suppress_hidden_trick_selection: bool = False
        self._deferred_arrival_action_id: str = ""
        self._deferred_rent_payment_action_id: str = ""
        self._deferred_supply_threshold_depth: int = 0
        self._deferred_supply_prev_f: float | None = None
        self.events = EventDispatcher()
        self.events.set_trace_hook(self._trace_semantic_event)
        self.rule_scripts = RuleScriptEngine(self, getattr(config, "rule_scripts_path", None))
        self.effect_handlers = EngineEffectHandlers(self)
        self.effect_handlers.register_default_handlers(self.events)
        if hasattr(self.policy, "register_policy_hook"):
            decision_log_hook = PolicyDecisionLogHook(self)
            self.policy.register_policy_hook("policy.before_decision", decision_log_hook.before_decision)
            self.policy.register_policy_hook("policy.after_decision", decision_log_hook.after_decision)

    def _sync_rng_state_to_state(self, state: GameState) -> None:
        rng_state = self.rng.getstate()
        payload = [int(rng_state[0]), list(rng_state[1]), rng_state[2]]
        state.rng_state_b64 = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode("ascii")
        ).decode("ascii")

    def _restore_rng_state_from_state(self, state: GameState) -> None:
        encoded = str(getattr(state, "rng_state_b64", "") or "")
        if not encoded:
            return
        try:
            payload = json.loads(base64.b64decode(encoded.encode("ascii")).decode("ascii"))
            rng_state = (int(payload[0]), tuple(int(item) for item in payload[1]), payload[2])
            self.rng.setstate(rng_state)
        except Exception as exc:
            raise ValueError("Invalid rng_state_b64 checkpoint payload") from exc

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

    def run(self, initial_state: GameState | None = None) -> GameResult:
        state = self.prepare_run(initial_state=initial_state)
        while True:
            step = self.run_next_transition(state)
            if step["status"] == "completed":
                break
            if step["status"] == "waiting_input":
                for resume in self._auto_resume_waiting_input(state):
                    step = self.run_next_transition(state, decision_resume=resume)
                    if step["status"] == "completed":
                        break
                if step["status"] == "completed":
                    break
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

    def prepare_run(self, initial_state: GameState | None = None) -> GameState:
        self._reset_run_trackers()
        if initial_state is not None:
            self._restore_rng_state_from_state(initial_state)
            self._last_prepared_state = initial_state
            return initial_state
        state = self.create_initial_state(deal_initial_tricks=False)
        self._last_prepared_state = state
        self._emit_vis(
            "session_start",
            Phase.SESSION_START,
            None,
            state,
            player_count=self.config.player_count,
            active_by_card=dict(state.active_by_card),
            players=[build_player_public_state(p, state).to_dict() for p in state.players],
            snapshot=build_turn_end_snapshot(state),
        )
        self._start_new_round(state, initial=True)
        self._sync_rng_state_to_state(state)
        return state

    def _auto_resume_waiting_input(self, state: GameState) -> list[EngineDecisionResume]:
        batch = getattr(state, "runtime_active_prompt_batch", None)
        if batch is not None:
            return self._auto_resume_prompt_batch(state, batch)
        prompt = getattr(state, "runtime_active_prompt", None)
        if prompt is not None:
            choice_id, choice_payload = self._default_prompt_choice(state, prompt.player_id, prompt)
            return [self._decision_resume_from_prompt(prompt, choice_id, choice_payload)]
        raise RuntimeError("engine.run reached waiting_input without an active prompt")

    def _auto_resume_prompt_batch(self, state: GameState, batch: Any) -> list[EngineDecisionResume]:
        resumes: list[EngineDecisionResume] = []
        for player_id in list(getattr(batch, "missing_player_ids", []) or []):
            prompt = batch.prompts_by_player_id[int(player_id)]
            choice_id, choice_payload = self._default_prompt_choice(state, int(player_id), prompt)
            resumes.append(self._decision_resume_from_prompt(prompt, choice_id, choice_payload, batch_id=batch.batch_id))
        if not resumes:
            raise RuntimeError("engine.run reached waiting_input with an already-complete prompt batch")
        return resumes

    def _decision_resume_from_prompt(
        self,
        prompt: Any,
        choice_id: str,
        choice_payload: dict,
        *,
        batch_id: str = "",
    ) -> EngineDecisionResume:
        return EngineDecisionResume(
            request_id=str(prompt.request_id),
            player_id=int(prompt.player_id) + 1,
            request_type=str(prompt.request_type),
            choice_id=choice_id,
            choice_payload=dict(choice_payload),
            resume_token=str(prompt.resume_token),
            frame_id=str(prompt.frame_id),
            module_id=str(prompt.module_id),
            module_type=str(prompt.module_type),
            module_cursor=str(prompt.module_cursor),
            batch_id=batch_id,
        )

    def _default_prompt_choice(self, state: GameState, player_id: int, prompt: Any) -> tuple[str, dict]:
        if str(prompt.request_type) == "burden_exchange":
            choice_id = self._burden_exchange_prompt_choice(state, player_id, prompt)
        else:
            choices = list(getattr(prompt, "legal_choices", []) or [])
            if not choices:
                raise RuntimeError(f"prompt has no legal choices: {prompt.request_type}")
            choice_id = str(choices[0].get("choice_id") or "")
        return choice_id, self._choice_payload_for_prompt(prompt, choice_id)

    def _burden_exchange_prompt_choice(self, state: GameState, player_id: int, prompt: Any) -> str:
        player = state.players[int(player_id)]
        context = dict(getattr(prompt, "public_context", {}) or {})
        deck_index = context.get("card_deck_index")
        card = next(
            (
                hand_card
                for hand_card in list(getattr(player, "trick_hand", []) or [])
                if getattr(hand_card, "deck_index", None) == deck_index
            ),
            None,
        )
        if card is None:
            return "no"
        return "yes" if self._request_decision("choose_burden_exchange_on_supply", state, player, card) else "no"

    @staticmethod
    def _choice_payload_for_prompt(prompt: Any, choice_id: str) -> dict:
        for choice in list(getattr(prompt, "legal_choices", []) or []):
            if str(choice.get("choice_id") or "") == choice_id:
                value = choice.get("value")
                return dict(value) if isinstance(value, dict) else {}
        return {}

    def create_initial_state(self, *, deal_initial_tricks: bool = True) -> GameState:
        state = GameState.create(self.config)
        self._initialize_active_faces(state)
        self.rng.shuffle(state.fortune_draw_pile)
        self.rng.shuffle(state.trick_draw_pile)
        self.rng.shuffle(state.weather_draw_pile)
        if deal_initial_tricks:
            self._deal_initial_tricks(state)
        self._sync_rng_state_to_state(state)
        return state

    def _deal_initial_tricks(self, state: GameState) -> None:
        for p in state.players:
            if not p.alive:
                continue
            self._draw_tricks(state, p, max(0, 5 - len(p.trick_hand)), sync_visibility=False)
        self._log({
            "event": "initial_public_tricks",
            "players": [
                {"player": p.player_id + 1, "public_tricks": p.public_trick_names(), "hidden_trick_count": p.hidden_trick_count()}
                for p in state.players
            ],
        })

    def run_next_transition(self, state: GameState, decision_resume: Any | None = None) -> dict[str, Any]:
        try:
            if getattr(state, "runtime_runner_kind", "module") == "module":
                return ModuleRunner().advance_engine(self, state, decision_resume=decision_resume)
            if state.pending_actions:
                return self._run_next_action_transition(state)
            if state.pending_turn_completion:
                return self._complete_pending_turn_transition(state)
            if not state.current_round_order:
                if self._check_end(state):
                    return {"status": "completed", "reason": "end_rule"}
                initial_round = (
                    state.rounds_completed == 0
                    and state.turn_index == 0
                    and state.current_weather is None
                    and not any(p.turns_taken for p in state.players)
                )
                self._start_new_round(state, initial=initial_round)
                if not state.current_round_order:
                    return {"status": "completed", "reason": "empty_round_order"}
            current_pid = state.current_round_order[state.turn_index % len(state.current_round_order)]
            player = state.players[current_pid]
            if self._materialize_scheduled_actions(state, phase="turn_start", player_id=current_pid):
                return self._run_next_action_transition(state)
            if player.alive:
                player.turns_taken += 1
                self._take_turn(state, player)
                if state.pending_actions or state.pending_turn_completion:
                    return {"status": "committed", "player_id": current_pid + 1, "turn_index": state.turn_index, "pending_actions": len(state.pending_actions)}
                if self._check_end(state):
                    return {"status": "completed", "reason": "end_rule", "player_id": current_pid + 1}
            round_ending = self._is_advancing_past_round_end(state)
            if round_ending:
                self._apply_round_end_marker_management(state)
                self._resolve_marker_flip(state)
            state.turn_index += 1
            if round_ending:
                state.rounds_completed += 1
                self._start_new_round(state, initial=False)
            return {"status": "committed", "player_id": current_pid + 1, "turn_index": state.turn_index}
        finally:
            self._sync_rng_state_to_state(state)

    def _is_advancing_past_round_end(self, state: GameState) -> bool:
        return bool(state.current_round_order) and ((state.turn_index + 1) % len(state.current_round_order) == 0)

    def _advance_turn_cursor_after_completion(self, state: GameState, player_id: int) -> dict[str, Any]:
        round_ending = self._is_advancing_past_round_end(state)
        if round_ending:
            self._apply_round_end_marker_management(state)
            self._resolve_marker_flip(state)
        state.turn_index += 1
        if round_ending:
            state.rounds_completed += 1
            self._start_new_round(state, initial=False)
        return {"status": "committed", "player_id": player_id + 1, "turn_index": state.turn_index}

    def _complete_pending_turn_transition(self, state: GameState) -> dict[str, Any]:
        pending = dict(state.pending_turn_completion)
        state.pending_turn_completion = {}
        player_id = int(pending.get("player_id", 0) or 0)
        player = state.players[player_id]
        disruption_before = dict(pending.get("disruption_before") or {})
        disruption_after = self._leader_disruption_snapshot(state, player)
        finisher_before = int(pending.get("finisher_before", 0) or 0)
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
        if self._check_end(state):
            return {"status": "completed", "reason": "end_rule", "player_id": player_id + 1}
        return self._advance_turn_cursor_after_completion(state, player_id)

    def _reset_run_trackers(self) -> None:
        self._action_log = []
        self._ai_decision_log = []
        self._weather_history = []
        self._bankruptcy_events = []
        self._last_payment_attempt_by_player = {}
        self._player_bankruptcy_info = {}
        self._last_semantic_event_name = None
        self._vis_step = 0
        self._vis_session_id = str(self._vis_session_id_override or uuid.uuid4())
        self._emitted_vis_idempotency_keys = set()
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

    def _effect_character_contract(self, character_name: str | None) -> dict:
        if not character_name:
            return {}
        character = CHARACTERS.get(character_name)
        if character is None:
            return {"effect_character_name": character_name}

        payload = {
            "effect_character_name": character_name,
            "effect_card_no": character.card_no,
        }
        faces = CARD_TO_NAMES.get(character.card_no)
        if faces and character_name in faces:
            payload["effect_character_id"] = f"character.card.{character.card_no}.face.{faces.index(character_name) + 1}"
        return payload

    def _effect_character_name_for_event(
        self,
        event_type: str,
        state: GameState,
        acting_player_id: int | None,
        payload: dict,
    ) -> str | None:
        explicit = payload.get("effect_character_name")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        actor_name = payload.get("actor_name") or payload.get("character")
        if event_type == "ability_suppressed" and isinstance(actor_name, str) and actor_name.strip():
            return actor_name.strip()

        effect_type = str(payload.get("effect_type") or payload.get("type") or "")
        effect_character_by_type = {
            "baksu_transfer": "박수",
            "manshin_remove_burdens": "만신",
        }
        if effect_type in effect_character_by_type:
            return effect_character_by_type[effect_type]

        if event_type == "tile_purchased":
            purchase_source = str(payload.get("purchase_source") or payload.get("source") or "")
            if purchase_source not in {"matchmaker_adjacent", "adjacent_extra"}:
                return None
        elif event_type not in {
            "mark_resolved",
            "mark_queued",
            "mark_target_none",
            "mark_target_missing",
            "mark_blocked",
            "ability_suppressed",
        }:
            return None

        source_player_id = payload.get("source_player_id") or payload.get("player_id") or acting_player_id
        if isinstance(source_player_id, int):
            player_index = source_player_id - 1
            if 0 <= player_index < len(state.players):
                character_name = state.players[player_index].current_character
                if character_name:
                    return character_name

        if isinstance(actor_name, str) and actor_name.strip():
            return actor_name.strip()
        return None

    def _with_effect_character_contract(
        self,
        event_type: str,
        state: GameState,
        acting_player_id: int | None,
        payload: dict,
    ) -> dict:
        if {"effect_character_name", "effect_card_no", "effect_character_id"}.issubset(payload):
            return payload
        character_name = self._effect_character_name_for_event(event_type, state, acting_player_id, payload)
        if character_name is None:
            return payload
        return {**payload, **self._effect_character_contract(character_name)}

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
        payload = self._with_effect_character_contract(event_type, state, acting_player_id, dict(payload))
        if self._vis_buffer is not None:
            self._vis_buffer.append((event_type, public_phase, acting_player_id, dict(payload)))
            return
        runtime_module = dict(payload.get("runtime_module") or {})
        if not runtime_module:
            runtime_module = runtime_module_for_event(
                state,
                event_type,
                str(public_phase),
                acting_player_id,
                payload,
                session_id=self._vis_session_id,
            )
            payload = {
                **payload,
                "runtime_module": runtime_module,
                "idempotency_key": runtime_module["idempotency_key"],
            }
        idempotency_key = str(runtime_module.get("idempotency_key") or payload.get("idempotency_key") or "")
        if idempotency_key:
            if idempotency_key in self._emitted_vis_idempotency_keys:
                return
            self._emitted_vis_idempotency_keys.add(idempotency_key)
        if event_type in {"turn_end_snapshot", "game_end"} and "engine_checkpoint" not in payload:
            self._sync_rng_state_to_state(state)
            payload = {**payload, "engine_checkpoint": state.to_checkpoint_payload()}
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
        if self._suppress_hidden_trick_selection:
            player.hidden_trick_deck_index = None
            return
        chosen = None
        if hasattr(self.policy, "choose_hidden_trick_card"):
            chosen = self._request_decision(
                "choose_hidden_trick_card",
                state,
                player,
                list(player.trick_hand),
                fallback=lambda: self.policy.choose_hidden_trick_card(state, player, list(player.trick_hand)),
            )
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

    def _refresh_hidden_trick_slots(self, state: GameState) -> None:
        for player in state.players:
            if player.alive:
                self._sync_trick_visibility(state, player)

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
        if getattr(state, "runtime_runner_kind", "module") == "module":
            return character_skill_suppression_modifier(state, int(player.player_id)) is not None
        return any(
            other.alive and other.player_id != player.player_id and is_eosa(other.current_character)
            for other in state.players
        )

    def _seed_character_start_modifiers(self, state: GameState) -> None:
        seed_character_start_modifiers(state)

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

    def _next_action_id(self, state: GameState, prefix: str) -> str:
        return f"{prefix}:{state.turn_index}:{len(state.pending_actions)}:{uuid.uuid4().hex[:8]}"

    def _action(
        self,
        state: GameState,
        action_type: str,
        player: PlayerState,
        source: str,
        payload: dict,
        *,
        parent_action_id: str = "",
        idempotency_key: str = "",
    ) -> ActionEnvelope:
        return ActionEnvelope(
            action_id=self._next_action_id(state, action_type),
            type=action_type,
            actor_player_id=player.player_id,
            source=source,
            parent_action_id=parent_action_id,
            idempotency_key=idempotency_key,
            payload=dict(payload),
        )

    def _schedule_action(
        self,
        state: GameState,
        action_type: str,
        actor: PlayerState,
        source: str,
        payload: dict,
        *,
        target_player_id: int,
        phase: str,
        priority: int = 100,
        idempotency_key: str = "",
        parent_action_id: str = "",
    ) -> ActionEnvelope:
        if idempotency_key:
            for existing in [*state.scheduled_actions, *state.pending_actions]:
                if existing.idempotency_key == idempotency_key:
                    return existing
        action = ActionEnvelope(
            action_id=self._next_action_id(state, action_type),
            type=action_type,
            actor_player_id=actor.player_id,
            source=source,
            target_player_id=target_player_id,
            phase=phase,
            priority=priority,
            parent_action_id=parent_action_id,
            idempotency_key=idempotency_key,
            payload=dict(payload),
        )
        state.scheduled_actions.append(action)
        state.scheduled_actions.sort(key=lambda item: (item.phase, item.target_player_id if item.target_player_id is not None else -1, item.priority, item.action_id))
        return action

    def _materialize_scheduled_actions(self, state: GameState, *, phase: str, player_id: int) -> bool:
        matched: list[ActionEnvelope] = []
        remaining: list[ActionEnvelope] = []
        for action in state.scheduled_actions:
            if action.phase == phase and action.target_player_id == player_id:
                matched.append(action)
            else:
                remaining.append(action)
        if not matched:
            return False
        matched.sort(key=lambda item: (item.priority, item.action_id))
        state.scheduled_actions = remaining
        state.enqueue_pending_actions(matched)
        return True

    def _resolve_arrival_action(self, state: GameState, action: ActionEnvelope, *, queue_followups: bool = False) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        previous_deferred_arrival_action_id = self._deferred_arrival_action_id
        self._deferred_arrival_action_id = action.action_id if queue_followups else ""
        try:
            landing = self._queue_unowned_purchase_from_arrival(state, player, action) if queue_followups else None
            if landing is None:
                landing = self._resolve_landing(state, player)
        finally:
            self._deferred_arrival_action_id = previous_deferred_arrival_action_id
        self._emit_vis(
            "landing_resolved",
            Phase.LANDING,
            player.player_id + 1,
            state,
            position=player.position,
            landing=landing,
            trigger=payload.get("trigger"),
            card_name=payload.get("card_name"),
        )
        result = {
            "type": "ARRIVAL",
            "trigger": payload.get("trigger", action.source),
            "card_name": payload.get("card_name", ""),
            "position": player.position,
            "landing": landing,
        }
        if not (isinstance(landing, dict) and (landing.get("type") == "QUEUED_PURCHASE" or landing.get("post_action_queued"))):
            self._record_pending_arrival_and_maybe_log_turn(state, action, landing)
        if queue_followups and isinstance(landing, dict) and landing.get("type") == "ZONE_CHAIN":
            followup = self._action(
                state,
                "apply_move",
                player,
                "zone_chain",
                {
                    "move_value": int(landing.get("extra_move", 0) or 0),
                    "lap_credit": True,
                    "schedule_arrival": True,
                    "emit_move_event": False,
                    "trigger": "zone_chain",
                    "formula": (landing.get("movement") or {}).get("formula", ""),
                    "movement_meta": dict(landing.get("movement") or {}),
                },
            )
            if followup.payload["move_value"] > 0:
                state.enqueue_pending_action(followup, front=True)
                result["followup"] = {"queued_action_id": followup.action_id, "action_type": followup.type}
        return result

    def _run_next_action_transition(self, state: GameState) -> dict[str, Any]:
        action = state.dequeue_pending_action()
        try:
            result = self._execute_action(state, action, queue_followups=True)
        except Exception:
            state.enqueue_pending_action(action, front=True)
            raise
        self._log(
            {
                "event": "action_transition",
                "action_id": action.action_id,
                "action_type": action.type,
                "actor_player_id": action.actor_player_id + 1,
                "source": action.source,
                "result": result,
                "pending_actions": len(state.pending_actions),
            }
        )
        return {
            "status": "committed",
            "action_id": action.action_id,
            "action_type": action.type,
            "player_id": action.actor_player_id + 1,
            "turn_index": state.turn_index,
            "pending_actions": len(state.pending_actions),
        }

    def _start_pending_turn_log(
        self,
        state: GameState,
        player: PlayerState,
        move: int,
        movement_meta: dict,
        *,
        obstacle_event: dict | None = None,
        encounter_event: dict | None = None,
    ) -> None:
        state.pending_action_log = {
            "kind": "turn",
            "actor_player_id": player.player_id,
            "round_index": state.rounds_completed + 1,
            "turn_index_global": state.turn_index + 1,
            "player": player.player_id + 1,
            "character": player.current_character,
            "turn_number_for_player": player.turns_taken,
            "start_pos": player.position,
            "move": move,
            "movement": dict(movement_meta),
            "cash_before": player.cash,
            "hand_coins_before": player.hand_coins,
            "shards_before": player.shards,
            "tiles_before": player.tiles_owned,
            "f_before": state.f_value,
            "alive_before": player.alive,
            "segments": [],
        }
        if obstacle_event is not None:
            state.pending_action_log["obstacle_slowdown"] = dict(obstacle_event)
        if encounter_event is not None:
            state.pending_action_log["encounter_bonus"] = dict(encounter_event)

    def _record_pending_move_segment(self, state: GameState, action: ActionEnvelope, result: dict) -> None:
        log = state.pending_action_log
        if not log or log.get("kind") != "turn" or int(log.get("actor_player_id", -1)) != action.actor_player_id:
            return
        log.setdefault("segments", []).append(
            {
                "start_pos": result.get("start_pos"),
                "end_pos": result.get("end_pos"),
                "move": result.get("move") or 0,
                "laps_gained": result.get("laps_gained", 0),
                "lap_events": list(result.get("lap_events") or []),
                "landing": None,
            }
        )

    def _record_pending_arrival_and_maybe_log_turn(self, state: GameState, action: ActionEnvelope, landing: dict) -> None:
        log = state.pending_action_log
        if not log or log.get("kind") != "turn" or int(log.get("actor_player_id", -1)) != action.actor_player_id:
            return
        segments = log.setdefault("segments", [])
        if segments:
            segments[-1]["landing"] = landing
        if isinstance(landing, dict) and landing.get("type") == "ZONE_CHAIN":
            return
        player = state.players[action.actor_player_id]
        final_segment = segments[-1] if segments else {"lap_events": [], "landing": landing}
        turn_row = {
            "event": "turn",
            "round_index": log.get("round_index"),
            "turn_index_global": log.get("turn_index_global"),
            "player": log.get("player"),
            "character": log.get("character"),
            "turn_number_for_player": log.get("turn_number_for_player"),
            "start_pos": log.get("start_pos"),
            "end_pos": player.position,
            "cell": state.board[player.position].name,
            "move": log.get("move"),
            "movement": dict(log.get("movement") or {}),
            "laps_gained": sum(int(seg.get("laps_gained", 0) or 0) for seg in segments),
            "lap_events": list(final_segment.get("lap_events") or []),
            "landing": final_segment.get("landing"),
            "cash_before": log.get("cash_before"),
            "cash_after": player.cash,
            "hand_coins_before": log.get("hand_coins_before"),
            "hand_coins_after": player.hand_coins,
            "shards_before": log.get("shards_before"),
            "shards_after": player.shards,
            "tiles_before": log.get("tiles_before"),
            "tiles_after": player.tiles_owned,
            "f_before": log.get("f_before"),
            "f_after": state.f_value,
            "alive_before": log.get("alive_before"),
            "alive_after": player.alive,
        }
        if "encounter_bonus" in log:
            turn_row["encounter_bonus"] = log["encounter_bonus"]
        if "obstacle_slowdown" in log:
            turn_row["obstacle_slowdown"] = log["obstacle_slowdown"]
        if len(segments) > 1:
            turn_row["chain_segments"] = segments
        self._log(turn_row)
        state.pending_action_log = {}

    def _apply_move_action(self, state: GameState, action: ActionEnvelope, *, queue_followups: bool = False) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        board_len = len(state.board)
        old_pos = player.position
        move_value = payload.get("move_value")
        direction = int(payload.get("direction", 1) or 1)
        lap_credit = bool(payload.get("lap_credit", False))
        lap_events: list[dict] = []
        path: list[int] = list(payload.get("path") or [])
        laps_crossed = 0
        if move_value is not None:
            move_value = int(move_value)
            raw_target = old_pos + (move_value * direction)
            if lap_credit and direction > 0 and move_value > 0:
                laps_crossed = max(0, raw_target // board_len)
                if not queue_followups:
                    for _ in range(laps_crossed):
                        lap_event = self._apply_lap_reward(state, player)
                        lap_events.append(lap_event)
                        if is_gakju(player.current_character):
                            geo_result = self._apply_geo_bonus(player, lap_event)
                            self._record_ai_decision(
                                state,
                                player,
                                "geo_bonus",
                                None,
                                result=geo_result,
                                source_event="lap_reward",
                            )
                            lap_events.append(geo_result)
            if direction > 0 and not path:
                cursor = old_pos
                for _ in range(max(0, move_value)):
                    cursor = (cursor + 1) % board_len
                    path.append(cursor)
            player.total_steps += max(0, move_value)
            target_pos = raw_target % board_len
        else:
            target_pos = int(payload["target_pos"]) % board_len
        player.position = target_pos
        result = {
            "type": "MOVE_APPLIED",
            "trigger": payload.get("trigger", action.source),
            "card_name": payload.get("card_name", ""),
            "start_pos": old_pos,
            "end_pos": player.position,
            "move": move_value if move_value is not None else payload.get("move"),
            "laps_gained": laps_crossed,
            "lap_events": lap_events,
            "path": path,
            "no_lap_credit": not lap_credit,
        }
        if payload.get("emit_move_event", True):
            move_event_type = str(payload.get("move_event_type") or "action_move")
            self._emit_vis(
                move_event_type,
                Phase.MOVEMENT,
                player.player_id + 1,
                state,
                player_id=player.player_id + 1,
                from_tile=old_pos,
                from_tile_index=old_pos,
                to_tile=player.position,
                to_tile_index=player.position,
                move=result["move"],
                crossed_start=laps_crossed > 0,
                formula=payload.get("formula", ""),
                path=path,
                movement_source=payload.get("trigger", action.source),
            )
        followup_actions: list[ActionEnvelope] = []
        if queue_followups and laps_crossed > 0:
            followup_actions.extend(
                self._action(
                    state,
                    "resolve_lap_reward",
                    player,
                    str(payload.get("trigger", action.source)),
                    {
                        "trigger": payload.get("trigger", action.source),
                        "card_name": payload.get("card_name", ""),
                        "lap_ordinal": index + 1,
                        "laps_crossed": laps_crossed,
                    },
                    parent_action_id=action.action_id,
                )
                for index in range(laps_crossed)
            )
            result["lap_rewards"] = [
                {"queued_action_id": lap_action.action_id, "lap_ordinal": index + 1}
                for index, lap_action in enumerate(followup_actions)
            ]
        if payload.get("schedule_arrival", False):
            arrival_action = self._action(
                state,
                "resolve_arrival",
                player,
                str(payload.get("trigger", action.source)),
                {
                    "trigger": payload.get("trigger", action.source),
                    "card_name": payload.get("card_name", ""),
                },
            )
            if queue_followups:
                followup_actions.append(arrival_action)
                result["arrival"] = {"queued_action_id": arrival_action.action_id}
            else:
                result["arrival"] = self._execute_action(state, arrival_action)
        if followup_actions:
            state.enqueue_pending_actions(followup_actions, front=True)
        self._record_pending_move_segment(state, action, result)
        return result

    def _execute_action(self, state: GameState, action: ActionEnvelope, *, queue_followups: bool = False) -> dict:
        if action.type == "apply_move":
            return self._apply_move_action(state, action, queue_followups=queue_followups)
        if action.type == "resolve_lap_reward":
            return self._resolve_lap_reward_action(state, action)
        if action.type == "resolve_arrival":
            return self._resolve_arrival_action(state, action, queue_followups=queue_followups)
        if action.type == "resolve_mark":
            return self._resolve_mark_action(state, action, queue_followups=queue_followups)
        if action.type == "resolve_fortune_takeover_backward":
            return self._resolve_fortune_takeover_backward_action(state, action)
        if action.type == "resolve_trick_tile_rent_modifier":
            return self._resolve_trick_tile_rent_modifier_action(state, action)
        if action.type == "request_purchase_tile":
            return self._request_purchase_tile_action(state, action)
        if action.type == "resolve_purchase_tile":
            return self._resolve_purchase_tile_action(state, action)
        if action.type == "resolve_score_token_placement":
            return self._resolve_score_token_placement_action(state, action)
        if action.type == "request_score_token_placement":
            return self._request_score_token_placement_action(state, action)
        if action.type == "resolve_unowned_post_purchase":
            return self._resolve_unowned_post_purchase_action(state, action)
        if action.type == "resolve_rent_payment":
            return self._resolve_rent_payment_action(state, action)
        if action.type == "resolve_landing_post_effects":
            return self._resolve_landing_post_effects_action(state, action)
        if action.type == "resolve_fortune_subscription":
            return self._resolve_fortune_subscription_action(state, action)
        if action.type == "resolve_fortune_land_thief":
            return self._resolve_fortune_land_thief_action(state, action)
        if action.type == "resolve_fortune_donation_angel":
            return self._resolve_fortune_donation_angel_action(state, action)
        if action.type == "resolve_fortune_forced_trade":
            return self._resolve_fortune_forced_trade_action(state, action)
        if action.type == "resolve_fortune_pious_marker":
            return self._resolve_fortune_pious_marker_action(state, action)
        if action.type == "resolve_supply_threshold":
            return self._resolve_supply_threshold_action(state, action)
        if action.type == "continue_after_trick_phase":
            return self._continue_after_trick_phase_action(state, action)
        raise ValueError(f"Unsupported action type: {action.type}")

    def _resolve_lap_reward_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        lap_event = self._apply_lap_reward(state, player)
        result = {
            "type": "LAP_REWARD",
            "trigger": action.payload.get("trigger", action.source),
            "card_name": action.payload.get("card_name", ""),
            "lap_ordinal": action.payload.get("lap_ordinal"),
            "laps_crossed": action.payload.get("laps_crossed"),
            "lap_reward": lap_event,
        }
        if is_gakju(player.current_character):
            geo_result = self._apply_geo_bonus(player, lap_event)
            self._record_ai_decision(
                state,
                player,
                "geo_bonus",
                None,
                result=geo_result,
                source_event="lap_reward",
            )
            result["geo_bonus"] = geo_result
        return result

    def _apply_target_move(
        self,
        state: GameState,
        player: PlayerState,
        target_pos: int,
        *,
        trigger: str,
        card_name: str = "",
        schedule_arrival: bool,
        emit_move_event: bool = False,
        move: int | None = None,
        formula: str = "",
    ) -> dict:
        action = self._action(
            state,
            "apply_move",
            player,
            trigger,
            {
                "target_pos": target_pos,
                "lap_credit": False,
                "schedule_arrival": schedule_arrival,
                "emit_move_event": emit_move_event,
                "trigger": trigger,
                "card_name": card_name,
                "move": move,
                "formula": formula,
            },
        )
        return self._execute_action(state, action)

    def _build_standard_move_action(
        self,
        state: GameState,
        player: PlayerState,
        move: int,
        movement_meta: dict,
        *,
        emit_move_event: bool = True,
        move_event_type: str | None = None,
    ) -> ActionEnvelope:
        effective_move, obstacle_event = self._apply_obstacle_slowdown(
            state,
            player,
            start_pos=player.position,
            planned_move=move,
        )
        encounter_event = None
        if player.trick_encounter_boost_this_turn and effective_move > 0:
            cur = player.position
            for step in range(1, effective_move):
                cur = (cur + 1) % len(state.board)
                if any(op.alive and op.player_id != player.player_id and op.position == cur for op in state.players):
                    extra = [self.rng.randint(1, 6), self.rng.randint(1, 6)]
                    effective_move += sum(extra)
                    encounter_event = {"met_at": cur, "step": step, "extra_dice": extra, "extra_move": sum(extra)}
                    break
            player.trick_encounter_boost_this_turn = False
        payload = {
            "move_value": effective_move,
            "lap_credit": True,
            "schedule_arrival": True,
            "emit_move_event": emit_move_event,
            "trigger": movement_meta.get("mode", "standard_move"),
            "formula": movement_meta.get("formula", ""),
            "movement_meta": dict(movement_meta),
            "planned_move": move,
        }
        if move_event_type:
            payload["move_event_type"] = move_event_type
        if obstacle_event is not None:
            payload["obstacle_slowdown"] = obstacle_event
        if encounter_event is not None:
            payload["encounter_bonus"] = encounter_event
        self._start_pending_turn_log(
            state,
            player,
            move,
            movement_meta,
            obstacle_event=obstacle_event,
            encounter_event=encounter_event,
        )
        return self._action(state, "apply_move", player, "standard_move", payload)

    def _enqueue_standard_move_action(
        self,
        state: GameState,
        player: PlayerState,
        move: int,
        movement_meta: dict,
        *,
        emit_move_event: bool = True,
        move_event_type: str | None = None,
    ) -> ActionEnvelope:
        action = self._build_standard_move_action(
            state,
            player,
            move,
            movement_meta,
            emit_move_event=emit_move_event,
            move_event_type=move_event_type,
        )
        state.enqueue_pending_action(action)
        return action

    def _apply_forced_landing(self, state: GameState, player: PlayerState, source_pos: int) -> dict:
        old_pos = player.position
        move_result = self._apply_target_move(
            state,
            player,
            source_pos,
            trigger="forced_move",
            card_name=player.current_character,
            schedule_arrival=True,
        )
        landing = dict(move_result.get("arrival", {}).get("landing", {}))
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

    def _request_purchase_tile_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        pos = int(payload["tile_index"])
        cell = state.board[pos]
        source = str(payload.get("purchase_source") or "action_purchase")
        result = self._request_purchase_tile_decision_for_action(state, player, pos, cell, action, source=source)
        if payload.get("record_landing_result") and result.get("type") != "QUEUED_PURCHASE_RESOLUTION":
            state.pending_action_log["pending_landing_purchase_result"] = dict(result)
        return result

    def _request_purchase_tile_decision_for_action(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        cell: CellKind,
        action: ActionEnvelope,
        *,
        source: str,
    ) -> dict:
        fail = self._purchase_precheck_result(state, player, pos, cell, source=source)
        if fail is not None:
            return fail
        purchase_context = build_purchase_context(state, player, pos, cell, source=source)
        cost = purchase_context.final_cost
        wants_purchase = self._request_decision(
            "choose_purchase_tile",
            state,
            player,
            pos,
            cell,
            cost,
            source=source,
            fallback=lambda: True,
        )
        purchase_debug = self.policy.pop_debug("purchase_decision", player.player_id) if hasattr(self.policy, "pop_debug") else None
        if not wants_purchase:
            result = {
                "type": "PURCHASE_SKIP_POLICY",
                "tile_kind": cell.name,
                "cost": cost,
                "base_cost": purchase_context.base_cost,
                "shard_cost": purchase_context.shard_cost,
                "purchase_context": purchase_context.to_payload(),
                "bankrupt": False,
                "skipped": True,
            }
            self._record_ai_decision(
                state,
                player,
                "purchase_decision",
                purchase_debug,
                result={
                    "tile_index": pos,
                    "purchased": False,
                    "reason": "policy_skip",
                    "cost": cost,
                    "base_cost": purchase_context.base_cost,
                },
                source_event=source,
            )
            return result
        resolve_action = self._action(
            state,
            "resolve_purchase_tile",
            player,
            source,
            {
                "tile_index": pos,
                "purchase_source": source,
                "base_cost": purchase_context.base_cost,
                "final_cost": purchase_context.final_cost,
                "shard_cost": purchase_context.shard_cost,
                "purchase_context": purchase_context.to_payload(),
                "purchase_debug": purchase_debug,
                "record_landing_result": bool(action.payload.get("record_landing_result")),
            },
            parent_action_id=action.action_id,
        )
        state.enqueue_pending_action(resolve_action, front=True)
        return {
            "type": "QUEUED_PURCHASE_RESOLUTION",
            "tile_kind": cell.name,
            "tile_index": pos,
            "cost": cost,
            "base_cost": purchase_context.base_cost,
            "shard_cost": purchase_context.shard_cost,
            "purchase_context": purchase_context.to_payload(),
            "queued_action_id": resolve_action.action_id,
        }

    def _resolve_purchase_tile_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        pos = int(payload["tile_index"])
        cell = state.board[pos]
        source = str(payload.get("purchase_source") or action.source or "action_purchase")
        purchase_context_payload = dict(payload.get("purchase_context") or {})
        result: dict
        if state.tile_owner[pos] is not None:
            result = {
                "type": "PURCHASE_FAIL",
                "tile_kind": cell.name,
                "reason": "already_owned",
                "owner": state.tile_owner[pos] + 1,
                "skipped": True,
            }
        elif state.tile_purchase_blocked_turn_index.get(pos) == state.turn_index:
            result = {"type": "PURCHASE_BLOCKED_THIS_TURN", "tile_kind": cell.name}
        else:
            cost = int(payload.get("final_cost", purchase_context_payload.get("final_cost", 0)))
            shard_cost = int(payload.get("shard_cost", purchase_context_payload.get("shard_cost", 0)))
            if player.cash < cost:
                result = {
                    "type": "PURCHASE_FAIL",
                    "tile_kind": cell.name,
                    "cost": cost,
                    "base_cost": int(payload.get("base_cost", purchase_context_payload.get("base_cost", cost))),
                    "shard_cost": shard_cost,
                    "purchase_context": purchase_context_payload,
                    "bankrupt": False,
                    "skipped": True,
                    "reason": "insufficient_cash_at_resolution",
                }
            else:
                result = self._apply_resolved_purchase(
                    state,
                    player,
                    pos,
                    cell,
                    source=source,
                    base_cost=int(payload.get("base_cost", purchase_context_payload.get("base_cost", cost))),
                    cost=cost,
                    shard_cost=shard_cost,
                    purchase_context_payload=purchase_context_payload,
                    purchase_debug=payload.get("purchase_debug"),
                    place_score_tokens=False,
                )
                if result.get("type") == "PURCHASE" and state.config.rules.token.can_place_on_first_purchase:
                    player.visited_owned_tile_indices.add(pos)
                    placement_action = self._queue_score_token_placement_action(
                        state,
                        player,
                        pos,
                        max_place=state.config.rules.token.place_limit_on_purchase(state, player, pos),
                        source="purchase",
                        parent_action_id=action.action_id,
                        update_pending_purchase_result=bool(payload.get("record_landing_result")),
                    )
                    if placement_action is not None:
                        result["placed"] = {
                            "type": "QUEUED_SCORE_TOKEN_PLACEMENT",
                            "queued_action_id": placement_action.action_id,
                            "target": pos,
                        }
        if payload.get("record_landing_result"):
            state.pending_action_log["pending_landing_purchase_result"] = dict(result)
        return result

    def _queue_score_token_placement_action(
        self,
        state: GameState,
        player: PlayerState,
        target: int,
        *,
        max_place: int | None,
        source: str,
        parent_action_id: str = "",
        update_pending_purchase_result: bool = False,
    ) -> ActionEnvelope | None:
        context = build_score_token_placement_context(state, player, target, max_place=max_place, source=source)
        if not context.can_place:
            return None
        action = self._action(
            state,
            "resolve_score_token_placement",
            player,
            source,
            {
                "target": target,
                "max_place": max_place,
                "source": source,
                "placement_context": context.to_payload(),
                "update_pending_purchase_result": update_pending_purchase_result,
            },
            parent_action_id=parent_action_id,
        )
        state.enqueue_pending_action(action, front=True)
        return action

    def _queue_score_token_placement_request(
        self,
        state: GameState,
        player: PlayerState,
        base_event: dict,
        *,
        source: str,
        parent_action_id: str = "",
        record_arrival_result: bool = False,
    ) -> dict | None:
        if player.hand_coins <= 0:
            return None
        action = self._action(
            state,
            "request_score_token_placement",
            player,
            source,
            {
                "base_event": dict(base_event),
                "source": source,
                "record_arrival_result": record_arrival_result,
            },
            parent_action_id=parent_action_id,
        )
        state.enqueue_pending_action(action, front=True)
        queued = dict(base_event)
        queued["placed"] = {
            "type": "QUEUED_SCORE_TOKEN_PLACEMENT_REQUEST",
            "queued_action_id": action.action_id,
        }
        queued["post_action_queued"] = True
        queued["queued_action_id"] = action.action_id
        return queued

    def _request_score_token_placement_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        source = str(payload.get("source") or action.source or "visit")
        base_event = dict(payload.get("base_event") or {})
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
            result = dict(base_event)
            result["placed"] = None
            if payload.get("record_arrival_result"):
                self._record_pending_arrival_and_maybe_log_turn(state, action, result)
            return result
        placement_action = self._action(
            state,
            "resolve_score_token_placement",
            player,
            source,
            {
                "target": int(target),
                "max_place": None,
                "source": source,
                "base_event": base_event,
                "record_arrival_result": bool(payload.get("record_arrival_result")),
            },
            parent_action_id=action.action_id,
        )
        state.enqueue_pending_action(placement_action, front=True)
        queued = dict(base_event)
        queued["placed"] = {
            "type": "QUEUED_SCORE_TOKEN_PLACEMENT",
            "queued_action_id": placement_action.action_id,
            "target": int(target),
        }
        return queued

    def _resolve_score_token_placement_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        target = int(payload["target"])
        max_place = payload.get("max_place")
        if max_place is not None:
            max_place = int(max_place)
        source = str(payload.get("source") or action.source or "visit")
        placed = self._place_hand_coins_on_tile(state, player, target, max_place=max_place, source=source)
        result = placed if placed is not None else {
            "type": "SCORE_TOKEN_PLACEMENT_SKIP",
            "target": target,
            "source": source,
            "placement_context": build_score_token_placement_context(
                state,
                player,
                target,
                max_place=max_place,
                source=source,
            ).to_payload(),
        }
        if payload.get("update_pending_purchase_result"):
            purchase = dict(state.pending_action_log.get("pending_landing_purchase_result") or {})
            if purchase:
                purchase["placed"] = placed
                state.pending_action_log["pending_landing_purchase_result"] = purchase
        if payload.get("base_event") is not None:
            event = dict(payload.get("base_event") or {})
            event["placed"] = placed
            if payload.get("record_arrival_result"):
                self._record_pending_arrival_and_maybe_log_turn(state, action, event)
            return event
        return result

    def _enqueue_target_move_action(
        self,
        state: GameState,
        player: PlayerState,
        target_pos: int,
        *,
        trigger: str,
        schedule_arrival: bool,
        lap_credit: bool,
        source: str | None = None,
        card_name: str = "",
        move: int | None = None,
        formula: str = "",
        move_event_type: str = "action_move",
    ) -> ActionEnvelope:
        action = self._action(
            state,
            "apply_move",
            player,
            source or trigger,
            {
                "target_pos": target_pos,
                "lap_credit": lap_credit,
                "schedule_arrival": schedule_arrival,
                "emit_move_event": True,
                "move_event_type": move_event_type,
                "trigger": trigger,
                "card_name": card_name,
                "move": move,
                "formula": formula,
            },
        )
        state.enqueue_pending_action(action)
        return action

    def _should_defer_landing_post_effects(self) -> bool:
        return bool(self._deferred_arrival_action_id)

    def _should_defer_rent_payment(self) -> bool:
        return bool(self._deferred_arrival_action_id and not self._deferred_rent_payment_action_id)

    def _queue_rent_payment(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        owner: int,
        *,
        source: str,
    ) -> dict:
        rent_action = self._action(
            state,
            "resolve_rent_payment",
            player,
            source,
            {
                "tile_index": pos,
                "owner": owner,
            },
            parent_action_id=self._deferred_arrival_action_id,
        )
        state.enqueue_pending_action(rent_action, front=True)
        return {
            "type": "QUEUED_RENT_PAYMENT",
            "tile_kind": state.board[pos].name,
            "owner": owner + 1,
            "tile_index": pos,
            "post_action_queued": True,
            "queued_action_id": rent_action.action_id,
        }

    def _queue_landing_post_effects(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        event: dict,
        *,
        source: str,
        require_paid_for_adjacent: bool,
    ) -> dict:
        post_action = self._action(
            state,
            "resolve_landing_post_effects",
            player,
            source,
            {
                "tile_index": pos,
                "base_event": dict(event),
                "require_paid_for_adjacent": bool(require_paid_for_adjacent),
            },
            parent_action_id=self._deferred_arrival_action_id,
        )
        state.enqueue_pending_action(post_action, front=True)
        queued = dict(event)
        queued["post_action_queued"] = True
        queued["queued_action_id"] = post_action.action_id
        return queued

    def _resolve_landing_post_effects_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        pos = int(payload["tile_index"])
        event = dict(payload.get("base_event") or {})
        result = self._resolve_landing_post_effects(
            state,
            player,
            pos,
            event,
            require_paid_for_adjacent=bool(payload.get("require_paid_for_adjacent", False)),
        )
        self._record_pending_arrival_and_maybe_log_turn(state, action, result)
        return result

    def _resolve_rent_payment_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        pos = int(payload["tile_index"])
        owner_value = payload.get("owner", state.tile_owner[pos])
        if owner_value is None:
            return self._apply_weather_same_tile_bonus(
                state,
                player,
                {"type": "RENT_NO_OWNER", "tile_kind": state.board[pos].name},
            )
        owner = int(owner_value)
        previous_deferred_arrival_action_id = self._deferred_arrival_action_id
        previous_deferred_rent_payment_action_id = self._deferred_rent_payment_action_id
        self._deferred_arrival_action_id = action.action_id
        self._deferred_rent_payment_action_id = action.action_id
        try:
            rent_result = self.events.emit_first_non_none("rent.payment.resolve", state, player, pos, owner)
        finally:
            self._deferred_arrival_action_id = previous_deferred_arrival_action_id
            self._deferred_rent_payment_action_id = previous_deferred_rent_payment_action_id
        if rent_result is not None:
            return rent_result
        return self._apply_weather_same_tile_bonus(
            state,
            player,
            {"type": "RENT_FAILSAFE", "tile_kind": state.board[pos].name, "owner": owner + 1},
        )

    def _resolve_landing_post_effects(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        event: dict,
        *,
        require_paid_for_adjacent: bool,
    ) -> dict:
        adjacent_allowed = player.alive and (not require_paid_for_adjacent or bool(event.get("paid")))
        if (
            is_matchmaker(player.current_character)
            and adjacent_allowed
            and event.get("type") != "DISPUTED_BANKRUPTCY"
        ):
            extra = self._matchmaker_buy_adjacent(state, player, pos)
            if extra is not None:
                event.setdefault("adjacent_bought", []).append(extra)
        elif player.trick_one_extra_adjacent_buy_this_turn and adjacent_allowed:
            extra = self._buy_one_adjacent_same_block(state, player, pos)
            if extra is not None:
                event["trick_adjacent_bought"] = extra
            player.trick_one_extra_adjacent_buy_this_turn = False
        co = [p for p in state.players if p.alive and p.player_id != player.player_id and p.position == pos]
        if co:
            if player.trick_same_tile_cash2_this_turn:
                gain = 2 * len(co)
                player.cash += gain
                event["trick_same_tile_cash_gain"] = gain
            if player.trick_same_tile_shard_rake_this_turn:
                total = 0
                details = []
                for op in co:
                    amt = player.shards
                    out = self._pay_or_bankrupt(state, op, amt, player.player_id) if amt > 0 else {"paid": True, "amount": 0}
                    total += amt if out.get("paid") else 0
                    details.append({"player": op.player_id + 1, "amount": amt, "paid": out.get("paid", True)})
                event["trick_same_tile_shard_rake"] = {"total": total, "details": details}
        return self._apply_weather_same_tile_bonus(state, player, event)

    def _queue_unowned_purchase_from_arrival(self, state: GameState, player: PlayerState, action: ActionEnvelope) -> dict | None:
        pos = player.position
        cell = state.board[pos]
        if state.tile_owner[pos] is not None or cell not in (CellKind.T2, CellKind.T3):
            return None
        disputed_payload = None
        if has_weather_id(state.current_weather_effects, WEATHER_MASS_UPRISING_ID):
            disputed_rent = state.config.rules.economy.rent_cost_for(state, pos)
            disputed = self._pay_or_bankrupt(state, player, disputed_rent, None)
            if not player.alive:
                return self._apply_weather_same_tile_bonus(
                    state,
                    player,
                    {"type": "DISPUTED_BANKRUPTCY", "tile_kind": cell.name, "rent": disputed_rent, **disputed},
                )
            disputed_payload = {"rent": disputed_rent, **disputed}
        purchase_action = self._action(
            state,
            "request_purchase_tile",
            player,
            "landing_purchase",
            {
                "tile_index": pos,
                "purchase_source": "landing_purchase",
                "record_landing_result": True,
            },
            parent_action_id=action.action_id,
        )
        post_payload = {"tile_index": pos}
        if disputed_payload is not None:
            post_payload["weather_disputed_rent"] = disputed_payload
        post_action = self._action(
            state,
            "resolve_unowned_post_purchase",
            player,
            "landing_post_purchase",
            post_payload,
            parent_action_id=purchase_action.action_id,
        )
        state.enqueue_pending_actions([purchase_action, post_action], front=True)
        return {
            "type": "QUEUED_PURCHASE",
            "tile_kind": cell.name,
            "tile_index": pos,
            "queued_action_ids": [purchase_action.action_id, post_action.action_id],
            "weather_disputed_rent": disputed_payload,
        }

    def _resolve_unowned_post_purchase_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        pos = int(payload["tile_index"])
        cell = state.board[pos]
        purchase = dict(state.pending_action_log.pop("pending_landing_purchase_result", {}) or {})
        if not purchase:
            purchase = {"type": "PURCHASE" if state.tile_owner[pos] == player.player_id else "PURCHASE_SKIP_POLICY", "tile_kind": cell.name}
        if payload.get("weather_disputed_rent") is not None:
            purchase["weather_disputed_rent"] = dict(payload["weather_disputed_rent"])
        result = self._resolve_landing_post_effects(state, player, pos, purchase, require_paid_for_adjacent=False)
        self._record_pending_arrival_and_maybe_log_turn(state, action, result)
        return result

    def _ensure_strategy_stats(self, state: GameState, player: PlayerState) -> dict:
        if len(self._strategy_stats) <= player.player_id:
            self._strategy_stats = [
                {
                    "purchases": 0, "purchase_t2": 0, "purchase_t3": 0,
                    "rent_paid": 0, "own_tile_visits": 0,
                    "f1_visits": 0, "f2_visits": 0, "s_visits": 0,
                    "s_cash_plus1": 0, "s_cash_plus2": 0, "s_cash_minus1": 0,
                    "malicious_visits": 0, "bankruptcies": 0,
                    "cards_used": 0, "card_turns": 0, "single_card_turns": 0, "pair_card_turns": 0,
                    "lap_cash_choices": 0, "lap_coin_choices": 0, "lap_shard_choices": 0,
                    "coins_gained_own_tile": 0, "coins_placed": 0,
                    "mark_attempts": 0, "mark_successes": 0,
                    "mark_fail_no_target": 0, "mark_fail_missing": 0, "mark_fail_blocked": 0,
                    "character": "", "shards_gained_f": 0, "shards_gained_lap": 0, "shard_income_cash": 0,
                    "draft_cards": [], "marked_target_names": [],
                }
                for _ in range(state.config.player_count)
            ]
        return self._strategy_stats[player.player_id]

    def _purchase_precheck_result(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        cell: CellKind,
        *,
        source: str,
    ) -> dict | None:
        if state.tile_purchase_blocked_turn_index.get(pos) == state.turn_index:
            return {"type": "PURCHASE_BLOCKED_THIS_TURN", "tile_kind": cell.name}
        purchase_context = build_purchase_context(state, player, pos, cell, source=source)
        cost = purchase_context.final_cost
        shard_cost = purchase_context.shard_cost
        if player.cash < cost:
            return {
                "type": "PURCHASE_FAIL",
                "tile_kind": cell.name,
                "cost": cost,
                "base_cost": purchase_context.base_cost,
                "shard_cost": shard_cost,
                "purchase_context": purchase_context.to_payload(),
                "bankrupt": False,
                "skipped": True,
            }
        return None

    def _apply_resolved_purchase(
        self,
        state: GameState,
        player: PlayerState,
        pos: int,
        cell: CellKind,
        *,
        source: str,
        base_cost: int,
        cost: int,
        shard_cost: int,
        purchase_context_payload: dict,
        purchase_debug: Any = None,
        place_score_tokens: bool = True,
    ) -> dict:
        stats = self._ensure_strategy_stats(state, player)
        stats["purchases"] += 1
        if cell == CellKind.T2:
            stats["purchase_t2"] += 1
        elif cell == CellKind.T3:
            stats["purchase_t3"] += 1
        shards_before = player.shards
        player.cash -= cost
        if shard_cost > 0:
            player.shards -= shard_cost
        state.tile_owner[pos] = player.player_id
        player.tiles_owned += 1
        player.first_purchase_turn_by_tile[pos] = player.turns_taken
        consume_purchase_one_shots(player, list(purchase_context_payload.get("one_shot_consumptions") or []))
        placed = None
        if place_score_tokens and state.config.rules.token.can_place_on_first_purchase:
            player.visited_owned_tile_indices.add(pos)
            placed = self._place_hand_coins_on_tile(
                state,
                player,
                pos,
                max_place=state.config.rules.token.place_limit_on_purchase(state, player, pos),
                source="purchase",
            )
        result = {
            "type": "PURCHASE",
            "tile_kind": cell.name,
            "cost": cost,
            "base_cost": base_cost,
            "shard_cost": shard_cost,
            "shards_before": shards_before,
            "shards_after": player.shards,
            "purchase_context": purchase_context_payload,
            "placed": placed,
        }
        self._record_ai_decision(
            state,
            player,
            "purchase_decision",
            purchase_debug,
            result={"tile_index": pos, "purchased": True, "cost": cost, "placed": placed},
            source_event=source,
        )
        self._emit_vis(
            "tile_purchased",
            Phase.ECONOMY,
            player.player_id + 1,
            state,
            player_id=player.player_id + 1,
            tile_index=pos,
            cost=cost,
            purchase_source=source,
            result=result,
        )
        return result

    def _resolve_purchase_tile_decision(self, state: GameState, player: PlayerState, pos: int, cell: CellKind, *, source: str) -> dict:
        fail = self._purchase_precheck_result(state, player, pos, cell, source=source)
        if fail is not None:
            return fail
        purchase_context = build_purchase_context(state, player, pos, cell, source=source)
        cost = purchase_context.final_cost
        shard_cost = purchase_context.shard_cost
        wants_purchase = self._request_decision(
            "choose_purchase_tile",
            state,
            player,
            pos,
            cell,
            cost,
            source=source,
            fallback=lambda: True,
        )
        purchase_debug = self.policy.pop_debug("purchase_decision", player.player_id) if hasattr(self.policy, "pop_debug") else None
        if not wants_purchase:
            self._record_ai_decision(
                state,
                player,
                "purchase_decision",
                purchase_debug,
                result={"tile_index": pos, "purchased": False, "reason": "policy_skip", "cost": cost, "base_cost": purchase_context.base_cost},
                source_event=source,
            )
            return {
                "type": "PURCHASE_SKIP_POLICY",
                "tile_kind": cell.name,
                "cost": cost,
                "base_cost": purchase_context.base_cost,
                "shard_cost": shard_cost,
                "purchase_context": purchase_context.to_payload(),
                "bankrupt": False,
                "skipped": True,
            }
        return self._apply_resolved_purchase(
            state,
            player,
            pos,
            cell,
            source=source,
            base_cost=purchase_context.base_cost,
            cost=cost,
            shard_cost=shard_cost,
            purchase_context_payload=purchase_context.to_payload(),
            purchase_debug=purchase_debug,
        )

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
        return 1 if has_weather_id(state.current_weather_effects, WEATHER_FATTENED_HORSES_ID) else 0

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
        if has_weather_id(state.current_weather_effects, WEATHER_LOVE_AND_FRIENDSHIP_ID) and co:
            gain = 4 * len(co)
            player.cash += gain
            event["weather_same_tile_cash_gain"] = gain
            event["weather_same_tile_with"] = [p.player_id + 1 for p in co]
        return event

    def _prepare_round_start_state(self, state: GameState, initial: bool) -> None:
        state.current_round_order = []
        state.round_setup_replay_base = {}
        state.prompt_sequence = 0
        self._sync_rng_state_to_state(state)
        state.round_setup_replay_base = state.to_checkpoint_payload()
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
        state.runtime_modifier_registry.modifiers = []
        state.current_weather = None
        state.current_weather_effects = set()
        self._suppress_hidden_trick_selection = True
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

    def _reveal_round_weather(self, state: GameState) -> None:
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

    def _run_round_draft_module(self, state: GameState, initial: bool) -> None:
        if initial:
            self._deal_initial_tricks(state)
        self._run_draft(state)
        if getattr(state, "runtime_runner_kind", "module") == "module":
            self._seed_character_start_modifiers(state)
        self._suppress_hidden_trick_selection = False
        self._refresh_hidden_trick_slots(state)

    def _schedule_round_turn_order(self, state: GameState, initial: bool) -> None:
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
        state.round_setup_replay_base = {}

    def _start_new_round(self, state: GameState, initial: bool) -> None:
        self._prepare_round_start_state(state, initial)
        if initial:
            for player in state.players:
                if player.alive:
                    self._apply_start_reward(state, player)
        self._reveal_round_weather(state)
        self._run_round_draft_module(state, initial)
        self._schedule_round_turn_order(state, initial)

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

    def _complete_draft_pick(
        self,
        state: GameState,
        pid: int,
        pool: list[int],
        draft_phase: int,
    ) -> None:
        player = state.players[pid]
        offered_cards = self._draft_offered_cards(pool)
        pick, draft_debug, record_debug = self._choose_draft_pick(state, player, offered_cards)
        self._apply_draft_pick(state, player, pool, pick, draft_phase, draft_debug, record_debug)

    def _new_shuffled_draft_cards(self) -> list[int]:
        cards = list(CARD_TO_NAMES.keys())
        self.rng.shuffle(cards)
        return cards

    @staticmethod
    def _draft_offered_cards(pool: list[int]) -> list[int]:
        return list(pool)

    def _choose_draft_pick(
        self,
        state: GameState,
        player: PlayerState,
        offered_cards: list[int],
    ) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
        if len(offered_cards) == 1:
            pick = offered_cards[0]
            draft_debug = {
                "auto_resolved": True,
                "forced": True,
                "offered_count": 1,
                "offered_cards": list(offered_cards),
            }
            record_debug = None
        else:
            pick = self._request_decision("choose_draft_card", state, player, offered_cards)
            draft_debug = self.policy.pop_debug("draft_card", player.player_id) if hasattr(self.policy, "pop_debug") else None
            record_debug = draft_debug
        return int(pick), draft_debug, record_debug

    def _apply_draft_pick(
        self,
        state: GameState,
        player: PlayerState,
        pool: list[int],
        pick: int,
        draft_phase: int,
        draft_debug: dict[str, Any] | None,
        record_debug: dict[str, Any] | None,
    ) -> None:
        player.drafted_cards.append(pick)
        self._record_ai_decision(
            state,
            player,
            "draft_card",
            record_debug,
            result={"picked_card": pick, "draft_phase": draft_phase},
            source_event="draft_pick",
        )
        self._log({"event": "draft_pick", "phase": draft_phase, "player": player.player_id + 1, "picked_card": pick, "decision": draft_debug})
        self._emit_vis("draft_pick", Phase.DRAFT, player.player_id + 1, state, draft_phase=draft_phase, picked_card=pick)
        pool.remove(pick)

    def _run_draft(self, state: GameState) -> None:
        cards = self._new_shuffled_draft_cards()
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
                self._complete_draft_pick(state, pid, pool, 1)

            second_pool = list(reserve_pool) + list(pool)
            last_pid = clockwise[-1]
            self._complete_draft_pick(state, last_pid, second_pool, 2)

            for pid in reverse[1:]:
                self._complete_draft_pick(state, pid, second_pool, 2)

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
                self._complete_draft_pick(state, pid, pool, 1)

            pool = list(second_pool)
            for pid in reverse:
                self._complete_draft_pick(state, pid, pool, 2)

        for p in state.players:
            self._complete_final_character_choice(state, p)

    def _complete_final_character_choice(self, state: GameState, player: PlayerState) -> None:
        if not player.alive:
            player.current_character = ""
            self._strategy_stats[player.player_id]["character"] = ""
            self._strategy_stats[player.player_id]["draft_cards"] = []
            return
        chosen = self._request_decision("choose_final_character", state, player, list(player.drafted_cards))
        final_debug = self.policy.pop_debug("final_character", player.player_id) if hasattr(self.policy, "pop_debug") else None
        self._record_ai_decision(
            state,
            player,
            "final_character",
            final_debug,
            result={"character": chosen},
            source_event="final_character_choice",
        )
        player.current_character = chosen
        self._strategy_stats[player.player_id]["character"] = chosen
        self._strategy_stats[player.player_id]["last_selected_character"] = chosen
        counts = self._strategy_stats[player.player_id].setdefault("character_choice_counts", {})
        counts[chosen] = counts.get(chosen, 0) + 1
        self._strategy_stats[player.player_id]["draft_cards"] = list(player.drafted_cards)
        self._strategy_stats[player.player_id]["character_policy_mode"] = (self.policy.character_mode_for_player(player.player_id) if hasattr(self.policy, "character_mode_for_player") else getattr(self.policy, "character_policy_mode", ""))
        self._log({"event": "final_character_choice", "player": player.player_id + 1, "character": chosen, "decision": final_debug})
        self._emit_vis(
            "final_character_choice",
            Phase.CHARACTER_SELECT,
            player.player_id + 1,
            state,
            character=chosen,
            drafted_cards=list(player.drafted_cards),
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
        if has_weather_id(state.current_weather_effects, WEATHER_FATTENED_HORSES_ID):
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
        trick_continuation = {
            "finisher_before": finisher_before,
            "disruption_before": dict(disruption_before),
        }
        trick_phase_deferred = self._use_trick_phase(state, player, turn_continuation=trick_continuation)
        if trick_phase_deferred:
            return
        self._finish_turn_after_trick_phase(
            state,
            player,
            finisher_before=finisher_before,
            disruption_before=disruption_before,
        )

    def _finish_turn_after_trick_phase(
        self,
        state: GameState,
        player: PlayerState,
        *,
        finisher_before: int,
        disruption_before: dict,
    ) -> None:
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
        self._enqueue_standard_move_action(
            state,
            player,
            move,
            movement_meta,
            emit_move_event=True,
            move_event_type="player_move",
        )
        state.pending_turn_completion = {
            "player_id": player.player_id,
            "finisher_before": finisher_before,
            "disruption_before": dict(disruption_before),
        }


    def _continue_after_trick_phase_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        if not action.payload.get("hidden_trick_synced"):
            self._sync_trick_visibility(state, player)
            action.payload["hidden_trick_synced"] = True
        self._finish_turn_after_trick_phase(
            state,
            player,
            finisher_before=int(action.payload.get("finisher_before", 0) or 0),
            disruption_before=dict(action.payload.get("disruption_before") or {}),
        )
        return {
            "type": "CONTINUE_AFTER_TRICK_PHASE",
            "player_id": player.player_id + 1,
            "pending_actions": len(state.pending_actions),
            "pending_turn_completion": bool(state.pending_turn_completion),
        }

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
            result = self._resolve_mark_effect(state, player, eff, queue_followups=False)
            if result.get("type") == "UNKNOWN_MARK":
                remaining.append(eff)
            if not player.alive:
                remaining = []
                break
        player.pending_marks = remaining

    def _remove_pending_mark(self, target: PlayerState, mark: dict) -> None:
        index = self._pending_mark_index(target, mark)
        if index is not None:
            del target.pending_marks[index]

    def _pending_mark_index(self, target: PlayerState, mark: dict) -> int | None:
        mark_payload = dict(mark or {})
        mark_idempotency_key = str(mark_payload.get("idempotency_key") or "")
        for index, current in enumerate(list(target.pending_marks)):
            current_payload = dict(current)
            if current_payload == mark_payload:
                return index
            if mark_idempotency_key and str(current_payload.get("idempotency_key") or "") == mark_idempotency_key:
                return index
        return None

    def _resolve_mark_action(self, state: GameState, action: ActionEnvelope, *, queue_followups: bool = False) -> dict:
        target_id = (
            action.target_player_id
            if action.target_player_id is not None
            else action.payload.get("target_player_id", action.actor_player_id)
        )
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return {"type": "MARK_SKIPPED", "reason": "invalid_target", "target_player_id": None}
        if target_id < 0 or target_id >= len(state.players):
            return {"type": "MARK_SKIPPED", "reason": "invalid_target", "target_player_id": target_id + 1}
        target = state.players[int(target_id)]
        mark = dict(action.payload.get("mark") or {})
        pending_mark_index = self._pending_mark_index(target, mark)
        if pending_mark_index is None:
            return {"type": "MARK_SKIPPED", "reason": "mark_not_pending", "target_player_id": target.player_id + 1}
        pending_mark = dict(target.pending_marks[pending_mark_index])
        source_id = pending_mark.get("source_pid", mark.get("source_pid", action.actor_player_id))
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            self._remove_pending_mark(target, pending_mark)
            return {"type": "MARK_SKIPPED", "reason": "invalid_source", "target_player_id": target.player_id + 1}
        if source_id < 0 or source_id >= len(state.players):
            self._remove_pending_mark(target, pending_mark)
            return {"type": "MARK_SKIPPED", "reason": "invalid_source", "target_player_id": target.player_id + 1}
        if not target.alive:
            self._remove_pending_mark(target, pending_mark)
            return {"type": "MARK_SKIPPED", "reason": "target_not_alive", "target_player_id": target.player_id + 1}
        if not state.players[source_id].alive:
            self._remove_pending_mark(target, pending_mark)
            return {"type": "MARK_SKIPPED", "reason": "source_not_alive", "target_player_id": target.player_id + 1}
        if target.immune_to_marks_this_round:
            self._remove_pending_mark(target, pending_mark)
            return {"type": "MARK_SKIPPED", "reason": "immune_to_marks", "target_player_id": target.player_id + 1}
        result = self._resolve_mark_effect(state, target, pending_mark, queue_followups=queue_followups)
        if result.get("type") != "UNKNOWN_MARK":
            self._remove_pending_mark(target, pending_mark)
        return result

    def _resolve_mark_effect(self, state: GameState, player: PlayerState, eff: dict, *, queue_followups: bool = False) -> dict:
        etype = eff.get("type")
        source = state.players[int(eff["source_pid"])]
        if etype == "bandit_tax":
            amount = source.shards
            outcome = self._pay_or_bankrupt(state, player, amount, source.player_id)
            self._strategy_stats[source.player_id]["shard_income_cash"] += amount if outcome.get("paid") else 0
            result = {"type": "bandit_tax", "amount": amount, **outcome}
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
            return result
        if etype == "hunter_pull":
            if queue_followups:
                old_pos = player.position
                move_action = self._action(
                    state,
                    "apply_move",
                    player,
                    "forced_move",
                    {
                        "target_pos": int(eff["source_pos"]),
                        "lap_credit": False,
                        "schedule_arrival": True,
                        "emit_move_event": True,
                        "move_event_type": "action_move",
                        "trigger": "hunter_pull",
                        "card_name": source.current_character,
                    },
                )
                state.enqueue_pending_action(move_action, front=True)
                result = {
                    "type": "hunter_pull",
                    "queued_action_id": move_action.action_id,
                    "start_pos": old_pos,
                    "target_pos": int(eff["source_pos"]),
                    "no_lap_credit": True,
                }
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
                return result
            landing = self._apply_forced_landing(state, player, int(eff["source_pos"]))
            self._emit_vis(
                "mark_resolved",
                Phase.MARK,
                source.player_id + 1,
                state,
                source_player_id=source.player_id + 1,
                effect_type=etype,
                target_player_id=player.player_id + 1,
                success=True,
                resolution=landing,
            )
            return {"type": "hunter_pull", "landing": landing, "no_lap_credit": True}
        if etype == "baksu_transfer":
            resolution = self._resolve_baksu_transfer(state, source, player)
            self._emit_vis(
                "mark_resolved",
                Phase.MARK,
                source.player_id + 1,
                state,
                source_player_id=source.player_id + 1,
                effect_type=etype,
                target_player_id=player.player_id + 1,
                actor_name=source.current_character,
                target_character=player.current_character,
                success=True,
                resolution=resolution,
                summary=resolution.get("summary"),
            )
            return resolution
        if etype == "manshin_remove_burdens":
            resolution = self._resolve_manshin_remove_burdens(state, source, player)
            self._emit_vis(
                "mark_resolved",
                Phase.MARK,
                source.player_id + 1,
                state,
                source_player_id=source.player_id + 1,
                effect_type=etype,
                target_player_id=player.player_id + 1,
                actor_name=source.current_character,
                target_character=player.current_character,
                success=True,
                resolution=resolution,
                summary=resolution.get("summary"),
            )
            return resolution
        return {"type": "UNKNOWN_MARK", "effect_type": etype}

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
            self._emit_vis(
                "ability_suppressed",
                Phase.MARK,
                player.player_id + 1,
                state,
                source_player_id=player.player_id + 1,
                actor_name=char,
                reason="muroe_blocked_by_eosa",
                effect_type="character_skill_suppressed",
                effect_source="character",
                summary=f"{char} 능력 차단 / 어사가 무뢰 인물 능력을 막음",
            )
            self._log(
                {
                    "event": "ability_suppressed",
                    "player": player.player_id + 1,
                    "character": char,
                    "reason": "muroe_blocked_by_eosa",
                }
            )
            return

        if self._module_runtime_uses_target_judicator(state) and self._character_mark_intent(state, player) is not None:
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

    @staticmethod
    def _module_runtime_uses_target_judicator(state: GameState) -> bool:
        if str(getattr(state, "runtime_runner_kind", "") or "").strip() != "module":
            return False
        for frame in list(getattr(state, "runtime_frame_stack", []) or []):
            if getattr(frame, "frame_type", "") != "turn" or getattr(frame, "status", "") not in {"running", "suspended"}:
                continue
            for module in list(getattr(frame, "module_queue", []) or []):
                if (
                    getattr(module, "module_type", "") == "TargetJudicatorModule"
                    and getattr(module, "status", "") in {"queued", "running", "suspended"}
                ):
                    return True
        return False

    def _character_mark_intent(self, state: GameState, player: PlayerState) -> dict | None:
        del state
        card_no = self._character_card_no(player)
        is_front_face = self._is_character_front_face(player)
        if card_no == 2 and is_front_face:
            return {"mode": "immediate", "effect_type": "assassin_reveal", "queued_payload": None}
        if card_no == 2 and not is_front_face:
            return {"mode": "queued", "effect_type": "bandit_tax", "queued_payload": {"type": "bandit_tax"}}
        if card_no == 3 and is_front_face:
            return {
                "mode": "queued",
                "effect_type": "hunter_pull",
                "queued_payload": {"type": "hunter_pull", "source_pos": player.position},
            }
        if card_no == 6 and is_front_face:
            return {"mode": "queued", "effect_type": "baksu_transfer", "queued_payload": {"type": "baksu_transfer"}}
        if card_no == 6 and not is_front_face:
            return {
                "mode": "queued",
                "effect_type": "manshin_remove_burdens",
                "queued_payload": {"type": "manshin_remove_burdens"},
            }
        return None

    def _resolve_character_mark_target_decision(
        self,
        state: GameState,
        player: PlayerState,
    ) -> tuple[Optional[str], dict | None]:
        requested = self._request_decision("choose_mark_target", state, player, player.current_character)
        target, coerced = self._coerce_mark_target_character(state, player, requested)
        mark_debug = self.policy.pop_debug("mark_target", player.player_id) if hasattr(self.policy, "pop_debug") else None
        if mark_debug is not None and coerced:
            mark_debug = dict(mark_debug)
            mark_debug["coerced_by_engine"] = True
            mark_debug["coerced_target_character"] = target
        if coerced:
            self._log(
                {
                    "event": "mark_target_coerced",
                    "player": player.player_id + 1,
                    "character": player.current_character,
                    "requested_target_character": requested,
                    "target_character": target,
                }
            )
        return target, mark_debug

    def _adjudicate_character_mark(self, state: GameState, player: PlayerState) -> dict | None:
        intent = self._character_mark_intent(state, player)
        if intent is None:
            return None
        if self._is_muroe_skill_blocked(state, player):
            return {"mode": "suppressed", "effect_type": intent.get("effect_type")}

        target, mark_debug = self._resolve_character_mark_target_decision(state, player)
        self._record_ai_decision(
            state,
            player,
            "mark_target",
            mark_debug,
            result={"target_character": target},
            source_event="target_judicator",
        )
        if intent["mode"] == "queued":
            self._queue_mark(
                state,
                player.player_id,
                target,
                dict(intent.get("queued_payload") or {}),
                decision=mark_debug,
            )
            return {
                "mode": "queued",
                "effect_type": intent.get("effect_type"),
                "target_character": target,
                "decision": mark_debug,
            }

        target_player = self._find_mark_target_player(state, player, target)
        return {
            "mode": "immediate",
            "effect_type": intent.get("effect_type"),
            "target_character": target,
            "target_player_id": None if target_player is None else int(target_player.player_id),
            "decision": mark_debug,
        }

    def _apply_immediate_marker_transfer(
        self,
        state: GameState,
        player: PlayerState,
        adjudication: dict,
    ) -> None:
        effect_type = str(adjudication.get("effect_type") or "")
        target = adjudication.get("target_character")
        target_character = str(target) if target else None
        decision = adjudication.get("decision") if isinstance(adjudication.get("decision"), dict) else None
        if effect_type != "assassin_reveal":
            return
        target_p = self._find_mark_target_player(state, player, target_character)
        if target_p is not None:
            self._record_mark_attempt(player.player_id, "success", state)
            target_p.pending_marks.clear()
            target_p.immune_to_marks_this_round = True
            target_p.skipped_turn = True
            target_p.revealed_this_round = True
            self._strategy_stats[player.player_id]["marked_target_names"].append(target_character)
            self._emit_vis(
                "mark_resolved",
                Phase.MARK,
                player.player_id + 1,
                state,
                source_player_id=player.player_id + 1,
                target_player_id=target_p.player_id + 1,
                target_character=target_character,
                success=True,
                effect_type="assassin_reveal",
                resolution={"type": "assassin_reveal"},
            )
            self._log(
                {
                    "event": "assassin_reveal",
                    "player": player.player_id + 1,
                    "target_player": target_p.player_id + 1,
                    "target_character": target_character,
                    "decision": decision,
                }
            )
            return

        self._record_mark_attempt(player.player_id, "none" if not target_character else "missing", state)
        self._emit_vis(
            "mark_target_none" if not target_character else "mark_target_missing",
            Phase.MARK,
            player.player_id + 1,
            state,
            source_player_id=player.player_id + 1,
            actor_name=player.current_character,
            target_character=target_character,
            effect_type="assassin_reveal",
            fallback_applied=False,
        )
        if decision is not None:
            event_name = "mark_target_none" if not target_character else "mark_target_missing"
            row = {
                "event": event_name,
                "player": player.player_id + 1,
                "character": player.current_character,
                "decision": decision,
            }
            if target_character:
                row["target_character"] = target_character
            self._log(row)

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
        effect_type = str(payload.get("type", "unknown") or "unknown")
        idempotency_key = self._mark_queue_idempotency_key(state, source_pid, target_p.player_id, effect_type)
        if self._has_equivalent_queued_mark(state, target_p, source_pid, payload, idempotency_key):
            self._log(
                {
                    "event": "mark_queue_duplicate_suppressed",
                    "source_player": source_pid + 1,
                    "target_player": target_p.player_id + 1,
                    "target_character": target_character,
                    "effect_type": effect_type,
                    "idempotency_key": idempotency_key,
                    "decision": decision,
                }
            )
            return
        self._record_mark_attempt(source_pid, "success", state)
        mark = {"source_pid": source_pid, **payload, "idempotency_key": idempotency_key}
        target_p.pending_marks.append(mark)
        self._schedule_action(
            state,
            "resolve_mark",
            source,
            f"mark:{effect_type}",
            {
                "mark": dict(mark),
                "target_player_id": target_p.player_id,
                "target_character": target_character,
            },
            target_player_id=target_p.player_id,
            phase="turn_start",
            priority=10,
            idempotency_key=idempotency_key,
        )
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

    def _mark_queue_idempotency_key(self, state: GameState, source_pid: int, target_pid: int, effect_type: str) -> str:
        return f"mark:{state.rounds_completed + 1}:{state.turn_index + 1}:{source_pid}:{target_pid}:{effect_type}"

    def _has_equivalent_queued_mark(
        self,
        state: GameState,
        target: PlayerState,
        source_pid: int,
        payload: dict,
        idempotency_key: str,
    ) -> bool:
        for mark in target.pending_marks:
            if self._mark_payload_matches(mark, source_pid, payload, idempotency_key):
                return True
        for action in [*state.scheduled_actions, *state.pending_actions]:
            if action.type != "resolve_mark":
                continue
            action_target_id = action.target_player_id
            if action_target_id is None:
                action_target_id = action.payload.get("target_player_id")
            try:
                if int(action_target_id) != target.player_id:
                    continue
            except (TypeError, ValueError):
                continue
            if action.idempotency_key == idempotency_key:
                return True
            if self._mark_payload_matches(dict(action.payload.get("mark") or {}), source_pid, payload, idempotency_key):
                return True
        return False

    def _mark_payload_matches(self, mark: dict, source_pid: int, payload: dict, idempotency_key: str) -> bool:
        if str(mark.get("idempotency_key", "") or "") == idempotency_key:
            return True
        try:
            if int(mark.get("source_pid", -1)) != source_pid:
                return False
        except (TypeError, ValueError):
            return False
        for key, value in payload.items():
            if mark.get(key) != value:
                return False
        return True

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
        if state is not None and 0 <= source_pid < len(state.players):
            stats = self._ensure_strategy_stats(state, state.players[source_pid])
        else:
            stats = self._strategy_stats[source_pid]
        stats["mark_attempts"] = stats.get("mark_attempts", 0) + 1
        if outcome == "success":
            stats["mark_successes"] = stats.get("mark_successes", 0) + 1
            if state is not None and has_weather_id(state.current_weather_effects, WEATHER_HUNTING_SEASON_ID):
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
        fallback_target = self._find_player_by_character(
            state,
            target_character,
            exclude=source.player_id,
            source_pid=source.player_id,
            future_only=True,
        )
        if fallback_target is not None:
            return fallback_target
        return self._find_player_by_character(state, target_character, exclude=source.player_id)

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


    def _draw_tricks(self, state: GameState, player: PlayerState, count: int, *, sync_visibility: bool = True) -> list[TrickCard]:
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
        if sync_visibility:
            self._sync_trick_visibility(state, player)
        return drawn

    def _choose_trick_redraw_card(self, state: GameState, player: PlayerState, hand: list[TrickCard], source: str) -> TrickCard | None:
        if not hand:
            return None
        chosen = self._request_decision(
            "choose_trick_redraw_card",
            state,
            player,
            list(hand),
            source,
            fallback=lambda: None,
        )
        if chosen is None:
            return None
        for card in hand:
            if getattr(card, "deck_index", None) == getattr(chosen, "deck_index", None):
                return card
        return None

    def _choose_dice_card_value(
        self,
        state: GameState,
        player: PlayerState,
        candidates: list[int],
        source: str,
    ) -> int | None:
        legal = sorted({int(value) for value in candidates if isinstance(value, int)})
        if not legal:
            return None
        chosen = self._request_decision(
            "choose_dice_card_value",
            state,
            player,
            list(legal),
            source,
            fallback=lambda: legal[0],
        )
        try:
            selected = int(chosen)
        except Exception:
            return legal[0]
        return selected if selected in legal else legal[0]

    def _recover_dice_cards(
        self,
        state: GameState,
        player: PlayerState,
        count: int,
        source: str,
    ) -> list[int]:
        recovered: list[int] = []
        for _ in range(max(0, count)):
            candidates = sorted(int(value) for value in player.used_dice_cards)
            if not candidates:
                break
            selected = self._choose_dice_card_value(state, player, candidates, source)
            if selected is None or selected not in player.used_dice_cards:
                break
            player.used_dice_cards.discard(selected)
            recovered.append(selected)
        return recovered

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

    def _resolve_supply_burden_exchange(
        self,
        state: GameState,
        player: PlayerState,
        card: TrickCard,
    ) -> dict[str, Any] | None:
        if not getattr(card, "is_burden", False):
            return None
        cost = int(getattr(card, "burden_cost", 0) or 0)
        if getattr(player, "cash", 0) < cost:
            return None
        held = next(
            (
                hand_card
                for hand_card in list(getattr(player, "trick_hand", []))
                if getattr(hand_card, "deck_index", None) == getattr(card, "deck_index", None)
                and getattr(hand_card, "is_burden", False)
            ),
            None,
        )
        if held is None:
            return None
        player.cash -= cost
        self._discard_trick(state, player, held)
        self._draw_tricks(state, player, 1)
        return {"name": getattr(held, "name", ""), "cost": cost}

    def _resolve_baksu_transfer(self, state: GameState, source: PlayerState, target: PlayerState) -> dict:
        burdens = list(self._burden_cards(source))
        if not burdens:
            self._log({"event": "baksu_transfer_none", "player": source.player_id + 1, "target_player": target.player_id + 1})
            return {
                "type": "baksu_transfer",
                "actor_name": source.current_character,
                "source_player_id": source.player_id + 1,
                "target_player_id": target.player_id + 1,
                "burden_count": 0,
                "reward_count": 0,
                "burden_names": [],
                "reward_names": [],
                "summary": f"박수 지목 성공 / P{source.player_id + 1} -> P{target.player_id + 1} / 전달할 짐 없음",
            }
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
        burden_names = [c.name for c in burdens]
        result = {
            "type": "baksu_transfer",
            "actor_name": source.current_character,
            "source_player_id": source.player_id + 1,
            "target_player_id": target.player_id + 1,
            "burden_count": len(burdens),
            "reward_count": len(rewards),
            "burden_names": burden_names,
            "reward_names": rewards,
            "summary": f"박수 지목 성공 / P{source.player_id + 1} -> P{target.player_id + 1} / 짐 {len(burdens)}장 전달 / 잔꾀 {len(rewards)}장 획득",
        }
        self._log({"event": "baksu_transfer", "player": source.player_id + 1, "target_player": target.player_id + 1, "moved": burden_names, "rewarded": rewards, **self._public_trick_snapshot(source), "target_public_tricks": target.public_trick_names(), "target_hidden_trick_count": target.hidden_trick_count()})
        return result

    def _resolve_manshin_remove_burdens(self, state: GameState, source: PlayerState, target: PlayerState) -> dict:
        burdens = list(self._burden_cards(target))
        cost = sum(c.burden_cost for c in burdens)
        for card in burdens:
            self._discard_trick(state, target, card)
        outcome = self._pay_or_bankrupt(state, target, cost, source.player_id) if cost > 0 else {"cost": 0, "paid": True, "bankrupt": False, "receiver": source.player_id + 1}
        self._sync_trick_visibility(state, target)
        removed_names = [c.name for c in burdens]
        paid_amount = outcome.get("amount_paid", outcome.get("paid_amount", outcome.get("cost", cost)))
        result = {
            "type": "manshin_remove_burdens",
            "actor_name": source.current_character,
            "source_player_id": source.player_id + 1,
            "target_player_id": target.player_id + 1,
            "removed_count": len(burdens),
            "removed_names": removed_names,
            "paid_amount": paid_amount,
            "cash_delta": paid_amount,
            "bankrupt": outcome.get("bankrupt", False),
            "summary": f"만신 지목 성공 / P{target.player_id + 1} 짐 {len(burdens)}장 제거 / P{source.player_id + 1} +{paid_amount}냥",
            **outcome,
        }
        self._log({"event": "manshin_burden_clear", "player": source.player_id + 1, "target_player": target.player_id + 1, "removed": removed_names, **outcome, "target_public_tricks": target.public_trick_names(), "target_hidden_trick_count": target.hidden_trick_count()})
        return result

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

    def _begin_supply_threshold_deferral(self) -> None:
        self._deferred_supply_threshold_depth += 1

    def _discard_deferred_supply_thresholds(self) -> None:
        if self._deferred_supply_threshold_depth > 0:
            self._deferred_supply_threshold_depth -= 1
        if self._deferred_supply_threshold_depth == 0:
            self._deferred_supply_prev_f = None

    def _queue_deferred_supply_threshold_actions(
        self,
        state: GameState,
        player: PlayerState,
        *,
        turn_continuation: dict | None = None,
    ) -> bool:
        if self._deferred_supply_threshold_depth <= 0:
            return False
        self._deferred_supply_threshold_depth -= 1
        if self._deferred_supply_threshold_depth > 0:
            return False
        prev_f = self._deferred_supply_prev_f
        self._deferred_supply_prev_f = None
        if prev_f is None:
            return False

        thresholds: list[float] = []
        while prev_f < state.next_supply_f_threshold <= state.f_value:
            threshold = state.next_supply_f_threshold
            state.next_supply_f_threshold += 3
            thresholds.append(threshold)
        if not thresholds:
            return False

        queued: list[ActionEnvelope] = [
            self._action(
                state,
                "resolve_supply_threshold",
                player,
                "trick_supply_threshold",
                {"threshold": threshold},
            )
            for threshold in thresholds
        ]
        if turn_continuation is not None:
            queued.append(
                self._action(
                    state,
                    "continue_after_trick_phase",
                    player,
                    "trick_supply_threshold",
                    dict(turn_continuation),
                )
            )
        state.enqueue_pending_actions(queued, front=True)
        return True

    def _resolve_supply_threshold_action(self, state: GameState, action: ActionEnvelope) -> dict:
        threshold = action.payload.get("threshold")
        self._run_supply(state, int(threshold), action=action)
        return {"type": "SUPPLY_THRESHOLD", "threshold": threshold}

    def _run_supply(self, state: GameState, threshold: int, action: ActionEnvelope | None = None) -> None:
        event = {"event": "trick_supply", "threshold": threshold, "players": []}
        processed_by_player = action.payload.setdefault("processed_burden_deck_indices_by_player", {}) if action is not None else {}
        eligible_by_player = action.payload.setdefault("eligible_burden_deck_indices_by_player", {}) if action is not None else {}
        for p in state.players:
            if not p.alive:
                continue
            processed_deck_indices = set()
            if isinstance(processed_by_player, dict):
                raw_processed = processed_by_player.get(str(p.player_id), processed_by_player.get(p.player_id, []))
                if isinstance(raw_processed, list):
                    processed_deck_indices = {int(item) for item in raw_processed if isinstance(item, int)}
            eligible_deck_indices: set[int] | None = None
            if isinstance(eligible_by_player, dict):
                raw_eligible = eligible_by_player.get(str(p.player_id), eligible_by_player.get(p.player_id))
                if isinstance(raw_eligible, list):
                    eligible_deck_indices = {int(item) for item in raw_eligible if isinstance(item, int)}
                else:
                    eligible_deck_indices = {
                        card.deck_index
                        for card in p.trick_hand
                        if card.is_burden and isinstance(getattr(card, "deck_index", None), int)
                    }
                    eligible_by_player[str(p.player_id)] = sorted(eligible_deck_indices)
            exchanged = []
            for card in list(p.trick_hand):
                if not card.is_burden:
                    continue
                deck_index = getattr(card, "deck_index", None)
                if (
                    isinstance(deck_index, int)
                    and eligible_deck_indices is not None
                    and deck_index not in eligible_deck_indices
                ):
                    continue
                if isinstance(deck_index, int) and deck_index in processed_deck_indices:
                    continue
                accepted = self._request_decision(
                    "choose_burden_exchange_on_supply",
                    state,
                    p,
                    card,
                    fallback=lambda: p.cash >= card.burden_cost,
                )
                if isinstance(deck_index, int) and isinstance(processed_by_player, dict):
                    processed_deck_indices.add(deck_index)
                    processed_by_player[str(p.player_id)] = sorted(processed_deck_indices)
                burden_debug = self.policy.pop_debug("burden_exchange", p.player_id) if hasattr(self.policy, "pop_debug") else None
                self._record_ai_decision(
                    state,
                    p,
                    "burden_exchange",
                    burden_debug,
                    result={"card_name": card.name, "accepted": bool(accepted and p.cash >= card.burden_cost)},
                    source_event="trick_supply",
                )
                if accepted:
                    exchanged_card = self._resolve_supply_burden_exchange(state, p, card)
                    if exchanged_card is not None:
                        exchanged.append(exchanged_card)
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
        if self._deferred_supply_threshold_depth > 0:
            if self._deferred_supply_prev_f is None or prev < self._deferred_supply_prev_f:
                self._deferred_supply_prev_f = prev
            return
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
        if owner_player_id is None:
            return 0
        return build_rent_context(state, payer, pos, owner_player_id, include_waivers=False).final_rent

    def _is_trick_phase_usable(self, card: TrickCard) -> bool:
        return not bool(getattr(card, "is_burden", False))

    def _trick_hand_context(self, player: PlayerState) -> list[dict[str, object]]:
        hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
        return [
            {
                "deck_index": getattr(card, "deck_index", None),
                "name": getattr(card, "name", str(card)),
                "card_description": getattr(card, "description", ""),
                "description": getattr(card, "description", ""),
                "is_hidden": hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index,
                "is_usable": self._is_trick_phase_usable(card),
            }
            for card in player.trick_hand
        ]

    def _use_trick_phase(self, state: GameState, player: PlayerState, *, turn_continuation: dict | None = None) -> bool:
        if not hasattr(self.policy, "choose_trick_to_use"):
            return False

        def choose_and_apply(hand: list[TrickCard], phase: str) -> bool:
            if not hand:
                return False
            pending_actions_before = len(state.pending_actions)
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
                state.runtime_last_trick_sequence_result = {
                    "phase": phase,
                    "selected_trick": None,
                    "resolution": {"type": "SKIPPED"},
                    "deferred_followups": False,
                }
                if debug is not None:
                    self._log({"event": "trick_use_skip", "player": player.player_id + 1, "phase": phase, "decision": debug})
                return False
            self._begin_supply_threshold_deferral()
            try:
                resolution = self._apply_trick_card(state, player, card)
                previous_hidden_selection_suppression = self._suppress_hidden_trick_selection
                self._suppress_hidden_trick_selection = True
                try:
                    self._discard_trick(state, player, card)
                finally:
                    self._suppress_hidden_trick_selection = previous_hidden_selection_suppression
                stats = self._strategy_stats[player.player_id]
                stats["tricks_used"] += 1
                stats["regular_tricks_used"] += 1
                self._log({"event": "trick_used", "player": player.player_id + 1, "phase": phase, "character": player.current_character, "card": {"deck_index": card.deck_index, "name": card.name}, "resolution": resolution, "decision": debug})
                state.runtime_last_trick_sequence_result = {
                    "phase": phase,
                    "selected_trick": card.name,
                    "selected_trick_deck_index": card.deck_index,
                    "resolution": dict(resolution or {}),
                    "deferred_followups": False,
                }
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
                    full_hand=self._trick_hand_context(player),
                    hand_count=len(player.trick_hand),
                    public_tricks=player.public_trick_names(),
                    hidden_trick_count=player.hidden_trick_count(),
                    player_cash=player.cash,
                    player_shards=player.shards,
                    f_value=state.f_value,
                    snapshot=build_turn_end_snapshot(state),
                )
            except Exception:
                self._discard_deferred_supply_thresholds()
                raise
            if self._queue_deferred_supply_threshold_actions(state, player, turn_continuation=turn_continuation):
                if state.runtime_last_trick_sequence_result is not None:
                    state.runtime_last_trick_sequence_result["deferred_followups"] = True
                return True
            try:
                self._sync_trick_visibility(state, player)
            except Exception:
                if turn_continuation is not None:
                    state.enqueue_pending_action(
                        self._action(
                            state,
                            "continue_after_trick_phase",
                            player,
                            "hidden_trick_selection",
                            dict(turn_continuation),
                        ),
                        front=True,
                    )
                raise
            if turn_continuation is not None and len(state.pending_actions) > pending_actions_before:
                continuation_payload = dict(turn_continuation)
                continuation_payload["hidden_trick_synced"] = True
                state.enqueue_pending_action(
                    self._action(
                        state,
                        "continue_after_trick_phase",
                        player,
                        "trick_phase_deferred_action",
                        continuation_payload,
                    )
                )
                if state.runtime_last_trick_sequence_result is not None:
                    state.runtime_last_trick_sequence_result["deferred_followups"] = True
                return True
            return False

        # 규칙 정합성: 잔꾀는 매 턴 1장만 선택/사용한다.
        usable_hand = [c for c in player.trick_hand if self._is_trick_phase_usable(c)]
        return choose_and_apply(usable_hand, "regular")

    def _apply_trick_card(self, state: GameState, player: PlayerState, card: TrickCard) -> dict:
        result = self.events.emit_first_non_none("trick.card.resolve", state, player, card)
        return result if result is not None else {"type": "NOT_YET_IMPLEMENTED", "name": card.name}

    def _enqueue_trick_tile_rent_modifier_action(
        self,
        state: GameState,
        player: PlayerState,
        card_name: str,
        *,
        target_scope: str,
        selection_mode: str,
        modifier_kind: str,
    ) -> dict:
        action = self._action(
            state,
            "resolve_trick_tile_rent_modifier",
            player,
            "trick_tile_rent_modifier",
            {
                "card_name": card_name,
                "target_scope": target_scope,
                "selection_mode": selection_mode,
                "modifier_kind": modifier_kind,
            },
        )
        state.enqueue_pending_action(action)
        return {
            "type": "QUEUED_TRICK_TILE_RENT_MODIFIER",
            "card_name": card_name,
            "modifier_kind": modifier_kind,
            "queued_action_id": action.action_id,
        }

    def _resolve_trick_tile_rent_modifier_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        payload = action.payload
        card_name = str(payload.get("card_name") or action.source)
        target_scope = str(payload.get("target_scope") or "")
        selection_mode = str(payload.get("selection_mode") or "")
        modifier_kind = str(payload.get("modifier_kind") or "")
        if target_scope == "other_owned":
            candidates = [i for i, owner in enumerate(state.tile_owner) if owner is not None and owner != player.player_id]
            fallback = lambda: self._select_other_player_tile(state, player, highest=True)
        elif target_scope == "owned":
            candidates = [i for i, owner in enumerate(state.tile_owner) if owner == player.player_id]
            fallback = lambda: self._select_owned_tile(state, player.player_id, highest=True)
        else:
            return {"type": "NO_EFFECT", "reason": "invalid_target_scope", "card_name": card_name}
        if not candidates:
            return {"type": "NO_EFFECT", "reason": "no_target_tile", "card_name": card_name}
        pos = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            card_name,
            list(candidates),
            selection_mode,
            fallback=fallback,
        )
        if pos is None:
            return {"type": "NO_EFFECT", "reason": "no_target_tile", "card_name": card_name}
        if modifier_kind == "rent_zero":
            state.tile_rent_modifiers_this_turn[pos] = 0
            return {"type": "TILE_RENT_ZERO", "pos": pos, "card_name": card_name}
        if modifier_kind == "rent_double":
            state.tile_rent_modifiers_this_turn[pos] = max(2, state.tile_rent_modifiers_this_turn.get(pos, 1) * 2)
            return {"type": "TILE_RENT_DOUBLE", "pos": pos, "card_name": card_name}
        return {"type": "NO_EFFECT", "reason": "invalid_modifier_kind", "card_name": card_name}

    def _apply_flash_trade(self, state: GameState, player: PlayerState) -> dict:
        others = [p for p in state.players if p.alive and p.player_id != player.player_id and p.trick_hand]
        if not others or not player.trick_hand:
            return {"type": "NO_EFFECT", "reason": "missing_trade_target"}
        def my_value(card: TrickCard) -> int:
            return -10 if card.is_burden else 10 - card.burden_cost
        def their_value(card: TrickCard) -> int:
            card_id = trick_card_id_for_name(card.name)
            return 20 if card.is_burden else 10 + (2 if card_id in {TRICK_FREE_GIFT_ID, TRICK_PREFERENTIAL_PASS_ID, TRICK_RELIC_COLLECTOR_ID} else 0)
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
        # Continuous passive from the opposite face of character slot 1 selected by someone else.
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
        """Immediate movement helper retained for parity tests and extension hooks.

        Runtime turn execution should enqueue `apply_move -> resolve_arrival` instead of calling this directly.
        """
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
                laps_crossed = max(0, (current_start + current_move) // board_len)
                player.total_steps += current_move
                player.position = (current_start + current_move) % board_len

                lap_events: List[dict] = []
                for _ in range(laps_crossed):
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
                    "laps_gained": laps_crossed,
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

    def _apply_start_reward(self, state: GameState, player: PlayerState) -> dict:
        result = self.events.emit_first_non_none("start.reward.resolve", state, player)
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
        move = self._apply_target_move(
            state,
            player,
            target_pos,
            trigger=trigger,
            card_name=card_name,
            schedule_arrival=True,
        )
        return {
            "type": "ARRIVAL",
            "trigger": trigger,
            "card_name": card_name,
            "start_pos": move.get("start_pos"),
            "end_pos": move.get("end_pos"),
            "landing": move.get("arrival", {}).get("landing"),
            "no_lap_credit": True,
        }

    def _enqueue_fortune_target_move(
        self,
        state: GameState,
        player: PlayerState,
        target_pos: int,
        *,
        trigger: str,
        card_name: str,
        schedule_arrival: bool,
        move: int | None = None,
        formula: str = "",
    ) -> dict:
        old_pos = player.position
        action = self._enqueue_target_move_action(
            state,
            player,
            target_pos,
            trigger=trigger,
            schedule_arrival=schedule_arrival,
            lap_credit=False,
            card_name=card_name,
            move=move,
            formula=formula,
        )
        return {
            "type": "QUEUED_ARRIVAL" if schedule_arrival else "QUEUED_MOVE_ONLY",
            "trigger": trigger,
            "card_name": card_name,
            "start_pos": old_pos,
            "target_pos": target_pos % len(state.board),
            "queued_action_id": action.action_id,
            "no_lap_credit": True,
        }

    def _enqueue_fortune_takeover_backward(self, state: GameState, player: PlayerState, steps: int, card_name: str) -> dict:
        target_pos = (player.position - steps) % len(state.board)
        move_action = self._action(
            state,
            "apply_move",
            player,
            "fortune_takeover_backward",
            {
                "target_pos": target_pos,
                "lap_credit": False,
                "schedule_arrival": False,
                "emit_move_event": True,
                "move_event_type": "action_move",
                "trigger": "fortune_takeover_backward",
                "card_name": card_name,
                "move": -steps,
                "formula": f"-{steps}",
            },
        )
        takeover_action = self._action(
            state,
            "resolve_fortune_takeover_backward",
            player,
            "fortune_takeover_backward",
            {
                "card_name": card_name,
                "steps": steps,
            },
        )
        state.enqueue_pending_actions([move_action, takeover_action])
        return {
            "type": "QUEUED_TAKEOVER_BACKWARD",
            "card_name": card_name,
            "steps": steps,
            "start_pos": player.position,
            "target_pos": target_pos,
            "queued_action_ids": [move_action.action_id, takeover_action.action_id],
            "no_lap_credit": True,
        }

    def _enqueue_fortune_subscription(self, state: GameState, player: PlayerState, card_name: str) -> dict:
        action = self._action(
            state,
            "resolve_fortune_subscription",
            player,
            "fortune_subscription",
            {"card_name": card_name},
        )
        state.enqueue_pending_action(action)
        return {"type": "QUEUED_FORTUNE_SUBSCRIPTION", "queued_action_id": action.action_id}

    def _resolve_fortune_subscription_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        name = str(action.payload.get("card_name") or action.source or "fortune_subscription")
        result = self._resolve_fortune_subscription(state, player, name)
        self._emit_fortune_action_result(state, player, name, result)
        return result

    def _resolve_fortune_subscription(self, state: GameState, player: PlayerState, name: str) -> dict:
        pos = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._empty_block_tile_candidates(state)),
            "empty_block_purchase",
            fallback=lambda: self._select_empty_block_tile(state),
        )
        if pos is None:
            return {"type": "NO_EFFECT", "reason": "no_empty_block"}
        purchase_action = self._action(
            state,
            "request_purchase_tile",
            player,
            "fortune_subscription",
            {
                "tile_index": pos,
                "purchase_source": "fortune_subscription",
            },
        )
        state.enqueue_pending_action(purchase_action)
        return {
            "type": "QUEUED_SUBSCRIPTION_PURCHASE",
            "selection": pos,
            "queued_action_id": purchase_action.action_id,
        }

    def _enqueue_fortune_decision_action(self, state: GameState, player: PlayerState, action_type: str, card_name: str, result_type: str) -> dict:
        action = self._action(
            state,
            action_type,
            player,
            action_type.removeprefix("resolve_"),
            {"card_name": card_name},
        )
        state.enqueue_pending_action(action)
        return {"type": result_type, "queued_action_id": action.action_id}

    def _emit_fortune_action_result(self, state: GameState, player: PlayerState, card_name: str, result: dict) -> None:
        self._emit_vis(
            "fortune_resolved",
            Phase.FORTUNE,
            player.player_id + 1,
            state,
            card_name=card_name,
            resolution=result,
            summary=self._fortune_action_summary(card_name, player, result),
            action_result=True,
        )

    def _fortune_action_summary(self, card_name: str, player: PlayerState, result: dict) -> str:
        result_type = str(result.get("type") or "")
        transfer = result.get("transfer") if isinstance(result.get("transfer"), dict) else {}
        pos = transfer.get("pos", result.get("pos"))
        tile_text = f"{int(pos) + 1}번 칸" if isinstance(pos, int) else "선택한 칸"
        from_player = transfer.get("from")
        to_player = transfer.get("to")

        if result_type == "STEAL_TILE":
            return f"{card_name}: P{to_player}이 P{from_player}의 {tile_text}을 가져감"
        if result_type in {"MUROE_GIVE_TILE", "GIVE_TILE"}:
            return f"{card_name}: P{from_player}이 P{to_player}에게 {tile_text}을 넘김"
        if result_type == "SUBSCRIPTION":
            selection = result.get("selection")
            selected_tile = f"{int(selection) + 1}번 칸" if isinstance(selection, int) else tile_text
            return f"{card_name}: P{player.player_id + 1}이 {selected_tile}을 구매함"
        if result_type == "QUEUED_SUBSCRIPTION_PURCHASE":
            selection = result.get("selection")
            selected_tile = f"{int(selection) + 1}번 칸" if isinstance(selection, int) else tile_text
            return f"{card_name}: P{player.player_id + 1}이 {selected_tile} 구매를 선택함"
        if result_type == "FORCED_TRADE":
            own = result.get("own_to_other") if isinstance(result.get("own_to_other"), dict) else {}
            other = result.get("other_to_self") if isinstance(result.get("other_to_self"), dict) else {}
            own_pos = own.get("pos")
            other_pos = other.get("pos")
            own_tile = f"{int(own_pos) + 1}번 칸" if isinstance(own_pos, int) else "내 칸"
            other_tile = f"{int(other_pos) + 1}번 칸" if isinstance(other_pos, int) else "상대 칸"
            return f"{card_name}: {own_tile}과 {other_tile}을 교환함"
        if result_type == "PIOUS_MARKER_GAIN_TILE":
            return f"{card_name}: {tile_text}을 획득함"
        if result_type == "NO_EFFECT":
            return f"{card_name}: 효과 없음"
        return f"{card_name}: {result_type or '처리됨'}"

    def _resolve_fortune_land_thief_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        name = str(action.payload.get("card_name") or action.source)
        result = self._resolve_fortune_land_thief(state, player, name)
        self._emit_fortune_action_result(state, player, name, result)
        return result

    def _resolve_fortune_land_thief(self, state: GameState, player: PlayerState, name: str) -> dict:
        if self._is_muroe(player):
            own_candidates = self._owned_tile_candidates(state, player.player_id)
            pos = self._request_decision(
                "choose_trick_tile_target",
                state,
                player,
                name,
                list(own_candidates),
                "own_tile_give_marker",
                fallback=lambda: self._select_owned_tile(state, player.player_id, highest=False),
            )
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "muroe_no_owned_tile"}
            return {"type": "MUROE_GIVE_TILE", "transfer": self._transfer_tile(state, pos, state.marker_owner_id)}
        pos = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._other_player_tile_candidates(state, player)),
            "other_owned_tile_takeover",
            fallback=lambda: self._select_other_player_tile(state, player, highest=True),
        )
        if pos is None:
            return {"type": "NO_EFFECT", "reason": "no_other_tile"}
        tr = self._transfer_tile(state, pos, player.player_id)
        if tr.get("blocked_by_monopoly"):
            return {"type": "NO_EFFECT", "reason": "monopoly_protected", "attempt": "steal_tile", "pos": pos}
        return {"type": "STEAL_TILE", "transfer": tr}

    def _resolve_fortune_donation_angel_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        name = str(action.payload.get("card_name") or action.source)
        result = self._resolve_fortune_donation_angel(state, player, name)
        self._emit_fortune_action_result(state, player, name, result)
        return result

    def _resolve_fortune_donation_angel(self, state: GameState, player: PlayerState, name: str) -> dict:
        pos = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._owned_tile_candidates(state, player.player_id)),
            "own_tile_donation",
            fallback=lambda: self._select_owned_tile(state, player.player_id, highest=False),
        )
        if pos is None:
            return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
        tr = self._transfer_tile(state, pos, state.marker_owner_id)
        if tr.get("blocked_by_monopoly"):
            return {"type": "NO_EFFECT", "reason": "monopoly_protected", "attempt": "give_tile", "pos": pos}
        return {"type": "GIVE_TILE", "transfer": tr}

    def _resolve_fortune_forced_trade_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        name = str(action.payload.get("card_name") or action.source)
        result = self._resolve_fortune_forced_trade(state, player, name)
        self._emit_fortune_action_result(state, player, name, result)
        return result

    def _resolve_fortune_forced_trade(self, state: GameState, player: PlayerState, name: str) -> dict:
        own = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._owned_tile_candidates(state, player.player_id)),
            "trade_own_tile",
            fallback=lambda: self._select_owned_tile(state, player.player_id, highest=False),
        )
        other = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._other_player_tile_candidates(state, player)),
            "trade_other_tile",
            fallback=lambda: self._select_other_player_tile(state, player, highest=True),
        )
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

    def _resolve_fortune_pious_marker_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        name = str(action.payload.get("card_name") or action.source)
        result = self._resolve_fortune_pious_marker_gain(state, player, name)
        self._emit_fortune_action_result(state, player, name, result)
        return result

    def _resolve_fortune_pious_marker_gain(self, state: GameState, player: PlayerState, name: str) -> dict:
        pos = self._request_decision(
            "choose_trick_tile_target",
            state,
            player,
            name,
            list(self._empty_block_tile_candidates(state)),
            "marker_empty_block_gain",
            fallback=lambda: self._select_empty_block_tile(state),
        )
        if pos is None:
            return {"type": "NO_EFFECT", "reason": "no_empty_block"}
        state.tile_owner[pos] = player.player_id
        player.tiles_owned += 1
        return {"type": "PIOUS_MARKER_GAIN_TILE", "pos": pos}

    def _apply_fortune_move_only_impl(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        move = self._apply_target_move(
            state,
            player,
            target_pos,
            trigger=trigger,
            card_name=card_name,
            schedule_arrival=False,
        )
        return {
            "type": "MOVE_ONLY",
            "trigger": trigger,
            "card_name": card_name,
            "start_pos": move.get("start_pos"),
            "end_pos": move.get("end_pos"),
            "no_lap_credit": True,
        }

    def _apply_fortune_arrival(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        """Immediate wrapper for direct fortune arrival callers.

        The queued fortune path should use `_enqueue_fortune_target_move()` or `_enqueue_target_move_action()`.
        """
        result = self.events.emit_first_non_none("fortune.movement.resolve", state, player, target_pos, trigger, card_name, "arrival")
        return result if result is not None else self._apply_fortune_arrival_impl(state, player, target_pos, trigger, card_name)

    def _apply_fortune_move_only(self, state: GameState, player: PlayerState, target_pos: int, trigger: str, card_name: str) -> dict:
        """Immediate wrapper for direct fortune move-only callers."""
        result = self.events.emit_first_non_none("fortune.movement.resolve", state, player, target_pos, trigger, card_name, "move_only")
        return result if result is not None else self._apply_fortune_move_only_impl(state, player, target_pos, trigger, card_name)

    def _apply_fortune_card(self, state: GameState, player: PlayerState, card: FortuneCard) -> dict:
        result = self.events.emit_first_non_none("fortune.card.apply", state, player, card)
        return result if result is not None else self._apply_fortune_card_impl(state, player, card)

    def _produce_fortune_card_actions(self, state: GameState, player: PlayerState, card: FortuneCard) -> dict:
        producer_result = self.events.emit_first_non_none("fortune.card.produce", state, player, card)
        if producer_result is not None:
            return self._apply_fortune_producer_result(state, player, card, producer_result)
        return self._apply_fortune_card_impl(state, player, card, queue_followups=True)

    def _apply_fortune_producer_result(self, state: GameState, player: PlayerState, card: FortuneCard, producer_result: dict) -> dict:
        if not isinstance(producer_result, dict):
            return {"type": "CUSTOM_FORTUNE", "result": producer_result}
        result_type = str(producer_result.get("type", ""))
        if result_type == "QUEUE_TARGET_MOVE":
            target_pos = int(producer_result["target_pos"])
            movement_type = str(producer_result.get("movement_type") or "arrival")
            schedule_arrival = bool(producer_result.get("schedule_arrival", movement_type != "move_only"))
            trigger = str(producer_result.get("trigger") or "custom_fortune_move")
            queued = self._enqueue_fortune_target_move(
                state,
                player,
                target_pos,
                trigger=trigger,
                card_name=str(producer_result.get("card_name") or card.name),
                schedule_arrival=schedule_arrival,
                move=producer_result.get("move"),
                formula=str(producer_result.get("formula") or ""),
            )
            return {**producer_result, "type": "CUSTOM_QUEUED_TARGET_MOVE", "movement": queued}
        return producer_result

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
        draw_count = 2 if has_weather_id(state.current_weather_effects, WEATHER_FORTUNE_LUCKY_DAY_ID) else 1
        if draw_count > 1:
            cards: list[dict[str, Any]] = []
            resolutions: list[dict[str, Any]] = []
            for _ in range(draw_count):
                resolved = self._resolve_fortune_tile_single(state, player)
                cards.append(dict(resolved["card"]))
                resolutions.append(dict(resolved["resolution"]))
            return {"type": "FORTUNE_CHAIN", "count": draw_count, "cards": cards, "resolutions": resolutions}
        return self._resolve_fortune_tile_single(state, player)

    def _resolve_fortune_tile_single(self, state: GameState, player: PlayerState) -> dict:
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
        event = self._produce_fortune_card_actions(state, player, card)
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

    def _apply_fortune_card_impl(self, state: GameState, player: PlayerState, card: FortuneCard, *, queue_followups: bool = False) -> dict:
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
        if card_id == FORTUNE_MOVE_BACK_2_ID:
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, player.position - 2, trigger="backward_2", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, player.position - 2, "backward_2", name)
        if card_id == FORTUNE_MOVE_BACK_3_ID:
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, player.position - 3, trigger="backward_3", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, player.position - 3, "backward_3", name)
        if card_id == FORTUNE_TAKEOVER_BACK_2_ID:
            if queue_followups:
                return self._enqueue_fortune_takeover_backward(state, player, 2, name)
            return self._fortune_takeover_backward(state, player, 2, name)
        if card_id == FORTUNE_TAKEOVER_BACK_3_ID:
            if queue_followups:
                return self._enqueue_fortune_takeover_backward(state, player, 3, name)
            return self._fortune_takeover_backward(state, player, 3, name)
        if card_id == FORTUNE_PERFORMANCE_BONUS_ID:
            gain = player.shards
            player.cash += gain
            self._strategy_stats[player.player_id]["shard_income_cash"] += gain
            return {"type": "CASH_GAIN", "cash_delta": gain, "formula": "shards*1"}
        if card_id == FORTUNE_HIGH_PERFORMANCE_BONUS_ID:
            gain = player.shards * 2
            player.cash += gain
            self._strategy_stats[player.player_id]["shard_income_cash"] += gain
            return {"type": "CASH_GAIN", "cash_delta": gain, "formula": "shards*2"}
        if card_id == FORTUNE_TRAFFIC_VIOLATION_ID:
            cost = 6 + (2 if self._is_muroe(player) else 0)
            return {"type": "BANK_PAY", **self._pay_or_bankrupt(state, player, cost, None)}
        if card_id == FORTUNE_DRUNK_RIDING_ID:
            return {"type": "BANK_PAY", **self._pay_or_bankrupt(state, player, 10, None)}
        if card_id == FORTUNE_SUBSCRIPTION_WIN_ID:
            if queue_followups:
                return self._enqueue_fortune_subscription(state, player, name)
            return self._resolve_fortune_subscription(state, player, name)
        if card_id == FORTUNE_POOR_CONSTRUCTION_ID:
            pos = self._select_owned_tile(state, player.player_id, highest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            return {"type": "LOSE_TILE", "transfer": self._transfer_tile(state, pos, None)}
        if card_id == FORTUNE_LAND_THIEF_ID:
            if queue_followups:
                return self._enqueue_fortune_decision_action(state, player, "resolve_fortune_land_thief", name, "QUEUED_FORTUNE_LAND_THIEF")
            return self._resolve_fortune_land_thief(state, player, name)
        if card_id == FORTUNE_DONATION_ANGEL_ID:
            if queue_followups:
                return self._enqueue_fortune_decision_action(state, player, "resolve_fortune_donation_angel", name, "QUEUED_FORTUNE_DONATION_ANGEL")
            return self._resolve_fortune_donation_angel(state, player, name)
        if card_id == FORTUNE_PARTY_ID:
            return self._fortune_party(state, player, amount=2, reverse=self._is_muroe(player), name=name)
        if card_id == FORTUNE_SUSPICIOUS_DRINK_ID:
            roll = self._roll_standard_move(state, player, explicit_dice_count=1)
            if queue_followups:
                return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._enqueue_fortune_target_move(state, player, player.position + roll["move"], trigger="suspicious_drink", card_name=name, schedule_arrival=True, move=roll["move"], formula=str(roll.get("move", "")))}
            return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._apply_fortune_arrival(state, player, player.position + roll["move"], "suspicious_drink", name)}
        if card_id == FORTUNE_VERY_SUSPICIOUS_DRINK_ID:
            roll = self._roll_standard_move(state, player, explicit_dice_count=2)
            if queue_followups:
                return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._enqueue_fortune_target_move(state, player, player.position + roll["move"], trigger="very_suspicious_drink", card_name=name, schedule_arrival=True, move=roll["move"], formula=str(roll.get("move", "")))}
            return {"type": "ROLL_ARRIVAL", **roll, "arrival": self._apply_fortune_arrival(state, player, player.position + roll["move"], "very_suspicious_drink", name)}
        if card_id == FORTUNE_HALF_PRICE_SALE_ID:
            pos = self._select_owned_tile(state, player.player_id, highest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tile"}
            sale = math.ceil(state.config.rules.economy.purchase_cost_for(state, pos) / 2)
            player.cash += sale
            tr = self._transfer_tile(state, pos, None)
            state.tile_coins[pos] = 0
            return {"type": "SELL_HALF", "cash_delta": sale, "transfer": tr}
        if card_id == FORTUNE_BLESSED_DICE_ID:
            d1, d2 = self.rng.randint(1,6), self.rng.randint(1,6)
            total = d1 + d2
            gain = 18 if total == 12 else total
            player.cash += gain
            return {"type": "BLESS_DICE", "dice": [d1,d2], "cash_delta": gain}
        if card_id == FORTUNE_CURSED_DICE_ID:
            d1, d2 = self.rng.randint(1,6), self.rng.randint(1,6)
            total = d1 + d2
            cost = 18 if total == 2 else total
            return {"type": "CURSE_DICE", "dice": [d1,d2], **self._pay_or_bankrupt(state, player, cost, None)}
        if card_id == FORTUNE_GOOD_FOR_OTHERS_ID:
            affected = 0
            for op in state.players:
                if op.alive and op.player_id != player.player_id and op.attribute != "무뢰":
                    op.cash += 4
                    affected += 1
            return {"type": "OTHERS_GAIN", "amount": 4, "affected_players": affected}
        if card_id == FORTUNE_BITTER_ENVY_ID:
            marker_owner = state.players[state.marker_owner_id]
            if marker_owner.turns_taken >= state.rounds_completed + 1:
                return {"type": "NO_EFFECT", "reason": "marker_owner_turn_passed"}
            marker_owner.free_purchase_this_turn = True
            return {"type": "MARKER_FREE_PURCHASE", "target_player": marker_owner.player_id + 1}
        if card_id == FORTUNE_UNBEARABLE_SMILE_ID:
            for op in state.players:
                if not op.alive or op.player_id == player.player_id:
                    continue
                mult = 2 if op.attribute == "무뢰" else 1
                out = self._pay_or_bankrupt(state, op, 3 * mult, None)
                if not op.alive:
                    return {"type": "OTHERS_BANK_PAY", "failed_player": op.player_id + 1, "amount": 3 * mult}
            return {"type": "OTHERS_BANK_PAY", "amount": 3}
        if card_id == FORTUNE_IRRESISTIBLE_DEAL_ID:
            if queue_followups:
                return self._enqueue_fortune_decision_action(state, player, "resolve_fortune_forced_trade", name, "QUEUED_FORTUNE_FORCED_TRADE")
            return self._resolve_fortune_forced_trade(state, player, name)
        if card_id == FORTUNE_PIOUS_MARKER_ID:
            if state.marker_owner_id == player.player_id:
                if queue_followups:
                    return self._enqueue_fortune_decision_action(state, player, "resolve_fortune_pious_marker", name, "QUEUED_FORTUNE_PIOUS_MARKER")
                return self._resolve_fortune_pious_marker_gain(state, player, name)
            return {"type": "PAY_MARKER_OWNER", **self._pay_or_bankrupt(state, player, 4, state.marker_owner_id)}
        if card_id == FORTUNE_BEAST_HEART_ID:
            return self._fortune_beast_heart(state, player)
        if card_id == FORTUNE_SHORT_TRIP_ID:
            pos = self._find_extreme_player_position(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, pos, trigger="nearest_player", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, pos, "nearest_player", name)
        if card_id == FORTUNE_CUT_IN_LINE_ID:
            pos = self._find_extreme_player_position(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            if self._is_japin_or_muroe(player):
                if queue_followups:
                    return self._enqueue_fortune_target_move(state, player, pos, trigger="nearest_player_arrival", card_name=name, schedule_arrival=True)
                return self._apply_fortune_arrival(state, player, pos, "nearest_player_arrival", name)
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, pos, trigger="nearest_player_move", card_name=name, schedule_arrival=False)
            return self._apply_fortune_move_only(state, player, pos, "nearest_player_move", name)
        if card_id == FORTUNE_LONG_TRIP_ID:
            pos = self._find_extreme_player_position(state, player, nearest=False)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_other_players"}
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, pos, trigger="furthest_player", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, pos, "furthest_player", name)
        if card_id == FORTUNE_REST_STOP_ID:
            pos = self._find_extreme_owned_tile(state, player, nearest=True)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tiles"}
            if self._is_japin_or_muroe(player):
                pos = (pos + 1) % board_len
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, pos, trigger="nearest_owned_tile", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, pos, "nearest_owned_tile", name)
        if card_id == FORTUNE_SAFE_MOVE_ID:
            pos = self._find_extreme_owned_tile(state, player, nearest=False)
            if pos is None:
                return {"type": "NO_EFFECT", "reason": "no_owned_tiles"}
            if self._is_japin_or_muroe(player):
                pos = (pos + 1) % board_len
            if queue_followups:
                return self._enqueue_fortune_target_move(state, player, pos, trigger="furthest_owned_tile", card_name=name, schedule_arrival=True)
            return self._apply_fortune_arrival(state, player, pos, "furthest_owned_tile", name)
        if card_id == FORTUNE_METEOR_FALL_ID:
            self._change_f(state, 2, reason="fortune_effect", source=name, actor_pid=player.player_id)
            player.shards += 2
            return {"type": "METEOR", "f_delta": 2, "shards_delta": 2}
        if card_id == FORTUNE_PIG_DREAM_ID:
            gained = self._recover_dice_cards(state, player, 2, "fortune_pig_dream")
            return {"type": "GAIN_DICE_CARDS", "cards": gained}
        return {"type": "UNIMPLEMENTED", "name": name}

    def _empty_block_tile_candidates(self, state: GameState) -> list[int]:
        candidates: list[int] = []
        for idx, owner in enumerate(state.tile_owner):
            if owner is not None:
                continue
            if state.board[idx] not in {CellKind.T2, CellKind.T3}:
                continue
            if state.block_ids[idx] <= 0:
                continue
            candidates.append(idx)
        return candidates

    def _owned_tile_candidates(self, state: GameState, owner_id: int) -> list[int]:
        return [
            idx
            for idx, tile_owner in enumerate(state.tile_owner)
            if tile_owner == owner_id and state.board[idx] in {CellKind.T2, CellKind.T3}
        ]

    def _other_player_tile_candidates(self, state: GameState, player: PlayerState) -> list[int]:
        return [
            idx
            for idx, tile_owner in enumerate(state.tile_owner)
            if tile_owner is not None and tile_owner != player.player_id and state.board[idx] in {CellKind.T2, CellKind.T3}
        ]

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
        player.position = pos
        return self._resolve_fortune_takeover_backward_at_position(state, player, pos)

    def _resolve_fortune_takeover_backward_action(self, state: GameState, action: ActionEnvelope) -> dict:
        player = state.players[action.actor_player_id]
        return self._resolve_fortune_takeover_backward_at_position(state, player, player.position)

    def _resolve_fortune_takeover_backward_at_position(self, state: GameState, player: PlayerState, pos: int) -> dict:
        owner = state.tile_owner[pos]
        cell = state.board[pos]
        if cell in {CellKind.F1, CellKind.F2, CellKind.S}:
            return {"type": "NO_EFFECT", "reason": "special_tile", "end_pos": pos}
        if owner is None:
            return {"type": "NO_EFFECT", "reason": "unowned_tile", "end_pos": pos}
        if owner == player.player_id:
            tr = self._transfer_tile(state, pos, state.marker_owner_id)
            if tr.get("blocked_by_monopoly"):
                return {"type": "NO_EFFECT", "reason": "monopoly_protected", "end_pos": pos}
            return {"type": "TRANSFER_TO_MARKER", "end_pos": pos, "transfer": tr}
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
        context = build_score_token_placement_context(state, player, target, max_place=max_place, source=source)
        if not context.can_place:
            return None
        amount = context.amount
        state.tile_coins[target] += amount
        player.hand_coins -= amount
        player.score_coins_placed += amount
        self._strategy_stats[player.player_id]["coins_placed"] += amount
        return {
            "target": target,
            "amount": amount,
            "tile_total_after": state.tile_coins[target],
            "source": source,
            "placement_context": context.to_payload(),
        }

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
