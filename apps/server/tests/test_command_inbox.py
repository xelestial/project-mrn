from __future__ import annotations

import unittest

from apps.server.src.services.command_inbox import CommandInbox
from apps.server.src.services.prompt_service import PromptService


class _CommandStore:
    def __init__(self) -> None:
        self.commands: list[dict] = []

    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict,
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> dict:
        command = {
            "stream_id": f"{len(self.commands) + 1}-0",
            "seq": len(self.commands) + 1,
            "type": command_type,
            "session_id": session_id,
            "server_time_ms": int(server_time_ms or 0),
            "payload": dict(payload),
            "request_id": request_id,
        }
        self.commands.append(command)
        return command


class _FailingCommandStore:
    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict,
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> None:
        return None


class _LuaMissingCommandStore:
    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict,
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> None:
        raise RuntimeError("redis_lua_required")


class _AtomicPromptStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def accept_decision_with_command(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        command_store = kwargs["command_store"]
        return command_store.append_command(
            kwargs["session_id"],
            kwargs["command_type"],
            kwargs["command_payload"],
            request_id=kwargs["request_id"],
            server_time_ms=kwargs["server_time_ms"],
        )


class CommandInboxTests(unittest.TestCase):
    def test_accept_prompt_decision_writes_durable_command_before_returning_reference(self) -> None:
        command_store = _CommandStore()
        prompt_store = _AtomicPromptStore()
        inbox = CommandInbox(command_store=command_store)

        accepted = inbox.accept_prompt_decision(
            prompt_store=prompt_store,
            session_id="s1",
            request_id="r1",
            decision_payload={"request_id": "r1", "choice_id": "roll"},
            resolved_payload={"request_id": "r1", "reason": "accepted"},
            command_payload={"request_id": "r1", "choice_id": "roll"},
            server_time_ms=123,
        )

        self.assertEqual(len(command_store.commands), 1)
        self.assertEqual(accepted["seq"], command_store.commands[0]["seq"])
        self.assertEqual(accepted["payload"]["request_id"], "r1")
        self.assertEqual(prompt_store.calls[0]["command_store"], command_store)

    def test_prompt_service_returns_command_seq_from_command_inbox_append(self) -> None:
        command_store = _CommandStore()
        service = PromptService(command_store=command_store)
        service.create_prompt(
            "s1",
            {
                "request_id": "r1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )

        accepted = service.submit_decision(
            {"session_id": "s1", "request_id": "r1", "player_id": 1, "choice_id": "roll"}
        )

        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["command_seq"], command_store.commands[0]["seq"])
        self.assertEqual(command_store.commands[0]["type"], "decision_submitted")

    def test_prompt_service_does_not_accept_when_command_append_fails(self) -> None:
        service = PromptService(command_store=_FailingCommandStore())
        service.create_prompt(
            "s1",
            {
                "request_id": "r1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )

        result = service.submit_decision(
            {"session_id": "s1", "request_id": "r1", "player_id": 1, "choice_id": "roll"}
        )

        self.assertEqual(result, {"status": "stale", "reason": "command_append_failed"})
        self.assertIsNotNone(service.get_pending_prompt("r1", session_id="s1"))

    def test_prompt_service_does_not_accept_when_redis_lua_is_missing(self) -> None:
        service = PromptService(command_store=_LuaMissingCommandStore())
        service.create_prompt(
            "s1",
            {
                "request_id": "r1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )

        result = service.submit_decision(
            {"session_id": "s1", "request_id": "r1", "player_id": 1, "choice_id": "roll"}
        )

        self.assertEqual(result, {"status": "stale", "reason": "command_append_failed"})
        self.assertIsNotNone(service.get_pending_prompt("r1", session_id="s1"))


if __name__ == "__main__":
    unittest.main()
