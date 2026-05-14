from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUIRED_MODULE_CONTINUATION_FIELDS = (
    "resume_token",
    "frame_id",
    "module_id",
    "module_type",
    "module_cursor",
)


def missing_module_continuation_fields(payload: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_MODULE_CONTINUATION_FIELDS
        if not str(payload.get(field) or "").strip()
    ]


def is_simultaneous_batch_prompt(payload: Mapping[str, Any]) -> bool:
    module_type = str(payload.get("module_type") or "").strip()
    request_type = str(payload.get("request_type") or "").strip()
    module_cursor = str(payload.get("module_cursor") or "").strip()
    if module_type == "SimultaneousPromptBatchModule":
        return True
    return (
        module_type == "ResupplyModule"
        and request_type in {"burden_exchange", "resupply_choice"}
        and module_cursor.startswith("await_resupply_batch")
    )


def simultaneous_batch_state_error(payload: Mapping[str, Any]) -> str | None:
    if not is_simultaneous_batch_prompt(payload):
        return None
    if not str(payload.get("batch_id") or "").strip():
        return "missing_batch_id"
    if not isinstance(payload.get("missing_player_ids"), list) or not isinstance(
        payload.get("resume_tokens_by_player_id"),
        dict,
    ):
        return "missing_simultaneous_batch_state"
    return None
