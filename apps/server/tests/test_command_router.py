from __future__ import annotations

import unittest

from apps.server.src.services.command_router import CommandRouter


class CommandRouterTests(unittest.TestCase):
    def test_wake_requires_accepted_command_reference(self) -> None:
        router = CommandRouter(session_loop_manager=_SessionLoopManager())

        result = router.wake_after_accept(
            command_ref={"status": "rejected", "session_id": "sess_router", "command_seq": 3},
            session_id="sess_router",
            trigger="test",
        )

        self.assertEqual(result, {"status": "skipped", "reason": "command_not_accepted"})

    def test_wake_rejects_session_mismatch(self) -> None:
        router = CommandRouter(session_loop_manager=_SessionLoopManager())

        result = router.wake_after_accept(
            command_ref={"status": "accepted", "session_id": "other", "command_seq": 3},
            session_id="sess_router",
            trigger="test",
        )

        self.assertEqual(result, {"status": "skipped", "reason": "session_mismatch", "command_seq": 3})

    def test_wake_skips_when_session_loop_manager_missing(self) -> None:
        router = CommandRouter()

        result = router.wake_after_accept(
            command_ref={"status": "accepted", "session_id": "sess_router", "command_seq": 11},
            session_id="sess_router",
            trigger="test_accept",
        )

        self.assertEqual(
            result,
            {"status": "skipped", "reason": "missing_session_loop_manager", "command_seq": 11},
        )

    def test_wake_delegates_to_session_loop_manager_when_present(self) -> None:
        manager = _SessionLoopManager()
        router = CommandRouter(
            session_loop_manager=manager,
        )

        result = router.wake_after_accept(
            command_ref={"status": "accepted", "session_id": "sess_router", "command_seq": 14},
            session_id="sess_router",
            trigger="manager",
        )

        self.assertEqual(result, {"status": "scheduled", "command_seq": 14})
        self.assertEqual(
            manager.wakes,
            [("sess_router", {"status": "accepted", "session_id": "sess_router", "command_seq": 14}, "manager")],
        )


class _SessionLoopManager:
    def __init__(self) -> None:
        self.wakes: list[tuple[str, dict, str]] = []

    def wake(self, *, session_id: str, command_ref: dict, trigger: str) -> dict:
        self.wakes.append((session_id, command_ref, trigger))
        return {"status": "scheduled", "command_seq": int(command_ref["command_seq"])}


if __name__ == "__main__":
    unittest.main()
