from __future__ import annotations

import asyncio
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
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService


def _reset_state() -> None:
    from apps.server.src import state

    state.session_service = SessionService()
    state.stream_service = StreamService()
    state.prompt_service = PromptService()
    state.runtime_service = RuntimeService(session_service=state.session_service, stream_service=state.stream_service)


def _all_ai_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {"seed": 42},
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class SessionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state()
        self.client = TestClient(app)

    def test_runtime_status_shape(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["data"]["session_id"]

        runtime = self.client.get(f"/api/v1/sessions/{session_id}/runtime-status")
        self.assertEqual(runtime.status_code, 200)
        payload = runtime.json()["data"]["runtime"]
        self.assertIn("status", payload)

    def test_replay_endpoint_returns_buffered_messages(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        session_id = created.json()["data"]["session_id"]

        async def _seed_events() -> None:
            from apps.server.src import state

            await state.stream_service.publish(session_id, "event", {"event_type": "round_start"})
            await state.stream_service.publish(session_id, "event", {"event_type": "turn_start"})

        asyncio.run(_seed_events())

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        data = replay.json()["data"]
        self.assertEqual(data["event_count"], 2)
        self.assertEqual(data["events"][0]["seq"], 1)
        self.assertEqual(data["events"][1]["seq"], 2)
        self.assertIn("server_time_ms", data["events"][0])


if __name__ == "__main__":
    unittest.main()
