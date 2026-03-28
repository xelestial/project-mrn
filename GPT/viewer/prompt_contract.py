"""Shared prompt envelope helpers for GPT human-play runtime."""
from __future__ import annotations

from typing import Any


def build_prompt_envelope(
    *,
    request_type: str,
    player_id: int,
    legal_choices: list[dict[str, Any]],
    public_context: dict[str, Any] | None = None,
    can_pass: bool = False,
    timeout_ms: int = 300_000,
    fallback_policy: str = "ai",
) -> dict[str, Any]:
    """Build a canonical prompt envelope with temporary legacy mirrors."""

    public_context = dict(public_context or {})
    mirrored_choices: list[dict[str, Any]] = []
    for choice in legal_choices:
        payload = dict(choice)
        payload.setdefault("id", payload.get("choice_id"))
        mirrored_choices.append(payload)

    envelope = {
        "request_type": request_type,
        "player_id": player_id,
        "legal_choices": mirrored_choices,
        "can_pass": can_pass,
        "timeout_ms": timeout_ms,
        "fallback_policy": fallback_policy,
        "public_context": public_context,
        # Temporary mirrors for the current viewer/test path.
        "type": request_type,
        "options": mirrored_choices,
    }
    envelope.update(public_context)
    return envelope


def extract_choice_id(response: dict[str, Any], default: str | None = None) -> str | None:
    """Accept both canonical and legacy response payloads."""
    choice_id = response.get("choice_id")
    if choice_id is not None:
        return str(choice_id)
    option_id = response.get("option_id")
    if option_id is not None:
        return str(option_id)
    return default
