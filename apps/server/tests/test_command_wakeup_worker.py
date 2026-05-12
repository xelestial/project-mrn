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

    def test_wakeup_worker_skips_command_tail_when_offset_is_current(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-tail",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = _CountingRedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 22},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="waiting_input")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        for seq in range(1, 41):
            command_store.append_command(
                session.session_id,
                "decision_resolved",
                {"request_id": f"req_observation_{seq}", "choice_id": "roll"},
                request_id=f"req_observation_{seq}",
            )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 40)

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(wakeups, [])
        self.assertEqual(command_store.full_list_calls, 0)
        self.assertEqual(command_store.recent_list_calls, 0)
        self.assertEqual(command_store.latest_seq_calls, 1)

    def test_wakeup_worker_throttles_consumed_command_rescan(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-consumed-throttle",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = _CountingRedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 23},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            waiting_request_id="req_missing",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:dice",
            active_module_type="DiceRollModule",
            active_module_cursor="await_turn_prompt",
        )
        now_ms = 1000
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
            consumed_command_rescan_interval_ms=2000,
            monotonic_ms=lambda: now_ms,
        )
        command_store.append_command(
            session.session_id,
            "decision_resolved",
            {"request_id": "req_observation", "choice_id": "roll"},
            request_id="req_observation",
        )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 1)

        first = asyncio.run(worker.run_once(session_id=session.session_id))
        second = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(command_store.recent_list_calls, 1)

        now_ms = 3100
        third = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(third, [])
        self.assertEqual(command_store.recent_list_calls, 2)

    def test_wakeup_worker_reprocesses_consumed_command_when_checkpoint_still_waits(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-consumed-waiting",
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
            config={"seed": 77},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            waiting_request_id="req_active",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:dice",
            active_module_type="DiceRollModule",
            active_module_cursor="await_turn_prompt",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": "req_active",
                "choice_id": "roll",
                "frame_id": "turn:1:p0",
                "module_id": "mod:turn:1:p0:dice",
                "module_type": "DiceRollModule",
                "module_cursor": "await_turn_prompt",
            },
            request_id="req_active",
        )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 1)

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], 1)
        self.assertTrue(wakeups[0]["reprocessed_consumed"])
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 77, None)])

    def test_wakeup_worker_reprocesses_consumed_waiting_command_only_once(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-consumed-waiting-once",
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
            config={"seed": 76},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            status_after_process="waiting_input",
            waiting_request_id="req_active",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:dice",
            active_module_type="DiceRollModule",
            active_module_cursor="await_turn_prompt",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": "req_active",
                "choice_id": "roll",
                "frame_id": "turn:1:p0",
                "module_id": "mod:turn:1:p0:dice",
                "module_type": "DiceRollModule",
                "module_cursor": "await_turn_prompt",
            },
            request_id="req_active",
        )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 1)

        first = asyncio.run(worker.run_once(session_id=session.session_id))
        second = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]["reprocessed_consumed"])
        self.assertEqual(second, [])
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 76, None)])

    def test_wakeup_worker_does_not_reprocess_consumed_command_for_stale_module(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-consumed-stale-module",
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
            config={"seed": 78},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            waiting_request_id="req_active",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:dice",
            active_module_type="DiceRollModule",
            active_module_cursor="await_turn_prompt",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": "req_active",
                "choice_id": "roll",
                "frame_id": "turn:1:p0",
                "module_id": "mod:turn:1:p0:dice",
                "module_type": "DiceRollModule",
                "module_cursor": "old_cursor",
            },
            request_id="req_active",
        )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 1)

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(wakeups, [])
        self.assertEqual(runtime.processed, [])

    def test_wakeup_worker_reprocesses_consumed_batch_command_when_checkpoint_still_waits(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-consumed-batch",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 79},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        sessions.start_session(session.session_id, session.host_token)
        request_id = "batch:simul:resupply:1:81:mod:simul:resupply:1:81:resupply:1:p0"
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            active_frame_id="simul:resupply:1:81",
            active_module_id="mod:simul:resupply:1:81:resupply",
            active_module_type="ResupplyModule",
            active_module_cursor="await_resupply_batch:1",
            active_prompt_batch={
                "batch_id": "batch:simul:resupply:1:81",
                "request_type": "burden_exchange",
                "missing_player_ids": [0],
                "prompts_by_player_id": {
                    "0": {
                        "request_id": request_id,
                        "frame_id": "simul:resupply:1:81",
                        "module_id": "mod:simul:resupply:1:81:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    }
                },
            },
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": request_id,
                "choice_id": "yes",
                "frame_id": "simul:resupply:1:81",
                "module_id": "mod:simul:resupply:1:81:resupply",
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:1",
            },
            request_id=request_id,
        )
        command_store.save_consumer_offset("runtime_wakeup", session.session_id, 1)

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], 1)
        self.assertTrue(wakeups[0]["reprocessed_consumed"])
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 79, None)])

    def test_wakeup_worker_skips_non_missing_batch_command_and_processes_missing_one(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-stale-batch",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        command_store = RedisCommandStore(connection)
        sessions = SessionService(restart_recovery_policy="keep")
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "human"},
            ],
            config={"seed": 80},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.join_session(session.session_id, 2, session.join_tokens[2], "P2")
        sessions.start_session(session.session_id, session.host_token)
        missing_request_id = "batch:simul:resupply:1:81:mod:simul:resupply:1:81:resupply:1:p0"
        already_answered_request_id = "batch:simul:resupply:1:81:mod:simul:resupply:1:81:resupply:1:p1"
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            active_frame_id="simul:resupply:1:81",
            active_module_id="mod:simul:resupply:1:81:resupply",
            active_module_type="ResupplyModule",
            active_module_cursor="await_resupply_batch:1",
            active_prompt_batch={
                "batch_id": "batch:simul:resupply:1:81",
                "request_type": "burden_exchange",
                "missing_player_ids": [0],
                "prompts_by_player_id": {
                    "0": {
                        "request_id": missing_request_id,
                        "frame_id": "simul:resupply:1:81",
                        "module_id": "mod:simul:resupply:1:81:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    },
                    "1": {
                        "request_id": already_answered_request_id,
                        "frame_id": "simul:resupply:1:81",
                        "module_id": "mod:simul:resupply:1:81:resupply",
                        "module_type": "ResupplyModule",
                        "module_cursor": "await_resupply_batch:1",
                    },
                },
            },
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": already_answered_request_id,
                "choice_id": "yes",
                "frame_id": "simul:resupply:1:81",
                "module_id": "mod:simul:resupply:1:81:resupply",
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:1",
            },
            request_id=already_answered_request_id,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": missing_request_id,
                "choice_id": "yes",
                "frame_id": "simul:resupply:1:81",
                "module_id": "mod:simul:resupply:1:81:resupply",
                "module_type": "ResupplyModule",
                "module_cursor": "await_resupply_batch:1",
            },
            request_id=missing_request_id,
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], 2)
        self.assertEqual(runtime.processed, [(session.session_id, 2, "runtime_wakeup", 80, None)])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_wakeup_worker_keeps_resume_command_queued_while_runtime_is_running(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-running-decision",
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
            config={"seed": 62},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(status="running")
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {"request_id": "req_running_final", "choice_id": "sandok"},
            request_id="req_running_final",
        )
        command_store.append_command(
            session.session_id,
            "decision_resolved",
            {"request_id": "req_ai_later", "choice_id": "5", "provider": "ai"},
            request_id="req_ai_later",
        )

        first = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(first, [])
        self.assertEqual(runtime.processed, [])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 0)

        runtime.set_status("waiting_input")

        second = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["command_seq"], 1)
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 62, None)])

    def test_wakeup_worker_processes_running_status_when_checkpoint_waits_for_same_prompt(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-running-checkpoint-waiting",
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
            config={"seed": 64},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="running",
            waiting_request_id="req_running_waiting",
            active_frame_id="turn:2:p0",
            active_module_id="mod:turn:2:p0:movement",
            active_module_type="MapMoveModule",
            active_module_cursor="move:await_choice",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": "req_running_waiting",
                "choice_id": "roll",
                "frame_id": "turn:2:p0",
                "module_id": "mod:turn:2:p0:movement",
                "module_type": "MapMoveModule",
                "module_cursor": "move:await_choice",
            },
            request_id="req_running_waiting",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["runtime_status"], "running")
        self.assertEqual(runtime.processed, [(session.session_id, 1, "runtime_wakeup", 64, None)])

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

    def test_wakeup_worker_restart_preserves_stale_submitted_command_until_recovery_resolves_it(self) -> None:
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

    def test_wakeup_worker_skips_matching_request_with_stale_module_cursor(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-stale-module",
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
            config={"seed": 61},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            waiting_request_id="req_active",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:movement",
            active_module_type="MapMoveModule",
            active_module_cursor="move:await_choice",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "request_id": "req_active",
                "choice_id": "roll",
                "frame_id": "turn:1:p0",
                "module_id": "mod:turn:1:p0:movement",
                "module_type": "MapMoveModule",
                "module_cursor": "move:old",
            },
            request_id="req_active",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(wakeups, [])
        self.assertEqual(runtime.processed, [])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

    def test_wakeup_worker_checks_nested_decision_module_identity(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-wakeup-nested-module",
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
            config={"seed": 63},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = _RuntimeProcessStub(
            status="waiting_input",
            waiting_request_id="req_active",
            active_frame_id="turn:1:p0",
            active_module_id="mod:turn:1:p0:movement",
            active_module_type="MapMoveModule",
            active_module_cursor="move:await_choice",
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=runtime,
            poll_interval_ms=50,
        )
        command_store.append_command(
            session.session_id,
            "decision_submitted",
            {
                "decision": {
                    "request_id": "req_active",
                    "choice_id": "roll",
                    "frame_id": "turn:1:p0",
                    "module_id": "mod:turn:1:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:old",
                }
            },
            request_id="req_active",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))

        self.assertEqual(wakeups, [])
        self.assertEqual(runtime.processed, [])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 1)

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
    def __init__(
        self,
        *,
        status: str,
        status_after_process: str = "idle",
        waiting_request_id: str | None = None,
        active_frame_id: str = "",
        active_module_id: str = "",
        active_module_type: str = "",
        active_module_cursor: str = "",
        active_prompt_batch: dict | None = None,
    ) -> None:
        self._status = status
        self._status_after_process = status_after_process
        self._waiting_request_id = waiting_request_id
        self._active_frame_id = active_frame_id
        self._active_module_id = active_module_id
        self._active_module_type = active_module_type
        self._active_module_cursor = active_module_cursor
        self._active_prompt_batch = active_prompt_batch
        self.processed: list[tuple[str, int, str, int, str | None]] = []

    def runtime_status(self, session_id: str) -> dict:
        status = {"status": self._status}
        if self._waiting_request_id or self._active_prompt_batch is not None:
            checkpoint = {
                "active_frame_id": self._active_frame_id,
                "active_module_id": self._active_module_id,
                "active_module_type": self._active_module_type,
                "active_module_cursor": self._active_module_cursor,
            }
            if self._waiting_request_id:
                checkpoint["waiting_prompt_request_id"] = self._waiting_request_id
            if self._active_prompt_batch is not None:
                checkpoint["runtime_active_prompt_batch"] = self._active_prompt_batch
            status["recovery_checkpoint"] = {
                "available": True,
                "checkpoint": checkpoint,
            }
        return status

    def set_status(self, status: str) -> None:
        self._status = status

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
        self._status = self._status_after_process
        return {"status": "committed"}


class _CountingRedisCommandStore(RedisCommandStore):
    def __init__(self, connection: RedisConnection) -> None:
        super().__init__(connection)
        self.full_list_calls = 0
        self.recent_list_calls = 0
        self.latest_seq_calls = 0

    def list_commands(self, session_id: str) -> list[dict]:
        self.full_list_calls += 1
        return super().list_commands(session_id)

    def list_recent_commands(self, session_id: str, *, limit: int = 32) -> list[dict]:
        self.recent_list_calls += 1
        return super().list_recent_commands(session_id, limit=limit)

    def latest_seq(self, session_id: str) -> int:
        self.latest_seq_calls += 1
        return super().latest_seq(session_id)


class _HealthRedis:
    def __init__(self, *, ok: bool) -> None:
        self.ok = ok

    def health_check(self) -> dict[str, object]:
        return {"ok": self.ok, "cluster_hash_tag": "mrn-test", "cluster_hash_tag_valid": True}


if __name__ == "__main__":
    unittest.main()
