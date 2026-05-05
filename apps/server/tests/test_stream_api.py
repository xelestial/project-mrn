from __future__ import annotations

import asyncio
import time
import unittest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.routes.stream import _filter_stream_message, _send_stream_catch_up

try:
    from fastapi.testclient import TestClient
    from apps.server.src.app import app
    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    TestClient = None
    app = None
    FASTAPI_AVAILABLE = False

from apps.server.src.services.prompt_service import PromptService
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorker
from apps.server.tests.prompt_payloads import module_prompt


def _reset_state(max_buffer: int = 2000, heartbeat_interval_ms: int = 5000) -> None:
    from apps.server.src import state

    state.runtime_settings = RuntimeSettings(
        stream_heartbeat_interval_ms=heartbeat_interval_ms,
        stream_sender_poll_timeout_ms=100,
        runtime_watchdog_timeout_ms=45000,
    )
    state.session_service = SessionService()
    state.stream_service = StreamService(max_buffer=max_buffer)
    state.prompt_service = PromptService()
    state.runtime_service = RuntimeService(
        session_service=state.session_service,
        stream_service=state.stream_service,
        prompt_service=state.prompt_service,
    )
    state.prompt_timeout_worker = PromptTimeoutWorker(
        prompt_service=state.prompt_service,
        runtime_service=state.runtime_service,
        stream_service=state.stream_service,
    )


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


def _three_ai_line_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": 202,
            "board_topology": "line",
            "seat_limits": {"min": 1, "max": 3, "allowed": [1, 2, 3]},
            "visibility": "public",
        },
    }


