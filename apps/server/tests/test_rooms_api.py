from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient
    from apps.server.src.app import app
    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    TestClient = None
    app = None
    FASTAPI_AVAILABLE = False

from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.room_service import RoomService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService


def _reset_state() -> None:
    from apps.server.src import state

    async def _noop_start_runtime(*args, **kwargs) -> None:
        return None

    state.session_service = SessionService()
    state.stream_service = StreamService(
        player_name_resolver=lambda session_id: state.session_service.player_display_names(session_id),
    )
    state.prompt_service = PromptService()
    state.runtime_service = RuntimeService(
        session_service=state.session_service,
        stream_service=state.stream_service,
        prompt_service=state.prompt_service,
    )
    state.room_service = RoomService(session_service=state.session_service)
    state.runtime_service.add_session_finished_callback(state.room_service.handle_session_finished)
    state.runtime_service.start_runtime = _noop_start_runtime


def _room_payload() -> dict:
    return {
        "room_title": "Room Alpha",
        "host_seat": 1,
        "nickname": "Host",
        "seats": [
            {"seat": 1, "seat_type": "human"},
            {"seat": 2, "seat_type": "human"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {"seed": 42},
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class RoomsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state()
        self.client = TestClient(app)

    def test_room_flow_create_join_ready_start_resume(self) -> None:
        created = self.client.post("/api/v1/rooms", json=_room_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        room_no = created_data["room"]["room_no"]
        host_token = created_data["room_member_token"]

        listed = self.client.get("/api/v1/rooms")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["data"]["rooms"]), 1)

        joined = self.client.post(
            f"/api/v1/rooms/{room_no}/join",
            json={"seat": 2, "nickname": "Guest"},
        )
        self.assertEqual(joined.status_code, 200)
        guest_token = joined.json()["data"]["room_member_token"]

        ready_host = self.client.post(
            f"/api/v1/rooms/{room_no}/ready",
            json={"room_member_token": host_token, "ready": True},
        )
        self.assertEqual(ready_host.status_code, 200)
        ready_guest = self.client.post(
            f"/api/v1/rooms/{room_no}/ready",
            json={"room_member_token": guest_token, "ready": True},
        )
        self.assertEqual(ready_guest.status_code, 200)
        self.assertEqual(ready_guest.json()["data"]["human_ready_count"], 2)

        resumed = self.client.get(f"/api/v1/rooms/{room_no}/resume", params={"room_member_token": host_token})
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["data"]["member_nickname"], "Host")

        started = self.client.post(
            f"/api/v1/rooms/{room_no}/start",
            json={"room_member_token": host_token},
        )
        self.assertEqual(started.status_code, 200)
        started_data = started.json()["data"]
        self.assertIn("session_id", started_data)
        self.assertIn("1", started_data["session_tokens"])

    def test_room_missing_returns_404(self) -> None:
        response = self.client.get("/api/v1/rooms/999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "ROOM_NOT_FOUND")
