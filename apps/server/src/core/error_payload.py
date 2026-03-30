from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    category: str
    retryable: bool
    message: str


_ERROR_CATEGORY_MAP: dict[str, str] = {
    "SESSION_NOT_FOUND": "session",
    "INVALID_REQUEST": "validation",
    "JOIN_REJECTED": "auth",
    "INVALID_STATE_TRANSITION": "state",
    "UNAUTHORIZED_SEAT": "auth",
    "PLAYER_MISMATCH": "auth",
    "UNSUPPORTED_MESSAGE": "transport",
    "RESUME_GAP_TOO_OLD": "transport",
    "PROMPT_REJECTED": "prompt",
    "RUNTIME_EXECUTION_FAILED": "runtime",
    "RUNTIME_STALLED_WARN": "runtime",
}


def build_error_payload(
    *,
    code: str,
    message: str,
    retryable: bool | None = None,
) -> dict:
    category = _ERROR_CATEGORY_MAP.get(code, "general")
    normalized_retryable = retryable if retryable is not None else category in {"transport", "runtime"}
    return {
        "code": code,
        "category": category,
        "message": message,
        "retryable": bool(normalized_retryable),
    }
