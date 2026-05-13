from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.command_recovery import CommandRecoveryService


class CommandProcessingGuardService:
    """Validate durable command processing preconditions and terminal stale commands."""

    def __init__(
        self,
        *,
        command_store: Any | None,
        command_recovery: CommandRecoveryService,
        prompt_lifecycle_provider: Callable[[str, dict | None], dict | None],
        now_ms: Callable[[], int],
    ) -> None:
        self._command_store = command_store
        self._command_recovery = command_recovery
        self._prompt_lifecycle_provider = prompt_lifecycle_provider
        self._now_ms = now_ms

    def guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        if self._command_store is None:
            return None
        target_seq = int(command_seq)
        offset = self._command_recovery.load_command_consumer_offset(session_id, consumer_name)
        if offset is not None and offset >= target_seq:
            matching_waiting_command = self._command_recovery.matching_resume_command_for_seq(
                session_id,
                target_seq,
                include_resolved=True,
            )
            if matching_waiting_command is not None:
                log_event(
                    "runtime_command_offset_conflict_reprocessing",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    request_id=CommandRecoveryService.command_payload_field(matching_waiting_command, "request_id"),
                )
                return None
            log_event(
                "runtime_command_already_consumed",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                consumer_offset=offset,
                stage=stage,
            )
            return {
                "status": "already_processed",
                "reason": "consumer_offset_already_advanced",
                "processed_command_seq": target_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": offset,
            }

        pending = self._command_recovery.pending_resume_command(session_id, consumer_name=consumer_name)
        target_command = self._command_recovery.command_for_seq(session_id, target_seq)
        target_command_type = str((target_command or {}).get("type") or "").strip()
        if pending is None:
            matching_waiting_command = self._command_recovery.matching_resume_command_for_seq(
                session_id,
                target_seq,
                include_resolved=True,
            )
            if matching_waiting_command is not None:
                self._log_checkpoint_waiting_reprocessing(
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    command=matching_waiting_command,
                )
                return None
            if target_command is None or target_command_type != "decision_submitted":
                return None
            log_event(
                "runtime_command_no_longer_pending",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                consumer_offset=offset,
                stage=stage,
            )
            self.save_rejected_command_offset(
                consumer_name,
                session_id,
                target_seq,
                reason=self.stale_command_terminal_reason(
                    session_id,
                    target_command,
                    default_reason="command_no_longer_matches_waiting_prompt",
                ),
                status=self.stale_command_terminal_state(session_id, target_command),
            )
            return {
                "status": "stale",
                "reason": "command_no_longer_matches_waiting_prompt",
                "processed_command_seq": target_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": target_seq,
            }

        pending_seq = _optional_int(pending.get("seq")) or 0
        if pending_seq != target_seq:
            matching_waiting_command = self._command_recovery.matching_resume_command_for_seq(
                session_id,
                target_seq,
                include_resolved=True,
            )
            if matching_waiting_command is not None:
                self._log_checkpoint_waiting_reprocessing(
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    command=matching_waiting_command,
                )
                return None
            if target_command is None or target_command_type != "decision_submitted":
                return None
            if target_seq > pending_seq:
                log_event(
                    "runtime_command_deferred_pending_precedes_target",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    pending_command_seq=pending_seq,
                    consumer_offset=offset,
                    stage=stage,
                )
                return {
                    "status": "running_elsewhere",
                    "reason": "pending_command_seq_precedes_target",
                    "processed_command_seq": target_seq,
                    "pending_command_seq": pending_seq,
                    "processed_command_consumer": consumer_name,
                    "consumer_offset": offset,
                }
            log_event(
                "runtime_command_pending_changed",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                pending_command_seq=pending_seq,
                consumer_offset=offset,
                stage=stage,
            )
            self.save_rejected_command_offset(
                consumer_name,
                session_id,
                target_seq,
                reason=self.stale_command_terminal_reason(
                    session_id,
                    target_command,
                    default_reason="pending_command_seq_changed",
                ),
                status=self.stale_command_terminal_state(session_id, target_command),
            )
            return {
                "status": "stale",
                "reason": "pending_command_seq_changed",
                "processed_command_seq": target_seq,
                "pending_command_seq": pending_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": target_seq,
            }
        return None

    def mark_command_state(
        self,
        session_id: str,
        command_seq: int | None,
        status: str,
        *,
        reason: str | None = None,
        server_time_ms: int | None = None,
        **extra: Any,
    ) -> None:
        if command_seq is None or self._command_store is None:
            return
        mark = getattr(self._command_store, "mark_command_state", None)
        if not callable(mark):
            return
        try:
            mark(
                session_id,
                int(command_seq),
                str(status),
                reason=reason,
                server_time_ms=server_time_ms if server_time_ms is not None else self._now_ms(),
                **extra,
            )
        except Exception as exc:
            log_event(
                "runtime_command_state_mark_failed",
                session_id=session_id,
                command_seq=command_seq,
                status=status,
                reason=reason,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )

    def save_rejected_command_offset(
        self,
        command_consumer_name: str | None,
        session_id: str,
        command_seq: int | None,
        *,
        reason: str = "rejected",
        status: str = "rejected",
    ) -> None:
        if not command_consumer_name or command_seq is None or self._command_store is None:
            return
        save_offset = getattr(self._command_store, "save_consumer_offset", None)
        if callable(save_offset):
            save_offset(command_consumer_name, session_id, int(command_seq))
        self.mark_command_state(
            session_id,
            command_seq,
            status,
            reason=reason,
            consumer_name=command_consumer_name,
        )

    def stale_command_terminal_state(self, session_id: str, command: dict | None) -> str:
        lifecycle = self._prompt_lifecycle_provider(session_id, command)
        if not isinstance(lifecycle, dict):
            return "rejected"
        reason = str(lifecycle.get("reason") or "").strip()
        state = str(lifecycle.get("state") or "").strip()
        if reason == "superseded":
            return "superseded"
        if state == "expired" or reason in {"prompt_timeout", "orphan_pending_cleanup"}:
            return "expired"
        return "rejected"

    def stale_command_terminal_reason(
        self,
        session_id: str,
        command: dict | None,
        *,
        default_reason: str,
    ) -> str:
        lifecycle = self._prompt_lifecycle_provider(session_id, command)
        if isinstance(lifecycle, dict):
            reason = str(lifecycle.get("reason") or "").strip()
            if reason:
                return reason
        return str(default_reason)

    @staticmethod
    def _log_checkpoint_waiting_reprocessing(
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        consumer_offset: int | None,
        stage: str,
        command: dict,
    ) -> None:
        log_event(
            "runtime_command_checkpoint_waiting_reprocessing",
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            consumer_offset=consumer_offset,
            stage=stage,
            request_id=CommandRecoveryService.command_payload_field(command, "request_id"),
            request_type=CommandRecoveryService.command_payload_field(command, "request_type"),
            module_id=CommandRecoveryService.command_payload_field(command, "module_id"),
        )


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
