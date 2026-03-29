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


def _reset_state(max_buffer: int = 2000) -> None:
    from apps.server.src import state

    state.session_service = SessionService()
    state.stream_service = StreamService(max_buffer=max_buffer)
    state.prompt_service = PromptService()
    state.runtime_service = RuntimeService(session_service=state.session_service, stream_service=state.stream_service)


def _all_ai_seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
    ]


def _seat1_human_others_ai() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
    ]


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class StreamApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state(max_buffer=2)
        self.client = TestClient(app)

    def test_resume_gap_too_old_emits_error_and_replays_latest_buffer(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 42})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e1"})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e2"})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e3"})

        asyncio.run(_seed())

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})

            messages: list[dict] = []
            for _ in range(6):
                msg = ws.receive_json()
                messages.append(msg)
                has_gap_error = any(
                    m.get("type") == "error" and m.get("payload", {}).get("code") == "RESUME_GAP_TOO_OLD"
                    for m in messages
                )
                replayed_seqs = sorted(m.get("seq") for m in messages if m.get("type") == "event")
                if has_gap_error and replayed_seqs == [2, 3]:
                    break

        gap_errors = [
            m for m in messages if m.get("type") == "error" and m.get("payload", {}).get("code") == "RESUME_GAP_TOO_OLD"
        ]
        replayed_seqs = sorted(m.get("seq") for m in messages if m.get("type") == "event")

        self.assertGreaterEqual(len(gap_errors), 1)
        self.assertEqual(replayed_seqs, [2, 3])
        self.assertIn("server_time_ms", gap_errors[0])

    def test_spectator_decision_is_rejected_with_unauthorized_seat(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 7})
        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_spectator",
                    "player_id": 1,
                    "choice_id": "skip",
                    "choice_payload": {},
                }
            )

            messages: list[dict] = []
            for _ in range(6):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "error" and msg.get("payload", {}).get("code") == "UNAUTHORIZED_SEAT":
                    break

        errors = [m for m in messages if m.get("type") == "error"]
        self.assertGreaterEqual(len(errors), 1)
        self.assertEqual(errors[-1].get("payload", {}).get("code"), "UNAUTHORIZED_SEAT")

    def test_seat_decision_with_player_mismatch_is_rejected(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 11})
        join_token = session.join_tokens[1]
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=join_token)
        session_token = joined["session_token"]

        path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
        with self.client.websocket_connect(path) as ws:
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_mismatch",
                    "player_id": 2,
                    "choice_id": "skip",
                    "choice_payload": {},
                }
            )

            messages: list[dict] = []
            for _ in range(6):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "error" and msg.get("payload", {}).get("code") == "PLAYER_MISMATCH":
                    break

        errors = [m for m in messages if m.get("type") == "error"]
        self.assertGreaterEqual(len(errors), 1)
        self.assertEqual(errors[-1].get("payload", {}).get("code"), "PLAYER_MISMATCH")


if __name__ == "__main__":
    unittest.main()
