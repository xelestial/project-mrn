from __future__ import annotations

import unittest

from apps.server.src.services.command_recovery import CommandRecoveryService


class CommandRecoveryServiceTests(unittest.TestCase):
    def test_has_unprocessed_runtime_commands_checks_consumer_offset(self) -> None:
        command_store = _CommandStoreStub(
            offset=1,
            commands=[
                {"seq": 1, "type": "decision_submitted"},
                {"seq": 2, "type": "decision_resolved"},
            ],
        )
        service = CommandRecoveryService(
            command_store=command_store,
            checkpoint_provider=lambda _session_id: None,
        )

        self.assertTrue(service.has_unprocessed_runtime_commands("sess_pending"))

        command_store.offset = 2

        self.assertFalse(service.has_unprocessed_runtime_commands("sess_pending"))

    def test_pending_resume_command_returns_unconsumed_matching_command(self) -> None:
        request_id = "sess_1:r1:t1:p1:final_character:1"
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "choice_id": "mansin",
                        "frame_id": "turn:1:p0",
                        "module_id": "mod:turn:1:p0:draft",
                        "module_type": "DraftModule",
                        "module_cursor": "final_character:1",
                    },
                }
            ],
        )
        service = CommandRecoveryService(
            command_store=command_store,
            checkpoint_provider=lambda _session_id: {
                "available": True,
                "checkpoint": {
                    "waiting_prompt_request_id": request_id,
                    "active_frame_id": "turn:1:p0",
                    "active_module_id": "mod:turn:1:p0:draft",
                    "active_module_type": "DraftModule",
                    "active_module_cursor": "final_character:1",
                },
                "current_state": {},
            },
        )

        command = service.pending_resume_command("sess_1")

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["seq"], 7)

    def test_matching_resume_command_for_seq_ignores_module_identity_mismatch(self) -> None:
        request_id = "sess_1:r1:t1:p1:final_character:1"
        command_store = _CommandStoreStub(
            offset=6,
            commands=[
                {
                    "seq": 7,
                    "type": "decision_submitted",
                    "payload": {
                        "request_id": request_id,
                        "frame_id": "turn:1:p0",
                        "module_id": "mod:turn:1:p0:draft",
                    },
                }
            ],
        )
        service = CommandRecoveryService(
            command_store=command_store,
            checkpoint_provider=lambda _session_id: {
                "available": True,
                "checkpoint": {
                    "waiting_prompt_request_id": request_id,
                    "active_frame_id": "turn:1:p0",
                    "active_module_id": "mod:turn:2:p0:draft",
                },
                "current_state": {},
            },
        )

        self.assertIsNone(service.pending_resume_command("sess_1"))
        self.assertIsNone(service.matching_resume_command_for_seq("sess_1", 7, include_resolved=True))


class _CommandStoreStub:
    def __init__(self, *, offset: int, commands: list[dict]) -> None:
        self.offset = offset
        self.commands = commands

    def load_consumer_offset(self, consumer_name: str, session_id: str) -> int:
        del consumer_name, session_id
        return self.offset

    def list_commands(self, session_id: str) -> list[dict]:
        del session_id
        return list(self.commands)
