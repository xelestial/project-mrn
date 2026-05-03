from __future__ import annotations

import asyncio
import unittest

from apps.server.src.services.command_wakeup_worker import CommandStreamWakeupWorker
from apps.server.src.workers.command_wakeup_worker_app import build_parser, health_from_state
from apps.server.src.services.persistence import RedisSessionStore
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

    def test_cli_parser_supports_health_mode(self) -> None:
        args = build_parser().parse_args(["--health", "--once", "--max-iterations", "3"])

        self.assertTrue(args.health)
        self.assertTrue(args.once)
        self.assertEqual(args.max_iterations, 3)

    def test_health_mode_reports_redis_readiness(self) -> None:
        from apps.server.src import state

        original_redis = state.redis_connection
        original_worker = state.command_wakeup_worker
        state.redis_connection = _HealthRedis(ok=True)  # type: ignore[assignment]
        state.command_wakeup_worker = object()  # type: ignore[assignment]
        try:
            payload = health_from_state()
        finally:
            state.redis_connection = original_redis  # type: ignore[assignment]
            state.command_wakeup_worker = original_worker  # type: ignore[assignment]

        self.assertEqual(
            payload,
            {
                "ok": True,
                "role": "command-wakeup-worker",
                "redis": {"ok": True, "cluster_hash_tag": "mrn-test", "cluster_hash_tag_valid": True},
            },
        )

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

    def test_wakeup_worker_skips_waiting_input_commands_for_non_active_prompt(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-stale",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 55},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="waiting_input", waiting_request_id="req_active")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_resolved",
            {"request_id": "req_stale", "choice_id": "dice", "provider": "ai"},
            request_id="req_stale",
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_active", "choice_id": "dice"},
            request_id="req_active",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], 2)
        self.assertEqual(runtime.processed, [(session.session_id, 2, "runtime_wakeup", 55, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_wakeup_worker_restart_skips_stale_waiting_commands_until_active_prompt(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-stale-restart",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 58},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="waiting_input", waiting_request_id="req_active")
        command_store.append_command(
            session.session_id,
            "decision_resolved",
            {"request_id": "req_old_1", "choice_id": "trick", "provider": "ai"},
            request_id="req_old_1",
        )
        first_worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )

        first_wakeups = asyncio.run(first_worker.run_once(session_id=session.session_id))

        self.assertEqual(first_wakeups, [])
        self.assertEqual(runtime.processed, [])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_old_2", "choice_id": "roll"},
            request_id="req_old_2",
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_active", "choice_id": "roll"},
            request_id="req_active",
        )
        restarted_worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )

        wakeups = asyncio.run(restarted_worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], 3)
        self.assertEqual(runtime.processed, [(session.session_id, 3, "runtime_wakeup", 58, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 2)

    def test_wakeup_worker_refreshes_redis_sessions_created_after_start(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-refresh",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        session_store = RedisSessionStore(connection)
        worker_sessions = SessionService(session_store=session_store, restart_recovery_policy="keep")
        backend_sessions = SessionService(session_store=session_store, restart_recovery_policy="keep")
        session = backend_sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 37},
        )
        backend_sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="waiting_input")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=worker_sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_refresh_1", "choice_id": "roll"},
            request_id="req_refresh_1",
        )

        wakeups = asyncio.run(worker.run_once())

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["session_id"], session.session_id)
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 37, None)])

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
    def __init__(self, *, status: str, waiting_request_id: str | None = None) -> None:
        self._status = status
        self._waiting_request_id = waiting_request_id
        self.processed: list[tuple[str, int, str, int, str | None]] = []

    def runtime_status(self, session_id: str) -> dict:
        status = {"status": self._status}
        if self._waiting_request_id:
            status["recovery_checkpoint"] = {
                "available": True,
                "checkpoint": {"waiting_prompt_request_id": self._waiting_request_id},
            }
        return status

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


class _HealthRedis:
    def __init__(self, *, ok: bool) -> None:
        self.ok = ok

    def health_check(self) -> dict[str, object]:
        return {"ok": self.ok, "cluster_hash_tag": "mrn-test", "cluster_hash_tag_valid": True}


if __name__ == "__main__":
    unittest.main()
