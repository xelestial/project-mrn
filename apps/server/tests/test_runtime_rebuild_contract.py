from __future__ import annotations

import unittest

from apps.server.src.routes import stream
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import RuntimeService


class _SessionService:
    def list_sessions(self) -> list:
        return []


class _CommandStore:
    def __init__(self, commands: list[dict]) -> None:
        self.commands = commands
        self.offsets: dict[tuple[str, str], int] = {}
        self.states: list[dict] = []

    def list_commands(self, session_id: str) -> list[dict]:
        return [dict(command) for command in self.commands if command["session_id"] == session_id]

    def load_consumer_offset(self, consumer_name: str, session_id: str) -> int:
        return self.offsets.get((consumer_name, session_id), 0)

    def save_consumer_offset(self, consumer_name: str, session_id: str, seq: int) -> None:
        self.offsets[(consumer_name, session_id)] = int(seq)

    def mark_command_state(self, session_id: str, seq: int, status: str, **extra) -> dict:
        state = {"session_id": session_id, "seq": int(seq), "status": status, **extra}
        self.states.append(state)
        return state


class RuntimeRebuildContractTests(unittest.TestCase):
    def test_decision_acceptance_is_not_gated_by_view_commit(self) -> None:
        service = PromptService()
        service.create_prompt(
            "session_1",
            {
                "request_id": "req_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 5000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        accepted = service.submit_decision(
            {
                "session_id": "session_1",
                "request_id": "req_1",
                "player_id": 1,
                "choice_id": "roll",
                "choice_payload": {},
            }
        )

        self.assertEqual(accepted["status"], "accepted")
        self.assertIsNone(accepted["reason"])

    def test_missing_pending_prompt_is_not_repaired_from_view_commit(self) -> None:
        service = PromptService()

        stale = service.submit_decision(
            {
                "session_id": "session_1",
                "request_id": "req_missing",
                "player_id": 1,
                "choice_id": "roll",
                "choice_payload": {},
                "view_commit_seq_seen": 12,
            }
        )

        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["reason"], "request_not_pending")

    def test_route_has_no_view_commit_decision_or_heartbeat_repair_helpers(self) -> None:
        self.assertFalse(hasattr(stream, "_decision_view_commit_rejection_reason"))
        self.assertFalse(hasattr(stream, "_repair_missing_pending_prompt_from_view_commit"))
        self.assertFalse(hasattr(stream, "_should_send_heartbeat_view_commit"))

    def test_stale_command_from_superseded_prompt_is_marked_superseded(self) -> None:
        prompt_service = PromptService()
        prompt_service.create_prompt(
            "s1",
            {"request_id": "r1", "request_type": "movement", "player_id": 1, "timeout_ms": 30000},
        )
        prompt_service.create_prompt(
            "s1",
            {"request_id": "r2", "request_type": "movement", "player_id": 1, "timeout_ms": 30000},
        )
        command_store = _CommandStore(
            [
                {
                    "seq": 1,
                    "type": "decision_submitted",
                    "session_id": "s1",
                    "payload": {"request_id": "r1", "player_id": 1, "choice_id": "roll"},
                }
            ]
        )
        service = RuntimeService(_SessionService(), None, prompt_service=prompt_service, command_store=command_store)

        result = service._command_processing_guard(
            session_id="s1",
            consumer_name="runtime",
            command_seq=1,
            stage="test",
        )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(command_store.states[-1]["status"], "superseded")
        self.assertEqual(command_store.states[-1]["reason"], "superseded")

    def test_stale_command_from_expired_prompt_is_marked_expired(self) -> None:
        prompt_service = PromptService()
        prompt_service.create_prompt(
            "s1",
            {"request_id": "r1", "request_type": "movement", "player_id": 1, "timeout_ms": 30000},
        )
        prompt_service.expire_prompt("r1", reason="prompt_timeout", session_id="s1")
        command_store = _CommandStore(
            [
                {
                    "seq": 1,
                    "type": "decision_submitted",
                    "session_id": "s1",
                    "payload": {"request_id": "r1", "player_id": 1, "choice_id": "roll"},
                }
            ]
        )
        service = RuntimeService(_SessionService(), None, prompt_service=prompt_service, command_store=command_store)

        result = service._command_processing_guard(
            session_id="s1",
            consumer_name="runtime",
            command_seq=1,
            stage="test",
        )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(command_store.states[-1]["status"], "expired")
        self.assertEqual(command_store.states[-1]["reason"], "prompt_timeout")
