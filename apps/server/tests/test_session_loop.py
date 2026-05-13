from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.persistence import RedisSessionStore
from apps.server.src.services.realtime_persistence import RedisCommandStore
from apps.server.src.services.session_loop import SessionLoop
from apps.server.src.services.session_loop_manager import SessionLoopManager
from apps.server.src.services.session_service import SessionService
from apps.server.tests.test_redis_realtime_services import _FakeRedis


class SessionLoopTests(unittest.TestCase):
    def test_session_loop_has_no_runtime_process_command_fallback(self) -> None:
        source = Path("apps/server/src/services/session_loop.py").read_text(encoding="utf-8")

        self.assertNotIn("self._runtime_service.process_command_once", source)

    def test_session_loop_processes_decision_command_through_runtime_boundary(self) -> None:
        command_store, sessions, session = _build_session(seed=31)
        runtime = _RuntimeBoundaryStub(command_store=command_store)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_1", "choice_id": "roll"},
            request_id="req_loop_1",
        )

        result = asyncio.run(loop.run_until_idle(session_id=session.session_id, trigger="test", max_commands=2))

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 31, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_session_loop_owns_command_lifecycle_without_runtime_process_adapter(self) -> None:
        command_store, sessions, session = _build_session(seed=37)
        runtime = _RuntimeLifecycleBoundaryStub(command_store=command_store)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_lifecycle", "choice_id": "roll"},
            request_id="req_loop_lifecycle",
        )

        result = asyncio.run(loop.run_until_idle(session_id=session.session_id, trigger="test", max_commands=2))

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(
            runtime.calls,
            [
                "runtime_guard:before_begin",
                "begin_processing",
                "runtime_guard:after_begin",
                "command_guard:before_lease",
                "acquire_lease",
                "start_renewer",
                "command_guard:after_lease",
                "mark_processing_started",
                "run_command_boundary",
                "record_timing",
                "apply_result",
                "stop_renewer",
                "release_lease",
                "end_processing",
            ],
        )
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_session_loop_observes_resolved_commands_before_decision_commands(self) -> None:
        command_store, sessions, session = _build_session(seed=32)
        runtime = _RuntimeBoundaryStub(command_store=command_store)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        command_store.append_command(
            session.session_id,
            "decision_resolved",
            {"request_id": "req_observed", "choice_id": "roll"},
            request_id="req_observed",
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_2", "choice_id": "roll"},
            request_id="req_loop_2",
        )

        result = asyncio.run(loop.run_until_idle(session_id=session.session_id, trigger="test", max_commands=3))

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["observed_count"], 1)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(runtime.processed, [(session.session_id, 2, "runtime_wakeup", 32, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 2)

    def test_session_loop_stops_when_runtime_does_not_advance_offset(self) -> None:
        command_store, sessions, session = _build_session(seed=33)
        runtime = _RuntimeBoundaryStub(command_store=command_store, advance_offset=False)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_blocked", "choice_id": "roll"},
            request_id="req_loop_blocked",
        )

        result = asyncio.run(loop.run_until_idle(session_id=session.session_id, trigger="test", max_commands=2))

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "consumer_offset_not_advanced")
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 33, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 0)

    def test_session_loop_manager_dedupes_session_wakeups(self) -> None:
        command_store, sessions, session = _build_session(seed=34)
        started = asyncio.Event()
        release = asyncio.Event()
        runtime = _RuntimeBoundaryStub(command_store=command_store, started=started, release=release)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        manager = SessionLoopManager(session_loop=loop)
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_dedupe", "choice_id": "roll"},
            request_id="req_loop_dedupe",
        )

        async def _scenario() -> None:
            first = manager.wake(
                session_id=session.session_id,
                command_ref={"session_id": session.session_id, "command_seq": 1},
                trigger="first",
            )
            await asyncio.wait_for(started.wait(), timeout=0.1)
            second = manager.wake(
                session_id=session.session_id,
                command_ref={"session_id": session.session_id, "command_seq": 1},
                trigger="second",
            )
            self.assertEqual(first, {"status": "scheduled", "command_seq": 1})
            self.assertEqual(second, {"status": "deduped", "command_seq": 1})
            release.set()
            for _ in range(20):
                if command_store.load_consumer_offset("runtime_wakeup", session.session_id) == 1:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("session loop manager did not finish")

        asyncio.run(_scenario())
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 34, None)])

    def test_session_loop_manager_retries_deferred_runtime(self) -> None:
        command_store, sessions, session = _build_session(seed=35)
        runtime = _RuntimeBoundaryStub(
            command_store=command_store,
            results=[{"status": "running_elsewhere", "reason": "lease_held"}, {"status": "committed"}],
        )
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        manager = SessionLoopManager(session_loop=loop, retry_delay_sec=0.001, retry_deadline_sec=0.1)
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_loop_retry", "choice_id": "roll"},
            request_id="req_loop_retry",
        )

        async def _scenario() -> None:
            manager.wake(
                session_id=session.session_id,
                command_ref={"session_id": session.session_id, "command_seq": 1},
                trigger="retry",
            )
            for _ in range(20):
                if len(runtime.processed) >= 2:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("session loop manager did not retry deferred runtime")

        asyncio.run(_scenario())
        self.assertEqual([call[1] for call in runtime.processed], [1, 1])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_session_loop_manager_continues_after_yielded_command_budget(self) -> None:
        command_store, sessions, session = _build_session(seed=36)
        runtime = _RuntimeBoundaryStub(command_store=command_store)
        loop = SessionLoop(command_store=command_store, session_service=sessions, runtime_service=runtime)
        manager = SessionLoopManager(
            session_loop=loop,
            retry_delay_sec=0.001,
            retry_deadline_sec=0.1,
            max_commands_per_wakeup=1,
        )
        for command_seq in range(1, 4):
            request_id = f"req_loop_yield_{command_seq}"
            command_store.append_command(
                session.session_id,
                "decision_submitted",
                {"request_id": request_id, "choice_id": "roll"},
                request_id=request_id,
            )

        async def _scenario() -> None:
            manager.wake(
                session_id=session.session_id,
                command_ref={"session_id": session.session_id, "command_seq": 1},
                trigger="yield-budget",
            )
            for _ in range(30):
                if command_store.load_consumer_offset("runtime_wakeup", session.session_id) == 3:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("session loop manager stopped after yielded command budget")

        asyncio.run(_scenario())
        self.assertEqual([call[1] for call in runtime.processed], [1, 2, 3])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 3)


