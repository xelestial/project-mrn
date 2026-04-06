from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal

DecisionProvider = Literal["human", "ai"]

ChoiceSerializer = Callable[[Any], str]
ContextBuilder = Callable[[tuple[Any, ...], dict[str, Any], Any, Any], dict[str, Any]]


@dataclass(frozen=True)
class DecisionMethodSpec:
    request_type: str
    choice_serializer: ChoiceSerializer
    public_context_builder: ContextBuilder | None = None


@dataclass(frozen=True)
class PreparedDecisionMethod:
    request_type: str
    public_context: dict[str, Any]
    choice_serializer: ChoiceSerializer


@dataclass(frozen=True)
class DecisionInvocation:
    method_name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    state: Any
    player: Any
    player_id: int | None


@dataclass(frozen=True)
class CanonicalDecisionRequest:
    decision_name: str
    request_type: str
    player_id: int | None
    round_index: int | None
    turn_index: int | None
    public_context: dict[str, Any]
    fallback_policy: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def _number_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _trim_public_context(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _round_index_from_state(state: Any) -> int | None:
    rounds_completed = _number_or_none(getattr(state, "rounds_completed", None))
    if rounds_completed is None:
        return None
    return rounds_completed + 1


def _turn_index_from_state(state: Any) -> int | None:
    turn_index = _number_or_none(getattr(state, "turn_index", None))
    if turn_index is None:
        return None
    return turn_index + 1


def _arg_or_kw(args: tuple[Any, ...], kwargs: dict[str, Any], index: int, key: str) -> Any:
    return args[index] if len(args) > index else kwargs.get(key)


def _serialize_default_choice(result: Any) -> str:
    return "none" if result is None else str(result)


def _serialize_movement_choice(result: Any) -> str:
    use_cards = bool(getattr(result, "use_cards", False))
    card_values = tuple(getattr(result, "card_values", ()) or ())
    if not use_cards or not card_values:
        return "dice"
    return "card_" + "_".join(str(value) for value in card_values)


def _serialize_lap_reward_choice(result: Any) -> str:
    choice = getattr(result, "choice", None)
    return str(choice) if isinstance(choice, str) and choice else "blocked"


def _serialize_yes_no_choice(result: Any) -> str:
    return "yes" if bool(result) else "no"


def _serialize_trick_like_choice(result: Any) -> str:
    if result is None:
        return "none"
    deck_index = getattr(result, "deck_index", None)
    if isinstance(deck_index, int):
        return str(deck_index)
    return str(getattr(result, "name", result))


def _serialize_string_choice(result: Any) -> str:
    return str(result)


def _build_card_choice_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    cards = _arg_or_kw(args, kwargs, 2, "offered_cards") or kwargs.get("card_choices")
    if isinstance(cards, list):
        return {"choice_count": len(cards)}
    return {}


def _build_purchase_tile_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {
        "tile_index": _arg_or_kw(args, kwargs, 2, "pos"),
        "cost": _arg_or_kw(args, kwargs, 4, "cost"),
        "source": kwargs.get("source", "landing"),
    }


def _build_mark_target_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {"actor_name": _arg_or_kw(args, kwargs, 2, "actor_name")}


def _build_active_flip_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    flippable_cards = _arg_or_kw(args, kwargs, 2, "flippable_cards")
    if isinstance(flippable_cards, list):
        return {"flip_count": len(flippable_cards)}
    return {}


def _build_hidden_trick_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        return {"hand_count": len(hand), "selection_required": True}
    return {}


def _build_trick_to_use_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        return {"hand_count": len(hand)}
    return {}


def _build_specific_trick_reward_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    choices = _arg_or_kw(args, kwargs, 2, "choices")
    if isinstance(choices, list):
        return {"reward_count": len(choices)}
    return {}


def _build_coin_placement_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del args, kwargs, state
    owned_tiles = getattr(player, "visited_owned_tile_indices", None)
    if owned_tiles is not None:
        return {"owned_tile_count": len(list(owned_tiles))}
    return {}


def _build_doctrine_relief_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    candidates = _arg_or_kw(args, kwargs, 2, "candidates")
    if isinstance(candidates, list):
        return {"candidate_count": len(candidates)}
    return {}


def _build_runaway_step_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {
        "one_short_pos": _arg_or_kw(args, kwargs, 2, "one_short_pos"),
        "bonus_target_pos": _arg_or_kw(args, kwargs, 3, "bonus_target_pos"),
        "bonus_target_kind": str(_arg_or_kw(args, kwargs, 4, "bonus_target_kind")),
    }


METHOD_SPECS: dict[str, DecisionMethodSpec] = {
    "choose_movement": DecisionMethodSpec("movement", _serialize_movement_choice),
    "choose_runaway_slave_step": DecisionMethodSpec(
        "runaway_step_choice",
        _serialize_yes_no_choice,
        _build_runaway_step_context,
    ),
    "choose_lap_reward": DecisionMethodSpec("lap_reward", _serialize_lap_reward_choice),
    "choose_draft_card": DecisionMethodSpec("draft_card", _serialize_string_choice, _build_card_choice_context),
    "choose_final_character": DecisionMethodSpec(
        "final_character",
        _serialize_string_choice,
        _build_card_choice_context,
    ),
    "choose_trick_to_use": DecisionMethodSpec(
        "trick_to_use",
        _serialize_trick_like_choice,
        _build_trick_to_use_context,
    ),
    "choose_purchase_tile": DecisionMethodSpec(
        "purchase_tile",
        _serialize_yes_no_choice,
        _build_purchase_tile_context,
    ),
    "choose_hidden_trick_card": DecisionMethodSpec(
        "hidden_trick_card",
        _serialize_trick_like_choice,
        _build_hidden_trick_context,
    ),
    "choose_mark_target": DecisionMethodSpec("mark_target", _serialize_default_choice, _build_mark_target_context),
    "choose_coin_placement_tile": DecisionMethodSpec(
        "coin_placement",
        _serialize_default_choice,
        _build_coin_placement_context,
    ),
    "choose_geo_bonus": DecisionMethodSpec("geo_bonus", _serialize_string_choice),
    "choose_doctrine_relief_target": DecisionMethodSpec(
        "doctrine_relief",
        _serialize_default_choice,
        _build_doctrine_relief_context,
    ),
    "choose_active_flip_card": DecisionMethodSpec(
        "active_flip",
        _serialize_default_choice,
        _build_active_flip_context,
    ),
    "choose_specific_trick_reward": DecisionMethodSpec(
        "specific_trick_reward",
        _serialize_trick_like_choice,
        _build_specific_trick_reward_context,
    ),
    "choose_burden_exchange_on_supply": DecisionMethodSpec("burden_exchange", _serialize_yes_no_choice),
    "choose_pabal_dice_mode": DecisionMethodSpec("pabal_dice_mode", _serialize_string_choice),
}


def _decision_method_spec_for_method(method_name: str) -> DecisionMethodSpec:
    return METHOD_SPECS.get(
        method_name,
        DecisionMethodSpec(
            request_type=method_name.removeprefix("choose_"),
            choice_serializer=_serialize_default_choice,
        ),
    )


def serialize_ai_choice_id(method_name: str, result: Any) -> str:
    return _decision_method_spec_for_method(method_name).choice_serializer(result)


def decision_request_type_for_method(method_name: str) -> str:
    return _decision_method_spec_for_method(method_name).request_type


def build_public_context(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    state = args[0] if len(args) > 0 else kwargs.get("state")
    player = args[1] if len(args) > 1 else kwargs.get("player")
    context: dict[str, Any] = {
        "round_index": _round_index_from_state(state),
        "turn_index": _turn_index_from_state(state),
        "player_cash": getattr(player, "cash", None),
        "player_position": getattr(player, "position", None),
        "player_shards": getattr(player, "shards", None),
    }
    spec = _decision_method_spec_for_method(method_name)
    if spec.public_context_builder is not None:
        context.update(spec.public_context_builder(args, kwargs, state, player))

    return _trim_public_context(context)


def prepare_decision_method(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> PreparedDecisionMethod:
    invocation = build_decision_invocation(method_name, args, kwargs)
    return prepare_decision_method_from_invocation(invocation)


def build_decision_invocation(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> DecisionInvocation:
    state = args[0] if len(args) > 0 else kwargs.get("state")
    player = args[1] if len(args) > 1 else kwargs.get("player")
    raw_player_id = getattr(player, "player_id", None)
    player_id = raw_player_id if isinstance(raw_player_id, int) else None
    return DecisionInvocation(
        method_name=method_name,
        args=args,
        kwargs=dict(kwargs),
        state=state,
        player=player,
        player_id=player_id,
    )


def prepare_decision_method_from_invocation(invocation: DecisionInvocation) -> PreparedDecisionMethod:
    spec = _decision_method_spec_for_method(invocation.method_name)
    return PreparedDecisionMethod(
        request_type=spec.request_type,
        public_context=build_public_context(invocation.method_name, invocation.args, invocation.kwargs),
        choice_serializer=spec.choice_serializer,
    )


def build_canonical_decision_request(
    invocation: DecisionInvocation,
    *,
    fallback_policy: str = "ai",
) -> CanonicalDecisionRequest:
    prepared = prepare_decision_method_from_invocation(invocation)
    public_context = dict(prepared.public_context)
    return CanonicalDecisionRequest(
        decision_name=invocation.method_name,
        request_type=prepared.request_type,
        player_id=invocation.player_id,
        round_index=public_context.get("round_index"),
        turn_index=public_context.get("turn_index"),
        public_context=public_context,
        fallback_policy=fallback_policy,
        args=invocation.args,
        kwargs=dict(invocation.kwargs),
    )


def build_decision_ack_payload(
    *,
    request_id: str,
    status: str,
    player_id: int,
    reason: str | None = None,
    provider: DecisionProvider = "human",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": request_id,
        "status": status,
        "player_id": player_id,
        "provider": provider,
    }
    if reason:
        payload["reason"] = reason
    return payload


def build_decision_requested_payload(
    *,
    request_id: str,
    player_id: int,
    request_type: str,
    fallback_policy: str,
    provider: DecisionProvider,
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_requested",
        "request_id": request_id,
        "player_id": player_id,
        "request_type": request_type,
        "fallback_policy": fallback_policy,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


def build_decision_resolved_payload(
    *,
    request_id: str,
    player_id: int,
    resolution: str,
    choice_id: str | None,
    provider: DecisionProvider,
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_resolved",
        "request_id": request_id,
        "player_id": player_id,
        "resolution": resolution,
        "choice_id": choice_id,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


def build_decision_timeout_fallback_payload(
    *,
    request_id: str,
    player_id: int,
    fallback_policy: str,
    fallback_execution: str | None,
    fallback_choice_id: str | None,
    provider: DecisionProvider = "human",
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_timeout_fallback",
        "request_id": request_id,
        "player_id": player_id,
        "fallback_policy": fallback_policy,
        "fallback_execution": fallback_execution,
        "fallback_choice_id": fallback_choice_id,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


class DecisionGateway:
    """Canonical runtime decision contract publisher for human and AI seats."""

    def __init__(
        self,
        *,
        session_id: str,
        prompt_service,
        stream_service,
        loop: asyncio.AbstractEventLoop,
        touch_activity: Callable[[str], None],
        fallback_executor,
    ) -> None:
        self._session_id = session_id
        self._prompt_service = prompt_service
        self._stream_service = stream_service
        self._loop = loop
        self._touch_activity = touch_activity
        self._fallback_executor = fallback_executor
        self._request_seq = 0

    def next_request_id(self) -> str:
        self._request_seq += 1
        return f"{self._session_id}_req_{self._request_seq}_{uuid.uuid4().hex[:6]}"

    def _publish_decision_requested(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
        fallback_policy: str,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_requested_payload(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                fallback_policy=fallback_policy,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def _publish_decision_resolved(
        self,
        *,
        request_id: str,
        player_id: int,
        resolution: str,
        choice_id: str | None,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_resolved_payload(
                request_id=request_id,
                player_id=player_id,
                resolution=resolution,
                choice_id=choice_id,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def _publish_decision_timeout_fallback(
        self,
        *,
        request_id: str,
        player_id: int,
        fallback_policy: str,
        fallback_execution: str | None,
        fallback_choice_id: str | None,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_timeout_fallback_payload(
                request_id=request_id,
                player_id=player_id,
                fallback_policy=fallback_policy,
                fallback_execution=fallback_execution,
                fallback_choice_id=fallback_choice_id,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def resolve_human_prompt(self, prompt: dict, parser, fallback_fn):
        envelope = dict(prompt)
        request_id = str(envelope.get("request_id") or self.next_request_id())
        timeout_ms = max(1, int(envelope.get("timeout_ms", 300000)))
        player_id = int(envelope.get("player_id", 0))
        fallback_policy = str(envelope.get("fallback_policy", "timeout_fallback"))
        public_context = dict(envelope.get("public_context") or {})

        envelope["request_id"] = request_id
        envelope["timeout_ms"] = timeout_ms

        try:
            self._prompt_service.create_prompt(session_id=self._session_id, prompt=envelope)
        except ValueError:
            request_id = self.next_request_id()
            envelope["request_id"] = request_id
            self._prompt_service.create_prompt(session_id=self._session_id, prompt=envelope)

        self.publish("prompt", {**envelope, "provider": "human"})
        self._publish_decision_requested(
            request_id=request_id,
            player_id=player_id,
            request_type=str(envelope.get("request_type", "")),
            fallback_policy=fallback_policy,
            provider="human",
            public_context=public_context,
        )
        self._touch_activity(self._session_id)
        response = self._prompt_service.wait_for_decision(request_id=request_id, timeout_ms=timeout_ms)

        if response is None:
            expired = self._prompt_service.expire_prompt(request_id=request_id, reason="prompt_timeout")
            if expired is None:
                return fallback_fn()
            fallback_result = asyncio.run_coroutine_threadsafe(
                self._fallback_executor(
                    session_id=self._session_id,
                    request_id=request_id,
                    player_id=player_id,
                    fallback_policy=fallback_policy,
                    prompt_payload=envelope,
                ),
                self._loop,
            ).result()
            self.publish(
                "decision_ack",
                build_decision_ack_payload(
                    request_id=request_id,
                    status="stale",
                    player_id=player_id,
                    reason="prompt_timeout",
                    provider="human",
                ),
            )
            self._publish_decision_resolved(
                request_id=request_id,
                player_id=player_id,
                resolution="timeout_fallback",
                choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            self._publish_decision_timeout_fallback(
                request_id=request_id,
                player_id=player_id,
                fallback_policy=fallback_policy,
                fallback_execution=fallback_result.get("status"),
                fallback_choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        try:
            parsed = parser(response)
        except Exception:
            self._publish_decision_resolved(
                request_id=request_id,
                player_id=player_id,
                resolution="parser_error_fallback",
                choice_id=str(response.get("choice_id", "")),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        self._publish_decision_resolved(
            request_id=request_id,
            player_id=int(response.get("player_id", player_id)),
            resolution="accepted",
            choice_id=str(response.get("choice_id", "")),
            provider="human",
            public_context=public_context,
        )
        return parsed

    def resolve_ai_decision(
        self,
        *,
        request_type: str,
        player_id: int,
        public_context: dict[str, Any],
        resolver: Callable[[], Any],
        choice_serializer: Callable[[Any], str],
    ) -> Any:
        request_id = self.next_request_id()
        self._publish_decision_requested(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            fallback_policy="ai",
            provider="ai",
            public_context=public_context,
        )
        result = resolver()
        self._publish_decision_resolved(
            request_id=request_id,
            player_id=player_id,
            resolution="accepted",
            choice_id=choice_serializer(result),
            provider="ai",
            public_context=public_context,
        )
        return result

    def publish(self, message_type: str, payload: dict) -> None:
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, message_type, payload),
            self._loop,
        )
        fut.result()
