from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedActionSpace:
    legal_actions: list[dict[str, Any]]
    chosen_action_id: str
    source: str


def normalize_decision_action_space(decision: dict[str, Any]) -> NormalizedActionSpace:
    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    decision_key = str(decision.get("decision_key") or decision.get("decision") or "")
    legal_actions = _extract_payload_actions(payload)
    source = "payload"

    if not legal_actions:
        legal_actions = _known_actions_for_decision(decision_key, payload)
        source = "known_decision" if legal_actions else "missing"

    return NormalizedActionSpace(
        legal_actions=legal_actions,
        chosen_action_id=_extract_chosen_action_id(decision.get("result")),
        source=source,
    )


def _extract_payload_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    options = payload.get("options")
    if not isinstance(options, list):
        options = payload.get("candidates")
    if not isinstance(options, list):
        offered_cards = payload.get("offered_cards")
        if isinstance(offered_cards, list):
            return [{"action_id": str(card), "legal": True, "label": str(card)} for card in offered_cards]
        card_choices = payload.get("card_choices")
        if isinstance(card_choices, list):
            return [{"action_id": str(card), "legal": True, "label": str(card)} for card in card_choices]
        return []

    actions: list[dict[str, Any]] = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            actions.append({"action_id": str(option), "legal": True, "label": str(option)})
            continue
        action_id = option.get("action_id") or option.get("id") or option.get("choice") or option.get("name") or str(index)
        action = {
            "action_id": str(action_id),
            "legal": bool(option.get("legal", True)),
        }
        if option.get("label") is not None:
            action["label"] = str(option["label"])
        actions.append(action)
    return actions


def _known_actions_for_decision(decision_key: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    key = decision_key.lower()
    if key in {"mark_target", "choose_mark_target"}:
        return (
            _actions_from_mapping(payload.get("candidate_scores"))
            or _actions_from_mapping(payload.get("candidate_probabilities"))
            or [{"action_id": "none", "legal": True, "label": "none"}]
        )
    if key in {"marker_flip", "active_flip", "choose_active_flip_card"}:
        return _actions_from_mapping(payload.get("candidate_scores")) or _actions_from_trace_feature(payload, "flippable_cards")
    if key in {"doctrine_relief", "choose_doctrine_relief_target"}:
        candidate_ids = payload.get("candidate_ids")
        if isinstance(candidate_ids, list):
            return [{"action_id": str(int(pid) + 1 if isinstance(pid, int) and pid < 4 else pid), "legal": True, "label": f"P{int(pid) + 1 if isinstance(pid, int) and pid < 4 else pid}"} for pid in candidate_ids]
    if key in {"burden_exchange", "choose_burden_exchange_on_supply"}:
        return [
            {"action_id": "accept", "legal": True, "label": "accept"},
            {"action_id": "reject", "legal": True, "label": "reject"},
        ]
    if key in {"purchase_decision", "choose_purchase_tile"}:
        return [
            {"action_id": "buy", "legal": True, "label": "BUY"},
            {"action_id": "skip", "legal": True, "label": "SKIP"},
        ]
    if key in {"lap_reward", "choose_lap_reward", "start_reward", "choose_start_reward"}:
        return [
            {"action_id": "cash", "legal": True, "label": "cash"},
            {"action_id": "shards", "legal": True, "label": "shards"},
            {"action_id": "coins", "legal": True, "label": "coins"},
        ]
    if key in {"movement_decision", "choose_movement"}:
        trace_actions = _movement_actions_from_trace(payload)
        if trace_actions:
            return trace_actions
        candidates = payload.get("movement_candidates")
        if isinstance(candidates, list):
            return [{"action_id": str(item), "legal": True, "label": str(item)} for item in candidates]
    if key in {"trick_use", "trick_to_use", "choose_trick_to_use", "hidden_trick", "choose_hidden_trick_card"}:
        trick_actions = _actions_from_mapping(payload.get("scores"))
        return [{"action_id": "none", "legal": True, "label": "none"}, *trick_actions]
    return []


def _actions_from_mapping(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [{"action_id": str(key), "legal": True, "label": str(key)} for key in value.keys()]


def _actions_from_trace_feature(payload: dict[str, Any], feature_key: str) -> list[dict[str, Any]]:
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    features = trace.get("features") if isinstance(trace.get("features"), dict) else {}
    value = features.get(feature_key)
    if not isinstance(value, list):
        return []
    return [{"action_id": str(item), "legal": True, "label": str(item)} for item in value]


def _movement_actions_from_trace(payload: dict[str, Any]) -> list[dict[str, Any]]:
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    adjustments = trace.get("effect_adjustments") if isinstance(trace.get("effect_adjustments"), list) else []
    action_ids = ["no_cards"]
    for item in adjustments:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        values = item.get("values")
        if kind in {"single_card_scores", "double_card_scores"} and isinstance(values, dict):
            action_ids.extend(str(key) for key in values.keys())
    return [{"action_id": action_id, "legal": True, "label": action_id} for action_id in dict.fromkeys(action_ids)]


def _extract_chosen_action_id(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("action_id", "choice_id", "choice", "picked_card", "name", "target_tile"):
            value = result.get(key)
            if value is not None:
                return str(value)
        if result.get("target_character") is not None:
            return str(result.get("target_character"))
        if result.get("chosen_card") is not None:
            return str(result.get("chosen_card"))
        if result.get("chosen_player_id") is not None:
            return str(result.get("chosen_player_id"))
        if result.get("accepted") is not None:
            return "accept" if result.get("accepted") else "reject"
        card_values = result.get("card_values")
        if isinstance(card_values, list) and card_values:
            return "+".join(str(v) for v in card_values)
        if result.get("use_cards") is False:
            return "no_cards"
        if result.get("purchased") is not None:
            return "buy" if result.get("purchased") else "skip"
    if result is None:
        return ""
    return str(result)
