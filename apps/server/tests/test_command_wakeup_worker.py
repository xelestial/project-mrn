from __future__ import annotations

import asyncio
import unittest

from apps.server.src.services.command_wakeup_worker import CommandStreamWakeupWorker
from apps.server.src.workers.command_wakeup_worker_app import build_parser
from apps.server.src.services.realtime_persistence import RedisCommandStore
from apps.server.tests.test_redis_realtime_services import _FakeRedis
from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.session_service import SessionService


class CommandStreamWakeupWorkerTests(unittest.TestCase):
    def test_wakeup_worker_starts_recoverable_runtime_once_per_command(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-wakeup", socket_timeout_ms=250),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 99},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeStub(status="recovery_required")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_wakeup_1", "choice_id": "roll"},
            request_id="req_wakeup_1",
        )

        first = asyncio.run(worker.run_once())
        second = asyncio.run(worker.run_once())

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["command_seq"], 1)
        self.assertEqual(second, [])
        self.assertEqual(runtime.started, [(session.session_id, 99, None)])

        restarted_worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        self.assertEqual(asyncio.run(restarted_worker.run_once()), [])

    def test_wakeup_worker_restarts_waiting_input_runtime_after_decision_command(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-wakeup-waiting", socket_timeout_ms=250),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 13},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeStub(status="waiting_input")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_waiting_1", "choice_id": "roll"},
            request_id="req_waiting_1",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["runtime_status"], "waiting_input")
        self.assertEqual(runtime.started, [(session.session_id, 13, None)])

    def test_wakeup_worker_prefers_command_processing_hook_before_offset(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-wakeup-process", socket_timeout_ms=250),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 21},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="waiting_input")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_process_1", "choice_id": "roll"},
            request_id="req_process_1",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 21, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 0)

    def test_cli_parser_supports_once_mode(self) -> None:
        args = build_parser().parse_args(["--once", "--session-id", "sess_1", "--max-iterations", "2"])

        self.assertTrue(args.once)
        self.assertEqual(args.session_id, "sess_1")
        self.assertEqual(args.max_iterations, 2)


class _RuntimeStub:
    def __init__(self, *, status: str) -> None:
        self._status = status
        self.started: list[tuple[str, int, str | None]] = []

    def runtime_status(self, session_id: str) -> dict:
        return {"status": self._status}

    async def start_runtime(self, *, session_id: str, seed: int, policy_mode: str | None = None) -> None:
        self.started.append((session_id, seed, policy_mode))
        self._status = "running"


class _RuntimeProcessStub:
    def __init__(self, *, status: str) -> None:
        self._status = status
        self.processed: list[tuple[str, int, str, int, str | None]] = []

    def runtime_status(self, session_id: str) -> dict:
        return {"status": self._status}

    async def process_command_once(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        seed: int,
        policy_mode: str | None = None,
    ) -> dict:
        self.processed.append((session_id, command_seq, consumer_name, seed, policy_mode))
        self._status = "idle"
        return {"status": "committed"}


if __name__ == "__main__":
    unittest.main()
