from __future__ import annotations

import asyncio
import unittest

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.persistence import RedisSessionStore
from apps.server.src.services.realtime_persistence import RedisCommandStore
from apps.server.src.services.session_loop import SessionLoop
from apps.server.src.services.session_loop_manager import SessionLoopManager
from apps.server.src.services.session_service import SessionService
from apps.server.tests.test_redis_realtime_services import _FakeRedis


class SessionLoopTests(unittest.TestCase):
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

    async def process_command_once(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        seed: int,
        policy_mode: str | None = None,
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


if __name__ == "__main__":
    unittest.main()
