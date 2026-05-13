from __future__ import annotations

from typing import Any


class CommandInbox:
    """Durable accepted-command boundary.

    Wakeup paths may only use the command reference returned from this class.
    They must not become the source of truth for accepted input.
    """

    def __init__(self, *, command_store=None) -> None:
        self._command_store = command_store

    @property
    def command_store(self):
        return self._command_store

    def supports_atomic_prompt_decision(self, prompt_store: Any) -> bool:
        return self._command_store is not None and callable(
            getattr(prompt_store, "accept_decision_with_command", None)
        )

    def accept_prompt_decision(
        self,
        *,
        prompt_store: Any,
        session_id: str,
        request_id: str,
        decision_payload: dict[str, Any],
        resolved_payload: dict[str, Any],
        command_payload: dict[str, Any],
        server_time_ms: int,
    ) -> dict[str, Any] | None:
        atomic_accept = getattr(prompt_store, "accept_decision_with_command", None)
        if self._command_store is None or not callable(atomic_accept):
            raise RuntimeError("atomic_prompt_decision_not_supported")
        try:
            return atomic_accept(
                session_id=session_id,
                request_id=request_id,
                decision_payload=decision_payload,
                resolved_payload=resolved_payload,
                command_store=self._command_store,
                command_type="decision_submitted",
                command_payload=command_payload,
                server_time_ms=server_time_ms,
            )
        except RuntimeError as exc:
            if str(exc) == "redis_lua_required":
                return None
            raise

    def append_decision_command(
        self,
        *,
        session_id: str,
        command_payload: dict[str, Any],
        request_id: str,
        server_time_ms: int,
    ) -> dict[str, Any] | None:
        if self._command_store is None:
            return None
        try:
            return self._command_store.append_command(
                session_id,
                "decision_submitted",
                command_payload,
                request_id=request_id,
                server_time_ms=server_time_ms,
            )
        except RuntimeError as exc:
            if str(exc) == "redis_lua_required":
                return None
            raise
