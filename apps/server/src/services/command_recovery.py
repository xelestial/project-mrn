from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.server.src.infra.structured_log import log_event


class CommandRecoveryService:
    """Read-side command recovery queries for durable runtime commands."""

    def __init__(
        self,
        *,
        command_store: Any | None,
        checkpoint_provider: Callable[[str], dict | None],
    ) -> None:
        self._command_store = command_store
        self._checkpoint_provider = checkpoint_provider

    def has_unprocessed_runtime_commands(self, session_id: str, consumer_name: str = "runtime_wakeup") -> bool:
        if self._command_store is None:
            return False
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(load_offset) or not callable(list_commands):
            return False
        last_seq = int(load_offset(consumer_name, session_id))
        for command in list_commands(session_id):
            if int(command.get("seq", 0) or 0) > last_seq:
                return True
        return False

    def pending_resume_command(self, session_id: str, consumer_name: str = "runtime_wakeup") -> dict | None:
        if self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        last_consumed_seq = self.load_command_consumer_offset(session_id, consumer_name) or 0
        checkpoint = self._recovery_checkpoint_payload(session_id)
        if checkpoint is None:
            return None
        waiting_request_ids = self.checkpoint_waiting_prompt_request_ids(checkpoint)
        if not waiting_request_ids:
            return None
        commands = self._sorted_commands(session_id)
        resolved_request_ids = {
            self.command_payload_field(command, "request_id")
            for command in commands
            if str(command.get("type") or "").strip() == "decision_resolved"
        }
        for command in commands:
            if str(command.get("type") or "").strip() != "decision_submitted":
                continue
            if int(command.get("seq", 0) or 0) <= last_consumed_seq:
                continue
            request_id = self.command_payload_field(command, "request_id")
            if request_id not in waiting_request_ids:
                continue
            if request_id in resolved_request_ids and not self.command_is_timeout_fallback(command):
                continue
            if self.command_module_identity_mismatch(checkpoint, command):
                continue
            return dict(command)
        return None

    def has_pending_resume_command(self, session_id: str, consumer_name: str = "runtime_wakeup") -> bool:
        return self.pending_resume_command(session_id, consumer_name=consumer_name) is not None

    def command_for_seq(self, session_id: str, command_seq: int) -> dict | None:
        if self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        target_seq = int(command_seq)
        for command in list_commands(session_id):
            if int(command.get("seq", 0) or 0) == target_seq:
                return dict(command)
        return None

    def matching_resume_command_for_seq(
        self,
        session_id: str,
        command_seq: int,
        *,
        include_resolved: bool = False,
    ) -> dict | None:
        checkpoint = self._recovery_checkpoint_payload(session_id)
        if checkpoint is None:
            return None
        waiting_request_ids = self.checkpoint_waiting_prompt_request_ids(checkpoint)
        if not waiting_request_ids:
            return None
        target_seq = int(command_seq)
        commands = self._sorted_commands(session_id)
        resolved_request_ids = {
            self.command_payload_field(command, "request_id")
            for command in commands
            if str(command.get("type") or "").strip() == "decision_resolved"
        }
        for command in commands:
            if int(command.get("seq", 0) or 0) != target_seq:
                continue
            if str(command.get("type") or "").strip() != "decision_submitted":
                return None
            request_id = self.command_payload_field(command, "request_id")
            if request_id not in waiting_request_ids:
                return None
            if not include_resolved and request_id in resolved_request_ids and not self.command_is_timeout_fallback(command):
                return None
            if self.command_module_identity_mismatch(checkpoint, command):
                return None
            return dict(command)
        return None

    def load_command_consumer_offset(self, session_id: str, consumer_name: str) -> int | None:
        if self._command_store is None:
            return None
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        if not callable(load_offset):
            return None
        try:
            return int(load_offset(consumer_name, session_id))
        except Exception as exc:
            log_event(
                "runtime_command_offset_load_failed",
                session_id=session_id,
                consumer_name=consumer_name,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return None

    def _recovery_checkpoint_payload(self, session_id: str) -> dict | None:
        recovery = self._checkpoint_provider(session_id)
        checkpoint = recovery.get("checkpoint") if isinstance(recovery, dict) else None
        return checkpoint if isinstance(checkpoint, dict) else None

    def _sorted_commands(self, session_id: str) -> list[dict]:
        if self._command_store is None:
            return []
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return []
        return sorted(list_commands(session_id), key=lambda command: int(command.get("seq", 0) or 0))

    @staticmethod
    def checkpoint_waiting_prompt_request_ids(checkpoint: dict) -> set[str]:
        request_ids: set[str] = set()
        single_request_id = str(checkpoint.get("waiting_prompt_request_id") or "").strip()
        if single_request_id:
            request_ids.add(single_request_id)

        active_prompt = checkpoint.get("runtime_active_prompt")
        if isinstance(active_prompt, dict):
            active_request_id = str(active_prompt.get("request_id") or "").strip()
            if active_request_id:
                request_ids.add(active_request_id)

        batch = checkpoint.get("runtime_active_prompt_batch")
        if not isinstance(batch, dict):
            return request_ids
        prompts_by_player_id = batch.get("prompts_by_player_id")
        if not isinstance(prompts_by_player_id, dict):
            return request_ids

        missing_filter: set[int] | None = None
        missing_player_ids = batch.get("missing_player_ids")
        if isinstance(missing_player_ids, list):
            missing_filter = set()
            for raw_player_id in missing_player_ids:
                try:
                    missing_filter.add(int(raw_player_id))
                except (TypeError, ValueError):
                    continue

        for raw_player_id, prompt in prompts_by_player_id.items():
            if missing_filter is not None:
                try:
                    internal_player_id = int(raw_player_id)
                except (TypeError, ValueError):
                    continue
                if internal_player_id not in missing_filter:
                    continue
            if isinstance(prompt, dict):
                request_id = str(prompt.get("request_id") or "").strip()
            else:
                request_id = str(getattr(prompt, "request_id", "") or "").strip()
            if request_id:
                request_ids.add(request_id)
        return request_ids

    @staticmethod
    def command_payload(command: dict) -> dict:
        payload = command.get("payload")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def command_payload_field(command: dict, name: str) -> str:
        payload = CommandRecoveryService.command_payload(command)
        decision = payload.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        return str(payload.get(name) or decision.get(name) or "").strip()

    @staticmethod
    def command_is_timeout_fallback(command: dict) -> bool:
        payload = CommandRecoveryService.command_payload(command)
        decision = payload.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        source = str(payload.get("source") or "").strip()
        provider = str(payload.get("provider") or decision.get("provider") or "").strip()
        return source == "timeout_fallback" or provider == "timeout_fallback"

    @staticmethod
    def command_module_identity_mismatch(checkpoint: dict, command: dict) -> bool:
        field_pairs = (
            ("frame_id", "active_frame_id"),
            ("module_id", "active_module_id"),
            ("module_type", "active_module_type"),
            ("module_cursor", "active_module_cursor"),
        )
        for command_field, checkpoint_field in field_pairs:
            command_value = CommandRecoveryService.command_payload_field(command, command_field)
            checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
            if command_value and checkpoint_value and command_value != checkpoint_value:
                return True
        return False
