from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Literal

DecisionProvider = Literal["human", "ai"]


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


def serialize_ai_choice_id(method_name: str, result: Any) -> str:
    if method_name == "choose_movement":
        use_cards = bool(getattr(result, "use_cards", False))
        card_values = tuple(getattr(result, "card_values", ()) or ())
        if not use_cards or not card_values:
            return "dice"
        return "card_" + "_".join(str(value) for value in card_values)

    if method_name == "choose_lap_reward":
        choice = getattr(result, "choice", None)
        return str(choice) if isinstance(choice, str) and choice else "blocked"

    if method_name in {"choose_purchase_tile", "choose_burden_exchange_on_supply", "choose_runaway_slave_step"}:
        return "yes" if bool(result) else "no"

    if method_name in {"choose_trick_to_use", "choose_hidden_trick_card", "choose_specific_trick_reward"}:
        if result is None:
            return "none"
        deck_index = getattr(result, "deck_index", None)
        if isinstance(deck_index, int):
            return str(deck_index)
        return str(getattr(result, "name", result))

    if method_name in {"choose_coin_placement_tile", "choose_active_flip_card", "choose_doctrine_relief_target"}:
        return "none" if result is None else str(result)

    if method_name == "choose_mark_target":
        return "none" if result is None else str(result)

    if method_name == "choose_pabal_dice_mode":
        return str(result)

    if method_name in {"choose_draft_card", "choose_final_character", "choose_geo_bonus"}:
        return str(result)

    return "none" if result is None else str(result)


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

    if method_name in {"choose_draft_card", "choose_final_character"}:
        cards = args[2] if len(args) > 2 else kwargs.get("offered_cards") or kwargs.get("card_choices")
        if isinstance(cards, list):
            context["choice_count"] = len(cards)
    elif method_name == "choose_purchase_tile":
        context["tile_index"] = args[2] if len(args) > 2 else kwargs.get("pos")
        context["cost"] = args[4] if len(args) > 4 else kwargs.get("cost")
        context["source"] = kwargs.get("source", "landing")
    elif method_name == "choose_mark_target":
        context["actor_name"] = args[2] if len(args) > 2 else kwargs.get("actor_name")
    elif method_name == "choose_active_flip_card":
        flippable_cards = args[2] if len(args) > 2 else kwargs.get("flippable_cards")
        if isinstance(flippable_cards, list):
            context["flip_count"] = len(flippable_cards)
    elif method_name == "choose_hidden_trick_card":
        hand = args[2] if len(args) > 2 else kwargs.get("hand")
        if isinstance(hand, list):
            context["hand_count"] = len(hand)
            context["selection_required"] = True
    elif method_name == "choose_trick_to_use":
        hand = args[2] if len(args) > 2 else kwargs.get("hand")
        if isinstance(hand, list):
            context["hand_count"] = len(hand)
    elif method_name == "choose_specific_trick_reward":
        choices = args[2] if len(args) > 2 else kwargs.get("choices")
        if isinstance(choices, list):
            context["reward_count"] = len(choices)
    elif method_name == "choose_coin_placement_tile":
        owned_tiles = getattr(player, "visited_owned_tile_indices", None)
        if owned_tiles is not None:
            context["owned_tile_count"] = len(list(owned_tiles))
    elif method_name == "choose_doctrine_relief_target":
        candidates = args[2] if len(args) > 2 else kwargs.get("candidates")
        if isinstance(candidates, list):
            context["candidate_count"] = len(candidates)
    elif method_name == "choose_runaway_slave_step":
        context["one_short_pos"] = args[2] if len(args) > 2 else kwargs.get("one_short_pos")
        context["bonus_target_pos"] = args[3] if len(args) > 3 else kwargs.get("bonus_target_pos")
        context["bonus_target_kind"] = str(args[4] if len(args) > 4 else kwargs.get("bonus_target_kind"))

    return _trim_public_context(context)


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
        self.publish(
            "event",
            build_decision_requested_payload(
                request_id=request_id,
                player_id=player_id,
                request_type=str(envelope.get("request_type", "")),
                fallback_policy=fallback_policy,
                provider="human",
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
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
            self.publish(
                "event",
                build_decision_resolved_payload(
                    request_id=request_id,
                    player_id=player_id,
                    resolution="timeout_fallback",
                    choice_id=fallback_result.get("choice_id"),
                    provider="human",
                    round_index=public_context.get("round_index"),
                    turn_index=public_context.get("turn_index"),
                ),
            )
            self.publish(
                "event",
                build_decision_timeout_fallback_payload(
                    request_id=request_id,
                    player_id=player_id,
                    fallback_policy=fallback_policy,
                    fallback_execution=fallback_result.get("status"),
                    fallback_choice_id=fallback_result.get("choice_id"),
                    provider="human",
                    round_index=public_context.get("round_index"),
                    turn_index=public_context.get("turn_index"),
                ),
            )
            return fallback_fn()

        try:
            parsed = parser(response)
        except Exception:
            self.publish(
                "event",
                build_decision_resolved_payload(
                    request_id=request_id,
                    player_id=player_id,
                    resolution="parser_error_fallback",
                    choice_id=str(response.get("choice_id", "")),
                    provider="human",
                    round_index=public_context.get("round_index"),
                    turn_index=public_context.get("turn_index"),
                ),
            )
            return fallback_fn()

        self.publish(
            "event",
            build_decision_resolved_payload(
                request_id=request_id,
                player_id=int(response.get("player_id", player_id)),
                resolution="accepted",
                choice_id=str(response.get("choice_id", "")),
                provider="human",
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
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
        self.publish(
            "event",
            build_decision_requested_payload(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                fallback_policy="ai",
                provider="ai",
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )
        result = resolver()
        self.publish(
            "event",
            build_decision_resolved_payload(
                request_id=request_id,
                player_id=player_id,
                resolution="accepted",
                choice_id=choice_serializer(result),
                provider="ai",
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )
        return result

    def publish(self, message_type: str, payload: dict) -> None:
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, message_type, payload),
            self._loop,
        )
        fut.result()
