from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from apps.server.src.services.persistence import JsonFileSessionStore, JsonFileStreamStore
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.realtime_persistence import (
    RedisCommandStore,
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
)
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.tests.test_redis_realtime_services import _FakeRedis


def _seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
    ]


class RestartPersistenceTests(unittest.TestCase):
    def test_session_in_progress_is_aborted_on_restart_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = str(Path(temp_dir) / "session-store.json")
            store = JsonFileSessionStore(session_path)

            first = SessionService(session_store=store)
            created = first.create_session(_seats(), config={"seed": 42})
            first.join_session(created.session_id, 1, created.join_tokens[1], "P1")
            first.start_session(created.session_id, created.host_token)

            second = SessionService(session_store=store)
            restored = second.get_session(created.session_id)
            self.assertEqual(restored.status.value, "aborted")
            self.assertEqual(restored.abort_reason, "server_restart_recovery")
            self.assertEqual(restored.seats[0].player_id, 1)
            self.assertIn(1, restored.session_tokens)

    def test_restart_policy_keep_preserves_in_progress_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = str(Path(temp_dir) / "session-store.json")
            store = JsonFileSessionStore(session_path)

            first = SessionService(
                session_store=store,
                restart_recovery_policy="keep",
            )
            created = first.create_session(_seats(), config={"seed": 42})
            first.join_session(created.session_id, 1, created.join_tokens[1], "P1")
            first.start_session(created.session_id, created.host_token)

            second = SessionService(
                session_store=store,
                restart_recovery_policy="keep",
            )
            restored = second.get_session(created.session_id)
            self.assertEqual(restored.status.value, "in_progress")
            runtime = RuntimeService(
                session_service=second,
                stream_service=StreamService(),
                prompt_service=PromptService(),
            )
            runtime_status = runtime.runtime_status(created.session_id)
            self.assertEqual(runtime_status.get("status"), "recovery_required")
            self.assertEqual(runtime_status.get("reason"), "runtime_task_missing_after_restart")

    def test_stream_buffer_persists_across_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stream_path = str(Path(temp_dir) / "stream-store.json")
            store = JsonFileStreamStore(stream_path)

            first = StreamService(stream_store=store)

            async def _seed() -> None:
                await first.publish("sess_replay_1", "event", {"event_type": "round_start"})
                await first.publish("sess_replay_1", "event", {"event_type": "turn_start"})

            asyncio.run(_seed())

            second = StreamService(stream_store=store)

            async def _check() -> None:
                latest = await second.latest_seq("sess_replay_1")
                snap = await second.snapshot("sess_replay_1")
                source = [message for message in snap if message.type != "view_commit"]
                commits = [message for message in snap if message.type == "view_commit"]
                self.assertEqual(latest, 4)
                self.assertEqual([message.seq for message in source], [1, 3])
                self.assertEqual([message.seq for message in commits], [2, 4])
                self.assertEqual(source[0].payload.get("event_type"), "round_start")
                self.assertEqual(source[1].payload.get("event_type"), "turn_start")

            asyncio.run(_check())

    def test_session_store_retention_keeps_recent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = str(Path(temp_dir) / "session-store.json")
            store = JsonFileSessionStore(session_path)
            service = SessionService(session_store=store, max_persisted_sessions=2)
            s1 = service.create_session(_seats(), config={"seed": 1})
            service.join_session(s1.session_id, 1, s1.join_tokens[1], "P1")
            service.start_session(s1.session_id, s1.host_token)
            service.finish_session(s1.session_id)
            s2 = service.create_session(_seats(), config={"seed": 2})
            s3 = service.create_session(_seats(), config={"seed": 3})

            reloaded = SessionService(session_store=store)
            sessions = sorted(reloaded.list_sessions(), key=lambda s: s.session_id)
            self.assertEqual(len(sessions), 2)
            ids = {s.session_id for s in sessions}
            self.assertIn(s2.session_id, ids)
            self.assertIn(s3.session_id, ids)

    def test_stream_store_retention_keeps_recent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stream_path = str(Path(temp_dir) / "stream-store.json")
            store = JsonFileStreamStore(stream_path)
            first = StreamService(stream_store=store, max_persisted_sessions=2)

            async def _seed() -> None:
                await first.publish("sess_a", "event", {"event_type": "round_start"})
                await first.publish("sess_b", "event", {"event_type": "round_start"})
                await first.publish("sess_c", "event", {"event_type": "round_start"})

            asyncio.run(_seed())

            second = StreamService(stream_store=store)

            async def _check() -> None:
                latest_a = await second.latest_seq("sess_a")
                latest_b = await second.latest_seq("sess_b")
                latest_c = await second.latest_seq("sess_c")
                kept_count = sum(1 for v in [latest_a, latest_b, latest_c] if v > 0)
                self.assertEqual(kept_count, 2)

            asyncio.run(_check())

    def test_redis_restart_recovers_stream_status_checkpoint_and_commands(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-restart", socket_timeout_ms=250),
            client_factory=_FakeRedis,
        )
        game_state = RedisGameStateStore(connection)
        command_store = RedisCommandStore(connection)

        first_sessions = SessionService(restart_recovery_policy="keep")
        first_streams = StreamService(
            stream_backend=RedisStreamStore(connection),
            game_state_store=game_state,
            command_store=command_store,
        )
        first_prompts = PromptService(prompt_store=RedisPromptStore(connection), command_store=command_store)
        session = first_sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 202},
        )
        first_sessions.start_session(session.session_id, session.host_token)

        async def _seed() -> None:
            await first_streams.publish(
                session.session_id,
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "round_index": 1,
                    "turn_index": 4,
                    "snapshot": {"schema_version": 1, "turn": 4},
                },
            )
            await first_streams.publish(
                session.session_id,
                "event",
                {
                    "event_type": "decision_resolved",
                    "request_id": "req_restart_ai",
                    "request_type": "movement",
                    "resolution": "accepted",
                    "choice_id": "roll",
                    "provider": "ai",
                    "player_id": 1,
                },
            )

        asyncio.run(_seed())

        second_streams = StreamService(
            stream_backend=RedisStreamStore(connection),
            game_state_store=game_state,
            command_store=command_store,
        )
        second_runtime = RuntimeService(
            session_service=first_sessions,
            stream_service=second_streams,
            prompt_service=first_prompts,
            runtime_state_store=RedisRuntimeStateStore(connection),
            game_state_store=game_state,
        )

        async def _verify() -> None:
            self.assertEqual(await second_streams.latest_seq(session.session_id), 4)
            replay = await second_streams.replay_from(session.session_id, 0)
            self.assertEqual([item.seq for item in replay if item.type != "view_commit"], [1, 3])
            self.assertEqual([item.seq for item in replay if item.type == "view_commit"], [2, 4])

        asyncio.run(_verify())
        status = second_runtime.runtime_status(session.session_id)
        commands = command_store.list_commands(session.session_id)

        self.assertEqual(status["status"], "recovery_required")
        self.assertTrue(status["recovery_checkpoint"]["available"])
        self.assertEqual(status["recovery_checkpoint"]["checkpoint"]["turn_index"], 4)
        self.assertEqual(commands[0]["payload"]["request_id"], "req_restart_ai")

    def test_pending_resume_command_rejects_nested_decision_module_mismatch(self) -> None:
        connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/10",
                key_prefix="mrn-restart-nested-module",
                socket_timeout_ms=250,
            ),
            client_factory=_FakeRedis,
        )
        game_state = RedisGameStateStore(connection)
        command_store = RedisCommandStore(connection)
        session_id = "sess_nested_resume"
        game_state.save_current_state(session_id, {"tiles": [{"owner": None}], "turn_index": 2})
        game_state.save_checkpoint(
            session_id,
            {
                "schema_version": 3,
                "session_id": session_id,
                "runner_kind": "module",
                "waiting_prompt_request_id": "req_resume",
                "active_frame_id": "turn:2:p0",
                "active_module_id": "mod:turn:2:p0:movement",
                "active_module_type": "MapMoveModule",
                "active_module_cursor": "move:await_choice",
            },
        )
        command_store.append_command(
            session_id,
            "decision_submitted",
            {
                "decision": {
                    "request_id": "req_resume",
                    "choice_id": "roll",
                    "frame_id": "turn:2:p0",
                    "module_id": "mod:turn:2:p0:movement",
                    "module_type": "MapMoveModule",
                    "module_cursor": "move:old",
                }
            },
            request_id="req_resume",
        )
        runtime = RuntimeService(
            session_service=SessionService(restart_recovery_policy="keep"),
            stream_service=StreamService(),
            prompt_service=PromptService(),
            game_state_store=game_state,
            command_store=command_store,
        )

        pending = runtime.pending_resume_command(session_id)

        self.assertIsNone(pending)


if __name__ == "__main__":
    unittest.main()