def _three_seat_line_with_human_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "human"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": 202,
            "board_topology": "line",
            "seat_limits": {"min": 1, "max": 3, "allowed": [1, 2, 3]},
            "visibility": "public",
        },
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class StreamApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state(max_buffer=256, heartbeat_interval_ms=250)
        self.client = TestClient(app)

    def test_resume_gap_too_old_emits_error_and_replays_latest_buffer(self) -> None:
        from apps.server.src import state

        _reset_state(max_buffer=2, heartbeat_interval_ms=250)
        self.client = TestClient(app)
        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 42, "visibility": "public"})

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
        self.assertEqual(gap_errors[0].get("payload", {}).get("category"), "transport")

    def test_heartbeat_does_not_run_prompt_timeout_worker(self) -> None:
        from apps.server.src import state

        calls: list[str | None] = []

        class CountingTimeoutWorker:
            async def run_once(self, session_id: str | None = None) -> list[dict]:
                calls.append(session_id)
                return []

        state.prompt_timeout_worker = CountingTimeoutWorker()  # type: ignore[assignment]
        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 7, "visibility": "public"})

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            heartbeat = ws.receive_json()

        self.assertEqual(heartbeat.get("type"), "heartbeat")
        self.assertEqual(calls, [])

    def test_resume_projects_only_latest_replayed_message(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 303, "visibility": "public"})

        async def _seed() -> None:
            for n in range(1, 9):
                await state.stream_service.publish(
                    session.session_id,
                    "event",
                    {"event_type": "round_start", "round_index": n},
                )

        asyncio.run(_seed())

        projected_seqs: list[int] = []
        original_project = state.stream_service.project_message_for_viewer

        async def _count_project(message: dict, viewer: object) -> dict | None:
            projected_seqs.append(int(message.get("seq", 0)))
            return await original_project(message, viewer)  # type: ignore[arg-type]

        state.stream_service.project_message_for_viewer = _count_project  # type: ignore[method-assign]
        try:
            path = f"/api/v1/sessions/{session.session_id}/stream"
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_seq": 0})
                seen: list[int] = []
                latest_payload: dict | None = None
                for _ in range(20):
                    msg = ws.receive_json()
                    if msg.get("type") != "event":
                        continue
                    seen.append(int(msg.get("seq", 0)))
                    latest_payload = msg.get("payload") if msg.get("seq") == 8 else latest_payload
                    if seen == list(range(1, 9)):
                        break
        finally:
            state.stream_service.project_message_for_viewer = original_project  # type: ignore[method-assign]

        self.assertEqual(seen, list(range(1, 9)))
        self.assertEqual(projected_seqs, [8])
        self.assertIsInstance(latest_payload, dict)
        self.assertIn("view_state", latest_payload or {})

    def test_resume_replays_stream_without_runtime_transition(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 304, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "turn_start", "turn_index": 1})

        asyncio.run(_seed())

        transition_calls: list[str] = []
        original_once = state.runtime_service._run_engine_transition_once_sync

        def _fail_transition(*args, **kwargs):  # type: ignore[no-untyped-def]
            transition_calls.append("transition")
            raise AssertionError("resume must not advance runtime")

        state.runtime_service._run_engine_transition_once_sync = _fail_transition  # type: ignore[method-assign]
        try:
            path = f"/api/v1/sessions/{session.session_id}/stream"
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_seq": 0})
                seen: list[int] = []
                for _ in range(8):
                    msg = ws.receive_json()
                    if msg.get("type") != "event":
                        continue
                    seen.append(int(msg.get("seq", 0)))
                    if seen == [1, 2]:
                        break
        finally:
            state.runtime_service._run_engine_transition_once_sync = original_once  # type: ignore[method-assign]

        self.assertEqual(seen, [1, 2])
        self.assertEqual(transition_calls, [])

    def test_stream_catch_up_replays_persisted_events_missed_by_live_queue(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 305, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
            await state.stream_service.publish(
                session.session_id,
                "prompt",
                module_prompt(
                    {
                        "request_id": "r_seat1",
                        "request_type": "final_character",
                        "player_id": 1,
                        "timeout_ms": 5000,
                        "legal_choices": [{"choice_id": "6", "label": "박수"}],
                    },
                    module_type="DraftModule",
                    frame_id="round:test:draft:p1",
                ),
            )
            await state.stream_service.publish(
                session.session_id,
                "prompt",
                module_prompt(
                    {
                        "request_id": "r_seat2",
                        "request_type": "final_character",
                        "player_id": 2,
                        "timeout_ms": 5000,
                        "legal_choices": [{"choice_id": "1", "label": "어사"}],
                    },
                    module_type="DraftModule",
                    frame_id="round:test:draft:p2",
                ),
            )

        class FakeWebSocket:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_json(self, message: dict) -> None:
                self.sent.append(message)

        fake_ws = FakeWebSocket()
        asyncio.run(_seed())
        latest = asyncio.run(
            _send_stream_catch_up(
                fake_ws,  # type: ignore[arg-type]
                state.stream_service,
                session_id=session.session_id,
                last_sent_seq=0,
                viewer=ViewerContext(role="seat", session_id=session.session_id, player_id=1),
                auth_ctx={"role": "seat", "player_id": 1},
            )
        )

        self.assertEqual(latest, 3)
        self.assertEqual([message.get("seq") for message in fake_ws.sent], [1, 2])
        self.assertEqual(fake_ws.sent[-1].get("payload", {}).get("request_id"), "r_seat1")
        self.assertIn("view_state", fake_ws.sent[-1].get("payload", {}))

    def test_spectator_decision_is_rejected_with_unauthorized_seat(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 7, "visibility": "public"})
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
        self.assertEqual(errors[-1].get("payload", {}).get("category"), "auth")

    def test_private_session_stream_rejects_missing_token(self) -> None:
        from starlette.websockets import WebSocketDisconnect
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 7})
        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            error = ws.receive_json()
            self.assertEqual(error.get("payload", {}).get("code"), "SPECTATOR_NOT_ALLOWED")
            with self.assertRaises(WebSocketDisconnect) as raised:
                ws.receive_json()
        self.assertEqual(raised.exception.code, 1008)

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
        self.assertEqual(errors[-1].get("payload", {}).get("category"), "auth")

    def test_seat_decision_accepts_pending_prompt_with_ack(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 17})
        join_token = session.join_tokens[1]
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=join_token)
        session_token = joined["session_token"]
        state.prompt_service.create_prompt(
            session.session_id,
            {
                "request_id": "r_accept_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 5000,
                "fallback_policy": "timeout_fallback",
            },
        )

        path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
        with self.client.websocket_connect(path) as ws:
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_accept_1",
                    "player_id": 1,
                    "choice_id": "roll",
                    "choice_payload": {},
                }
            )

            messages: list[dict] = []
            for _ in range(10):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "decision_ack" and msg.get("payload", {}).get("request_id") == "r_accept_1":
                    break

        acks = [m for m in messages if m.get("type") == "decision_ack" and m.get("payload", {}).get("request_id") == "r_accept_1"]
        self.assertGreaterEqual(len(acks), 1)
        self.assertEqual(acks[-1].get("payload", {}).get("status"), "accepted")
        self.assertIsNone(acks[-1].get("payload", {}).get("reason"))
        self.assertEqual(acks[-1].get("payload", {}).get("provider"), "human")

    def test_spectator_does_not_receive_prompt_or_decision_ack_for_seat(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 19, "visibility": "public"})
        join_token = session.join_tokens[1]
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=join_token)
        session_token = joined["session_token"]

        spectator_path = f"/api/v1/sessions/{session.session_id}/stream"
        seat_path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
        with self.client.websocket_connect(spectator_path) as spectator_ws, self.client.websocket_connect(seat_path) as seat_ws:
            async def _publish_private_messages() -> None:
                await state.stream_service.publish(
                    session.session_id,
                    "prompt",
                    module_prompt({
                        "request_id": "r_private_prompt",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 5000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                    }, module_type="MapMoveModule", frame_id="turn:test:p0"),
                )
                await state.stream_service.publish(
                    session.session_id,
                    "decision_ack",
                    {
                        "request_id": "r_private_prompt",
                        "status": "accepted",
                        "player_id": 1,
                        "provider": "human",
                    },
                )

            asyncio.run(_publish_private_messages())

            seat_messages: list[dict] = []
            for _ in range(6):
                msg = seat_ws.receive_json()
                seat_messages.append(msg)
                seen_types = {item.get("type") for item in seat_messages}
                if "prompt" in seen_types and "decision_ack" in seen_types:
                    break

            spectator_messages: list[dict] = []
            for _ in range(4):
                spectator_messages.append(spectator_ws.receive_json())

        self.assertIn("prompt", {msg.get("type") for msg in seat_messages})
        self.assertIn("decision_ack", {msg.get("type") for msg in seat_messages})
        self.assertNotIn("prompt", {msg.get("type") for msg in spectator_messages})
        self.assertNotIn("decision_ack", {msg.get("type") for msg in spectator_messages})

    def test_seat_decision_retry_returns_stale_after_first_accept(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 18})
        join_token = session.join_tokens[1]
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=join_token)
        session_token = joined["session_token"]
        state.prompt_service.create_prompt(
            session.session_id,
            {
                "request_id": "r_retry_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 5000,
                "fallback_policy": "timeout_fallback",
            },
        )

        path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
        with self.client.websocket_connect(path) as ws:
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_retry_1",
                    "player_id": 1,
                    "choice_id": "roll",
                    "choice_payload": {},
                }
            )
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_retry_1",
                    "player_id": 1,
                    "choice_id": "roll",
                    "choice_payload": {},
                }
            )

            acks: list[dict] = []
            for _ in range(20):
                msg = ws.receive_json()
                if msg.get("type") != "decision_ack":
                    continue
                payload = msg.get("payload", {})
                if payload.get("request_id") != "r_retry_1":
                    continue
                acks.append(payload)
                if len(acks) >= 2:
                    break

        self.assertGreaterEqual(len(acks), 2)
        self.assertEqual(acks[0].get("status"), "accepted")
        self.assertEqual(acks[1].get("status"), "stale")
        self.assertEqual(acks[1].get("reason"), "already_resolved")
        self.assertEqual(acks[0].get("provider"), "human")
        self.assertEqual(acks[1].get("provider"), "human")

    def test_prompt_timeout_emits_fallback_execution_and_runtime_tracks_history(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 13, "visibility": "public"})
        state.prompt_service.create_prompt(
            session.session_id,
            {
                "request_id": "r_timeout_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 1,
                "fallback_policy": "timeout_fallback",
                "fallback_choice_id": "choice_timeout_default",
                "legal_choices": [{"choice_id": "choice_timeout_default", "label": "Default"}],
            },
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        timeout_events: list[dict] = []
        resolved_events: list[dict] = []
        resolved_seq: int | None = None
        timeout_seq: int | None = None
        with self.client.websocket_connect(path) as ws:
            time.sleep(0.01)
            asyncio.run(state.prompt_timeout_worker.run_once(session_id=session.session_id))
            for _ in range(40):
                msg = ws.receive_json()
                if msg.get("type") != "event":
                    continue
                payload = msg.get("payload", {})
                if payload.get("event_type") == "decision_resolved":
                    resolved_events.append(payload)
                    resolved_seq = int(msg.get("seq", 0))
                if payload.get("event_type") == "decision_timeout_fallback":
                    timeout_events.append(payload)
                    timeout_seq = int(msg.get("seq", 0))
                    break

        self.assertEqual(len(resolved_events), 1)
        self.assertEqual(resolved_events[0].get("resolution"), "timeout_fallback")
        self.assertEqual(resolved_events[0].get("choice_id"), "choice_timeout_default")
        self.assertEqual(resolved_events[0].get("provider"), "human")
        self.assertEqual(len(timeout_events), 1)
        self.assertEqual(timeout_events[0].get("fallback_execution"), "executed")
        self.assertEqual(timeout_events[0].get("fallback_choice_id"), "choice_timeout_default")
        self.assertEqual(timeout_events[0].get("provider"), "human")
        self.assertIsNotNone(resolved_seq)
        self.assertIsNotNone(timeout_seq)
        self.assertLess(resolved_seq, timeout_seq)
        runtime_status = state.runtime_service.runtime_status(session.session_id)
        recent = runtime_status.get("recent_fallbacks", [])
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[-1].get("request_id"), "r_timeout_1")

    def test_resume_replays_latest_parameter_manifest_change(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 99, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "parameter_manifest",
                    "parameter_manifest": {"manifest_hash": "hash_old"},
                },
            )
            await state.stream_service.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "parameter_manifest",
                    "parameter_manifest": {"manifest_hash": "hash_new"},
                },
            )

        asyncio.run(_seed())

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_seq": 1})
            replayed = []
            for _ in range(4):
                msg = ws.receive_json()
                if msg.get("type") == "event":
                    replayed.append(msg)
                if len(replayed) >= 2:
                    break

        self.assertEqual([m.get("seq") for m in replayed], [2, 3])
        self.assertEqual(replayed[0].get("payload", {}).get("event_type"), "round_start")
        self.assertEqual(replayed[1].get("payload", {}).get("event_type"), "parameter_manifest")
        self.assertEqual(
            replayed[1].get("payload", {}).get("parameter_manifest", {}).get("manifest_hash"),
            "hash_new",
        )

    def test_resume_replays_flat_parameter_manifest_shape_without_mutation(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 100, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "parameter_manifest",
                    "manifest_hash": "flat_hash_new",
                    "board": {"tile_count": 40},
                },
            )
            await state.stream_service.publish(session.session_id, "event", {"event_type": "turn_start", "turn_index": 1})

        asyncio.run(_seed())

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_seq": 1})
            replayed = []
            for _ in range(4):
                msg = ws.receive_json()
                if msg.get("type") == "event":
                    replayed.append(msg)
                if len(replayed) >= 2:
                    break

        self.assertEqual([m.get("seq") for m in replayed], [2, 3])
        self.assertEqual(replayed[0].get("payload", {}).get("event_type"), "parameter_manifest")
        self.assertEqual(replayed[0].get("payload", {}).get("manifest_hash"), "flat_hash_new")
        self.assertEqual(replayed[0].get("payload", {}).get("board", {}).get("tile_count"), 40)
        self.assertEqual(replayed[1].get("payload", {}).get("event_type"), "turn_start")

    def test_resume_preserves_decision_then_domain_event_order(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 101, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "decision_requested",
                    "request_id": "r_order_1",
                    "player_id": 1,
                    "request_type": "movement",
                },
            )
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "decision_resolved",
                    "request_id": "r_order_1",
                    "player_id": 1,
                    "resolution": "accepted",
                    "choice_id": "roll",
                },
            )
            await state.stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "player_move",
                    "acting_player_id": 1,
                    "from_tile_index": 0,
                    "to_tile_index": 5,
                },
            )

        asyncio.run(_seed())

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})
            replayed: list[dict] = []
            for _ in range(8):
                msg = ws.receive_json()
                if msg.get("type") != "event":
                    continue
                replayed.append(msg)
                if len(replayed) >= 3:
                    break

        event_types = [m.get("payload", {}).get("event_type") for m in replayed]
        self.assertEqual(event_types, ["decision_requested", "decision_resolved", "player_move"])

    def test_filter_stream_message_hides_private_draft_details_from_other_viewers(self) -> None:
        seat1_auth = {"role": "seat", "player_id": 1}
        seat2_auth = {"role": "seat", "player_id": 2}
        spectator_auth = {"role": "spectator", "player_id": None}

        draft_requested = {
            "type": "event",
            "payload": {
                "event_type": "decision_requested",
                "player_id": 1,
                "request_type": "draft_card",
                "public_context": {"offered_names": ["객주", "박수", "자객"]},
            },
        }
        draft_resolved = {
            "type": "event",
            "payload": {
                "event_type": "decision_resolved",
                "player_id": 1,
                "request_type": "draft_card",
                "choice_id": "7",
            },
        }
        draft_pick = {
            "type": "event",
            "payload": {
                "event_type": "draft_pick",
                "player_id": 1,
                "acting_player_id": 1,
                "picked_card": 7,
            },
        }
        final_choice = {
            "type": "event",
            "payload": {
                "event_type": "final_character_choice",
                "player_id": 1,
                "acting_player_id": 1,
                "character": "객주",
            },
        }

        self.assertIsNotNone(_filter_stream_message(draft_requested, seat1_auth))
        self.assertIsNone(_filter_stream_message(draft_requested, seat2_auth))
        self.assertIsNone(_filter_stream_message(draft_requested, spectator_auth))

        self.assertIsNotNone(_filter_stream_message(draft_resolved, seat1_auth))
        self.assertIsNone(_filter_stream_message(draft_resolved, seat2_auth))
        self.assertIsNone(_filter_stream_message(draft_resolved, spectator_auth))

        filtered_seat2_draft = _filter_stream_message(draft_pick, seat2_auth)
        filtered_spectator_draft = _filter_stream_message(draft_pick, spectator_auth)
        self.assertIsNotNone(filtered_seat2_draft)
        self.assertIsNotNone(filtered_spectator_draft)
        self.assertNotIn("picked_card", filtered_seat2_draft["payload"])
        self.assertNotIn("picked_card", filtered_spectator_draft["payload"])

        self.assertIsNotNone(_filter_stream_message(final_choice, seat1_auth))
        self.assertIsNone(_filter_stream_message(final_choice, seat2_auth))
        self.assertIsNone(_filter_stream_message(final_choice, spectator_auth))

    def test_resume_replays_manifest_with_non_default_topology_and_seat_profile(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_three_seat_line_with_human_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]
        join_token = created_data["join_tokens"]["1"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": join_token, "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)

        original = state.runtime_service.start_runtime

        async def _noop_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            del session_id, seed, policy_mode

        state.runtime_service.start_runtime = _noop_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": host_token},
            )
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)
        expected_hash = started.json()["data"]["parameter_manifest"]["manifest_hash"]

        path = f"/api/v1/sessions/{session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})
            messages: list[dict] = []
            for _ in range(80):
                msg = ws.receive_json()
                messages.append(msg)
                manifest_events = [
                    m for m in messages if m.get("type") == "event" and m.get("payload", {}).get("event_type") == "parameter_manifest"
                ]
                if manifest_events:
                    break

        manifest_event = next(
            m
            for m in messages
            if m.get("type") == "event" and m.get("payload", {}).get("event_type") == "parameter_manifest"
        )
        manifest = manifest_event.get("payload", {}).get("parameter_manifest", {})
        self.assertEqual(manifest.get("manifest_hash"), expected_hash)
        self.assertEqual(manifest.get("board", {}).get("topology"), "line")
        self.assertEqual(manifest.get("seats", {}).get("allowed"), [1, 2, 3])

    def test_reconnect_replays_latest_manifest_after_hash_change_end_to_end(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_three_seat_line_with_human_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]
        join_token = created_data["join_tokens"]["1"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": join_token, "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)

        original = state.runtime_service.start_runtime

        async def _noop_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            del session_id, seed, policy_mode

        state.runtime_service.start_runtime = _noop_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": host_token},
            )
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)

        first_manifest_seq = 0
        ws_path = f"/api/v1/sessions/{session_id}/stream"
        with self.client.websocket_connect(ws_path) as ws:
            ws.send_json({"type": "resume", "last_seq": 0})
            for _ in range(120):
                msg = ws.receive_json()
                if msg.get("type") != "event":
                    continue
                payload = msg.get("payload", {})
                if payload.get("event_type") == "parameter_manifest":
                    first_manifest_seq = int(msg.get("seq", 0))
                    break

        self.assertGreater(first_manifest_seq, 0)

        async def _publish_manifest_change() -> None:
            await state.stream_service.publish(
                session_id,
                "event",
                {
                    "event_type": "parameter_manifest",
                    "parameter_manifest": {
                        "manifest_hash": "hash_e2e_changed",
                        "board": {"topology": "line", "tile_count": 40},
                        "seats": {"allowed": [1, 2, 3]},
                    },
                },
            )

        asyncio.run(_publish_manifest_change())

        with self.client.websocket_connect(ws_path) as ws:
            ws.send_json({"type": "resume", "last_seq": first_manifest_seq})
            replayed: list[dict] = []
            for _ in range(80):
                msg = ws.receive_json()
                if msg.get("type") != "event":
                    continue
                replayed.append(msg)
                payload = msg.get("payload", {})
                if payload.get("event_type") == "parameter_manifest" and payload.get("parameter_manifest", {}).get("manifest_hash") == "hash_e2e_changed":
                    break

        changed_manifest_event = next(
            m
            for m in replayed
            if m.get("payload", {}).get("event_type") == "parameter_manifest"
            and m.get("payload", {}).get("parameter_manifest", {}).get("manifest_hash") == "hash_e2e_changed"
        )
        changed_manifest = changed_manifest_event.get("payload", {}).get("parameter_manifest", {})
        self.assertEqual(changed_manifest.get("board", {}).get("topology"), "line")
        self.assertEqual(changed_manifest.get("seats", {}).get("allowed"), [1, 2, 3])

    def test_seat_stream_connection_recovers_runtime_when_in_progress(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_three_seat_line_with_human_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]
        join_token = created_data["join_tokens"]["1"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": join_token, "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        original = state.runtime_service.start_runtime

        async def _noop_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            del session_id, seed, policy_mode

        state.runtime_service.start_runtime = _noop_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": host_token},
            )
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)

        status_before = state.runtime_service.runtime_status(session_id)
        self.assertEqual(status_before.get("status"), "recovery_required")

        calls: list[tuple[str, int, str | None]] = []
        original = state.runtime_service.start_runtime

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            calls.append((session_id, seed, policy_mode))

        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        try:
            path = f"/api/v1/sessions/{session_id}/stream?token={session_token}"
            with self.client.websocket_connect(path):
                pass
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], session_id)

    def test_reconnect_soak_preserves_seq_continuity_across_multiple_resumes(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 303, "visibility": "public"})

        async def _seed(start: int, end: int) -> None:
            for n in range(start, end + 1):
                await state.stream_service.publish(
                    session.session_id,
                    "event",
                    {"event_type": "round_start", "round_index": n},
                )

        asyncio.run(_seed(1, 12))

        path = f"/api/v1/sessions/{session.session_id}/stream"

        def _collect_after(last_seq: int, target_latest_seq: int) -> list[int]:
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_seq": last_seq})
                seen: list[int] = []
                for _ in range(200):
                    msg = ws.receive_json()
                    if msg.get("type") != "event":
                        continue
                    seq = int(msg.get("seq", 0))
                    if seq <= 0:
                        continue
                    seen.append(seq)
                    if seq >= target_latest_seq:
                        break
            return seen

        first_seen = _collect_after(last_seq=0, target_latest_seq=12)
        self.assertEqual(first_seen, list(range(1, 13)))

        asyncio.run(_seed(13, 18))
        second_seen = _collect_after(last_seq=12, target_latest_seq=18)
        self.assertEqual(second_seen, list(range(13, 19)))

        asyncio.run(_seed(19, 23))
        third_seen = _collect_after(last_seq=18, target_latest_seq=23)
        self.assertEqual(third_seen, list(range(19, 24)))


if __name__ == "__main__":
    unittest.main()
