from __future__ import annotations

from typing import Any

from apps.server.src.infra.structured_log import log_event


class CommandRouter:
    """Wake the runtime for commands that are already durable in the inbox."""

    def __init__(
        self,
        *,
        session_loop_manager: Any | None = None,
        consumer_name: str = "runtime_wakeup",
    ) -> None:
        self._session_loop_manager = session_loop_manager
        self._consumer_name = str(consumer_name or "runtime_wakeup")

    def wake_after_accept(
        self,
        *,
        command_ref: dict[str, Any],
        session_id: str,
        trigger: str,
    ) -> dict[str, Any]:
        if str(command_ref.get("status") or "") != "accepted":
            return {"status": "skipped", "reason": "command_not_accepted"}
        return self.wake_command(command_ref=command_ref, session_id=session_id, trigger=trigger)

    def wake_command(
        self,
        *,
        command_ref: dict[str, Any],
        session_id: str,
        trigger: str,
    ) -> dict[str, Any]:
        command_seq = _command_seq(command_ref)
        if command_seq is None or command_seq <= 0:
            return {"status": "skipped", "reason": "invalid_command_seq"}
        command_session_id = str(command_ref.get("session_id") or session_id).strip()
        if command_session_id != session_id:
            log_event(
                "runtime_wakeup_command_skipped",
                session_id=session_id,
                command_session_id=command_session_id,
                command_seq=command_seq,
                trigger=trigger,
                reason="session_mismatch",
            )
            return {"status": "skipped", "reason": "session_mismatch", "command_seq": command_seq}

        if self._session_loop_manager is not None:
            return self._session_loop_manager.wake(
                session_id=session_id,
                command_ref=command_ref,
                trigger=trigger,
            )
        log_event(
            "runtime_wakeup_command_skipped",
            session_id=session_id,
            command_seq=command_seq,
            trigger=trigger,
            reason="missing_session_loop_manager",
        )
        return {"status": "skipped", "reason": "missing_session_loop_manager", "command_seq": command_seq}


def _command_seq(command_ref: dict[str, Any]) -> int | None:
    for field_name in ("command_seq", "seq"):
        value = command_ref.get(field_name)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
