from __future__ import annotations

from typing import Any


def module_prompt(
    payload: dict[str, Any],
    *,
    module_type: str = "TrickChoiceModule",
    frame_id: str = "seq:test",
    module_id: str | None = None,
    module_cursor: str = "test:await_prompt",
) -> dict[str, Any]:
    request_id = str(payload.get("request_id") or "req_test")
    enriched = dict(payload)
    enriched.setdefault("runner_kind", "module")
    enriched.setdefault("resume_token", f"resume:{request_id}")
    enriched.setdefault("frame_id", frame_id)
    enriched.setdefault("module_id", module_id or f"mod:test:{request_id}")
    enriched.setdefault("module_type", module_type)
    enriched.setdefault("module_cursor", module_cursor)
    enriched.setdefault(
        "runtime_module",
        {
            "runner_kind": "module",
            "frame_type": _frame_type(frame_id),
            "frame_id": enriched["frame_id"],
            "module_id": enriched["module_id"],
            "module_type": enriched["module_type"],
            "module_cursor": enriched["module_cursor"],
        },
    )
    return enriched


def _frame_type(frame_id: str) -> str:
    if frame_id.startswith("round:"):
        return "round"
    if frame_id.startswith("turn:"):
        return "turn"
    if frame_id.startswith("simul:"):
        return "simultaneous"
    return "sequence"
