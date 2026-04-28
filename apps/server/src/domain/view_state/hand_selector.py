from __future__ import annotations

from typing import Any

from .prompt_selector import latest_active_prompt
from .types import HandTrayCardViewState, HandTrayViewState


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _cards_from_public_context(public_context: dict[str, Any]) -> list[HandTrayCardViewState]:
    full_hand = public_context.get("full_hand")
    if isinstance(full_hand, list) and full_hand:
        cards: list[HandTrayCardViewState] = []
        for index, item in enumerate(full_hand):
            card = _record(item)
            if not card:
                continue
            deck_index = _number(card.get("deck_index"))
            name = _string(card.get("name")) or "Trick"
            cards.append(
                {
                    "key": f"{deck_index if deck_index is not None else 'x'}-{index}-{name}",
                    "name": name,
                    "description": _string(card.get("card_description")) or _string(card.get("description")),
                    "deck_index": deck_index,
                    "is_hidden": card.get("is_hidden") is True,
                    "is_current_target": card.get("is_current_target") is True,
                }
            )
        return cards

    burden_cards = public_context.get("burden_cards")
    if isinstance(burden_cards, list) and burden_cards:
        cards = []
        for index, item in enumerate(burden_cards):
            card = _record(item)
            if not card:
                continue
            deck_index = _number(card.get("deck_index"))
            name = _string(card.get("name")) or "Burden"
            cards.append(
                {
                    "key": f"{deck_index if deck_index is not None else 'x'}-{index}-{name}",
                    "name": name,
                    "description": _string(card.get("card_description")) or _string(card.get("description")),
                    "deck_index": deck_index,
                    "is_hidden": False,
                    "is_current_target": card.get("is_current_target") is True,
                }
            )
        return cards

    return []


def build_hand_tray_view_state(messages: list[dict[str, Any]]) -> HandTrayViewState | None:
    active_prompt = latest_active_prompt(messages)
    if active_prompt:
        public_context = _record(active_prompt.get("public_context")) or {}
        active_cards = _cards_from_public_context(public_context)
        if active_cards:
            return {"cards": active_cards}

    for message in reversed(messages):
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        if payload.get("event_type") != "trick_used":
            continue
        cards = _cards_from_public_context(payload)
        if cards:
            return {"cards": cards}
        return {"cards": []}

    for message in reversed(messages):
        if message.get("type") != "prompt":
            continue
        payload = _record(message.get("payload")) or {}
        public_context = _record(payload.get("public_context")) or {}
        cards = _cards_from_public_context(public_context)
        if cards:
            return {"cards": cards}
    return None
