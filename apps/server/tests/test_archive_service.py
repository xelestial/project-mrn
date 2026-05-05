from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from apps.server.src.services.archive_service import LocalJsonArchiveService
from apps.server.src.services.room_service import RoomService
from apps.server.src.services.session_service import SessionNotFoundError, SessionService
from apps.server.src.services.stream_service import StreamService


def _room_seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "human"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
    ]


class ArchiveServiceTests(unittest.TestCase):
    def test_archive_export_writes_json_and_cleans_hot_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions = SessionService(restart_recovery_policy="keep")
            streams = StreamService()
            rooms = RoomService(session_service=sessions)
            archive = LocalJsonArchiveService(
                session_service=sessions,
                stream_service=streams,
                room_service=rooms,
                archive_dir=temp_dir,
                hot_retention_seconds=0,
                redis_key_prefix="mrn-test",
                service_version="test-suite",
            )

            created = rooms.create_room(
                room_title="Archive Room",
                seats=_room_seats(),
                host_seat=1,
                nickname="Host",
                config={"seed": 42},
            )
            guest = rooms.join_room(room_no=1, seat=2, nickname="Guest")
            rooms.set_ready(room_no=1, room_member_token=created["room_member_token"], ready=True)
            rooms.set_ready(room_no=1, room_member_token=guest["room_member_token"], ready=True)
            started = rooms.start_room(room_no=1, room_member_token=created["room_member_token"])
            session = sessions.get_session(started["session_id"])
            sessions.start_session(session.session_id, session.host_token)

            async def _exercise() -> None:
                await streams.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
                await streams.publish(session.session_id, "event", {"event_type": "turn_start", "turn_index": 1})
                sessions.finish_session(session.session_id)
                await archive.handle_session_finished(session.session_id)
                rooms.handle_session_finished(session.session_id)
                await asyncio.sleep(0)

            asyncio.run(_exercise())

            archive_path = Path(temp_dir) / f"{session.session_id}.json"
            self.assertTrue(archive_path.exists())
            payload = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["schema_name"], "mrn.canonical_archive")
            self.assertEqual(payload["visibility"], "backend_canonical")
            self.assertFalse(payload["browser_safe"])
            self.assertEqual(payload["session"]["session_id"], session.session_id)
            self.assertEqual(payload["session"]["room_no"], 1)
            self.assertEqual(payload["session"]["room_title"], "Archive Room")
            self.assertEqual(payload["counts"]["event_count"], 2)
            self.assertEqual(payload["counts"]["view_commit_count"], 2)
            self.assertEqual(payload["exporter"]["redis_prefix"], "mrn-test")
            self.assertEqual(payload["final_state"]["host_token"], "")
            self.assertEqual(payload["final_state"]["session_tokens"], {})

            with self.assertRaises(SessionNotFoundError):
                sessions.get_session(session.session_id)

            async def _verify_cleanup() -> None:
                self.assertEqual(await streams.latest_seq(session.session_id), 0)
                self.assertEqual(await streams.snapshot(session.session_id), [])

            asyncio.run(_verify_cleanup())

    def test_archive_export_includes_separate_command_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions = SessionService(restart_recovery_policy="keep")
            streams = StreamService()
            command_store = _CommandStoreStub()
            archive = LocalJsonArchiveService(
                session_service=sessions,
                stream_service=streams,
                command_store=command_store,
                archive_dir=temp_dir,
                hot_retention_seconds=0,
            )
            session = sessions.create_session(
                seats=[
                    {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ],
                config={"seed": 7},
            )
            sessions.start_session(session.session_id, session.host_token)
            command_store.append_command(
                session.session_id,
                "decision_submitted",
                {
                    "request_id": "req_archive_1",
                    "player_id": 1,
                    "choice_id": "roll",
                },
            )

            async def _exercise() -> None:
                await streams.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
                sessions.finish_session(session.session_id)
                await archive.handle_session_finished(session.session_id)
                await asyncio.sleep(0)

            asyncio.run(_exercise())

            payload = json.loads((Path(temp_dir) / f"{session.session_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["command_count"], 1)
            self.assertEqual(payload["streams"]["commands"][0]["type"], "decision_submitted")
            self.assertEqual(payload["streams"]["commands"][0]["payload"]["request_id"], "req_archive_1")

    def test_archive_final_view_state_prefers_latest_view_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions = SessionService(restart_recovery_policy="keep")
            streams = StreamService()
            archive = LocalJsonArchiveService(
                session_service=sessions,
                stream_service=streams,
                game_state_store=_GameStateStoreStub(),
                archive_dir=temp_dir,
                hot_retention_seconds=0,
            )
            session = sessions.create_session(
                seats=[
                    {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ],
                config={"seed": 7},
            )
            sessions.start_session(session.session_id, session.host_token)

            async def _exercise() -> None:
                await streams.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
                sessions.finish_session(session.session_id)
                await archive.handle_session_finished(session.session_id)
                await asyncio.sleep(0)

            asyncio.run(_exercise())

            payload = json.loads((Path(temp_dir) / f"{session.session_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["final_view_state"], {"view_commit": True})
            self.assertEqual(payload["final_state"], {"canonical": True})

class _CommandStoreStub:
    def __init__(self) -> None:
        self._commands: dict[str, list[dict]] = {}

    def append_command(self, session_id: str, command_type: str, payload: dict) -> None:
        items = self._commands.setdefault(session_id, [])
        seq = len(items) + 1
        items.append(
            {
                "seq": seq,
                "type": command_type,
                "session_id": session_id,
                "server_time_ms": 1000 + seq,
                "payload": dict(payload),
            }
        )

    def list_commands(self, session_id: str) -> list[dict]:
        return list(self._commands.get(session_id, []))


class _GameStateStoreStub:
    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, viewer, player_id
        return {"view_state": {"view_commit": True}}

    def load_checkpoint(self, session_id: str) -> dict:
        return {"session_id": session_id, "latest_seq": 1}

    def load_current_state(self, session_id: str) -> dict:
        del session_id
        return {"canonical": True}

    def load_projected_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, player_id
        if viewer == "public":
            return {"public_projection": True}
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return {"view_state_alias": True}

    def delete_session_data(self, session_id: str) -> None:
        del session_id


if __name__ == "__main__":
    unittest.main()
