from __future__ import annotations

import unittest

from apps.server.src.services.command_processing_guard import CommandProcessingGuardService
from apps.server.src.services.command_recovery import CommandRecoveryService


class CommandProcessingGuardServiceTests(unittest.TestCase):
    def test_guard_skips_already_consumed_command(self) -> None:
        command_store = _CommandStoreStub(offset=7, commands=[{"seq": 7, "type": "decision_submitted"}])
        service = _guard_service(command_store, checkpoint_provider=lambda _session_id: None)

        result = service.guard(
            session_id="sess_1",
            consumer_name="runtime_wakeup",
            command_seq=7,
            stage="before_lease",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "already_processed")
        self.assertEqual(result["consumer_offset"], 7)
        self.assertEqual(command_store.offset, 7)

    def test_guard_marks_stale_command_when_it_no_longer_matches_waiting_prompt(self) -> None:
        command_store = _CommandStoreStub(
            offset=6,
            commands=[{"seq": 7, "type": "decision_submitted", "payload": {"request_id": "old_request"}}],
        )
        service = _guard_service(
            command_store,
            checkpoint_provider=lambda _session_id: {
                "available": True,
                "checkpoint": {"waiting_prompt_request_id": "new_request"},
                "current_state": {},
            },
        )

        result = service.guard(
            session_id="sess_1",
            consumer_name="runtime_wakeup",
            command_seq=7,
            stage="before_lease",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "command_no_longer_matches_waiting_prompt")
        self.assertEqual(command_store.offset, 7)
        self.assertEqual(command_store.marked_states[-1]["status"], "rejected")
        self.assertEqual(command_store.marked_states[-1]["reason"], "command_no_longer_matches_waiting_prompt")

    def test_guard_defers_newer_command_until_earlier_pending_is_consumed(self) -> None:
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {"seq": 7, "type": "decision_submitted", "payload": {"request_id": "current_request"}},
                {"seq": 8, "type": "decision_submitted", "payload": {"request_id": "next_request"}},
            ],
        )
        service = _guard_service(
            command_store,
            checkpoint_provider=lambda _session_id: {
                "available": True,
                "checkpoint": {"waiting_prompt_request_id": "current_request"},
                "current_state": {},
            },
        )

        result = service.guard(
            session_id="sess_1",
            consumer_name="runtime_wakeup",
            command_seq=8,
            stage="before_lease",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "running_elsewhere")
        self.assertEqual(result["reason"], "pending_command_seq_precedes_target")
        self.assertEqual(result["pending_command_seq"], 7)
        self.assertEqual(command_store.offset, 6)


def _guard_service(
    command_store: "_CommandStoreStub",
    *,
    checkpoint_provider,
) -> CommandProcessingGuardService:
    command_recovery = CommandRecoveryService(
        command_store=command_store,
        checkpoint_provider=checkpoint_provider,
    )
    return CommandProcessingGuardService(
        command_store=command_store,
        command_recovery=command_recovery,
        prompt_lifecycle_provider=lambda _session_id, _command: None,
        now_ms=lambda: 12345,
    )


class _CommandStoreStub:
    def __init__(self, *, offset: int, commands: list[dict]) -> None:
        self.offset = offset
        self.commands = commands
        self.marked_states: list[dict] = []

    def load_consumer_offset(self, consumer_name: str, session_id: str) -> int:
        del consumer_name, session_id
        return self.offset

    def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
        del consumer_name, session_id
        self.offset = max(self.offset, int(seq))

    def list_commands(self, session_id: str) -> list[dict]:
        del session_id
        return list(self.commands)

    def mark_command_state(
        self,
        session_id: str,
        seq: int,
        status: str,
        *,
        reason: str | None = None,
        server_time_ms: int | None = None,
        **extra,
    ) -> None:
        self.marked_states.append(
            {
                "session_id": session_id,
                "seq": seq,
                "status": status,
                "reason": reason,
                "server_time_ms": server_time_ms,
                **extra,
            }
        )
