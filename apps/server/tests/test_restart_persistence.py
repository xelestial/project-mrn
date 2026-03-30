from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from apps.server.src.services.persistence import JsonFileSessionStore, JsonFileStreamStore
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService


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
                self.assertEqual(latest, 2)
                self.assertEqual(len(snap), 2)
                self.assertEqual(snap[0].payload.get("event_type"), "round_start")
                self.assertEqual(snap[1].payload.get("event_type"), "turn_start")

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


if __name__ == "__main__":
    unittest.main()
