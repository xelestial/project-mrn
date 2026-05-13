from __future__ import annotations

import unittest

from apps.server.src.services.command_execution_gate import CommandExecutionGate


class CommandExecutionGateTests(unittest.TestCase):
    def test_begin_rejects_second_active_command_for_session(self) -> None:
        gate = CommandExecutionGate(runtime_task_provider=lambda _session_id: None)

        self.assertTrue(gate.begin("sess_1"))
        self.assertFalse(gate.begin("sess_1"))
        self.assertTrue(gate.active("sess_1"))

        gate.end("sess_1")

        self.assertFalse(gate.active("sess_1"))
        self.assertTrue(gate.begin("sess_1"))

    def test_runtime_task_guard_defers_when_task_is_active(self) -> None:
        tasks = {"sess_1": _TaskStub(done=False)}
        gate = CommandExecutionGate(runtime_task_provider=lambda session_id: tasks.get(session_id))

        result = gate.runtime_task_guard(
            session_id="sess_1",
            command_seq=9,
            consumer_name="runtime_wakeup",
            stage="before_begin",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "running_elsewhere")
        self.assertEqual(result["reason"], "runtime_task_already_active")
        self.assertEqual(result["processed_command_seq"], 9)

    def test_runtime_task_guard_allows_when_task_is_done(self) -> None:
        tasks = {"sess_1": _TaskStub(done=True)}
        gate = CommandExecutionGate(runtime_task_provider=lambda session_id: tasks.get(session_id))

        self.assertIsNone(
            gate.runtime_task_guard(
                session_id="sess_1",
                command_seq=9,
                consumer_name="runtime_wakeup",
                stage="before_begin",
            )
        )


class _TaskStub:
    def __init__(self, *, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done