def _build_session(*, seed: int) -> tuple[RedisCommandStore, SessionService, object]:
    connection = RedisConnection(
        RedisConnectionSettings(
            url="redis://127.0.0.1:6379/10",
            key_prefix=f"mrn-session-loop-{seed}",
            socket_timeout_ms=250,
        ),
        client_factory=_FakeRedis,
    )
    command_store = RedisCommandStore(connection)
    sessions = SessionService(session_store=RedisSessionStore(connection), restart_recovery_policy="keep")
    session = sessions.create_session(
        seats=[
            {"seat": 1, "seat_type": "human"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        config={"seed": seed},
    )
    sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
    sessions.start_session(session.session_id, session.host_token)
    return command_store, sessions, session


class _RuntimeBoundaryStub:
    def __init__(
        self,
        *,
        command_store: RedisCommandStore,
        advance_offset: bool = True,
        started: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        results: list[dict] | None = None,
    ) -> None:
        self._command_store = command_store
        self._advance_offset = advance_offset
        self._started = started
        self._release = release
        self._results = list(results or [{"status": "committed"}])
        self.processed: list[tuple[str, int, str, int, str | None]] = []

    def runtime_task_processing_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        return None

    def begin_command_processing(self, session_id: str) -> bool:
        return True

    def command_processing_guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        return None

    def acquire_runtime_lease(self, session_id: str) -> bool:
        return True

    def runtime_lease_owner(self, session_id: str) -> str | None:
        return None

    def start_runtime_lease_renewer(
        self,
        *,
        session_id: str,
        reason: str,
        command_seq: int | None = None,
        consumer_name: str | None = None,
    ) -> object:
        return object()

    def stop_runtime_lease_renewer(self, handle: object) -> None:
        return None

    def release_runtime_lease(self, session_id: str) -> bool:
        return True

    def end_command_processing(self, session_id: str) -> None:
        return None

    def mark_command_processing_started(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
    ) -> None:
        return None

    async def run_command_boundary(
        self,
        *,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        consumer_name: str,
        command_seq: int,
    ) -> dict:
        if self._started is not None:
            self._started.set()
        if self._release is not None:
            await self._release.wait()
        self.processed.append((session_id, command_seq, consumer_name, seed, policy_mode))
        result = self._results.pop(0) if self._results else {"status": "committed"}
        if self._advance_offset and str(result.get("status") or "") != "running_elsewhere":
            self._command_store.save_consumer_offset(consumer_name, session_id, command_seq)
        return {**result, "processed_command_seq": command_seq}

    def record_command_process_timing(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        result: dict,
        process_started: float,
        pre_executor_ms: int,
        executor_wall_ms: int,
    ) -> None:
        return None

    async def apply_command_process_result(
        self,
        *,
        session_id: str,
        result: dict,
    ) -> None:
        return None

    async def handle_command_commit_conflict(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        exc: Exception,
    ) -> dict:
        raise exc

    def handle_command_failure(self, *, session_id: str, exc: Exception) -> None:
        raise exc


class _RuntimeLifecycleBoundaryStub:
    def __init__(self, *, command_store: RedisCommandStore) -> None:
        self._command_store = command_store
        self.calls: list[str] = []

    def runtime_task_processing_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        self.calls.append(f"runtime_guard:{stage}")
        return None

    def begin_command_processing(self, session_id: str) -> bool:
        self.calls.append("begin_processing")
        return True

    def command_processing_guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        self.calls.append(f"command_guard:{stage}")
        return None

    def acquire_runtime_lease(self, session_id: str) -> bool:
        self.calls.append("acquire_lease")
        return True

    def runtime_lease_owner(self, session_id: str) -> str | None:
        return None

    def start_runtime_lease_renewer(
        self,
        *,
        session_id: str,
        reason: str,
        command_seq: int | None = None,
        consumer_name: str | None = None,
    ) -> object:
        self.calls.append("start_renewer")
        return object()

    def stop_runtime_lease_renewer(self, handle: object) -> None:
        self.calls.append("stop_renewer")

    def release_runtime_lease(self, session_id: str) -> bool:
        self.calls.append("release_lease")
        return True

    def end_command_processing(self, session_id: str) -> None:
        self.calls.append("end_processing")

    def mark_command_processing_started(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
    ) -> None:
        self.calls.append("mark_processing_started")

    async def run_command_boundary(
        self,
        *,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        consumer_name: str,
        command_seq: int,
    ) -> dict:
        self.calls.append("run_command_boundary")
        self._command_store.save_consumer_offset(consumer_name, session_id, command_seq)
        return {"status": "committed", "processed_command_seq": command_seq}

    def record_command_process_timing(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        result: dict,
        process_started: float,
        pre_executor_ms: int,
        executor_wall_ms: int,
    ) -> None:
        self.calls.append("record_timing")

    async def apply_command_process_result(
        self,
        *,
        session_id: str,
        result: dict,
    ) -> None:
        self.calls.append("apply_result")

    async def handle_command_commit_conflict(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        exc: Exception,
    ) -> dict:
        raise exc

    def handle_command_failure(self, *, session_id: str, exc: Exception) -> None:
        raise exc


if __name__ == "__main__":
    unittest.main()
