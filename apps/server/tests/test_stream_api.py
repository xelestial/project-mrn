from __future__ import annotations

import asyncio
import time
import unittest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.visibility.projector import project_stream_message_for_viewer

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


class _CachedViewCommitStore:
    def __init__(self) -> None:
        self._commits: dict[tuple[str, str, int | None], dict] = {}

    def apply_stream_message(self, _message: dict) -> None:
        return None

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        return self._commits.get((session_id, viewer, player_id if viewer == "player" else None))

    def save_view_commit(self, session_id: str, payload: dict, *, viewer: str, player_id: int | None = None) -> None:
        self._commits[(session_id, viewer, player_id if viewer == "player" else None)] = dict(payload)


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


def _cached_store() -> _CachedViewCommitStore:
    from apps.server.src import state

    store = getattr(state.stream_service, "_game_state_store", None)
    if not isinstance(store, _CachedViewCommitStore):
        store = _CachedViewCommitStore()
        state.stream_service._game_state_store = store
    return store


def _save_cached_view_commit(
    session_id: str,
    *,
    commit_seq: int,
    source_event_seq: int,
    view_state: dict | None = None,
    viewer: str = "spectator",
    player_id: int | None = None,
    seat: int | None = None,
    runtime: dict | None = None,
) -> dict:
    role = "seat" if viewer == "player" else viewer
    viewer_payload: dict = {"role": role}
    if player_id is not None:
        viewer_payload["player_id"] = player_id
    if seat is not None:
        viewer_payload["seat"] = seat
    payload = {
        "schema_version": 1,
        "commit_seq": commit_seq,
        "source_event_seq": source_event_seq,
        "viewer": viewer_payload,
        "runtime": runtime
        or {
            "status": "running",
            "round_index": view_state.get("turn_stage", {}).get("round_index", 0) if isinstance(view_state, dict) else 0,
            "turn_index": view_state.get("turn_stage", {}).get("turn_index", 0) if isinstance(view_state, dict) else 0,
            "active_frame_id": "frame:test",
            "active_module_id": "module:test",
            "active_module_type": "TestModule",
            "module_path": ["frame:test", "module:test"],
        },
        "view_state": dict(view_state or {}),
    }
    _cached_store().save_view_commit(session_id, payload, viewer=viewer, player_id=player_id)
    return payload


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

    def test_send_json_or_disconnect_treats_closed_socket_as_disconnect(self) -> None:
        from starlette.websockets import WebSocketDisconnect

        from apps.server.src.routes.stream import _send_json_or_disconnect

        class ClosedWebSocket:
            async def send_json(self, _payload: dict) -> None:
                raise RuntimeError('Cannot call "send" once a close message has been sent.')

        with self.assertRaises(WebSocketDisconnect):
            asyncio.run(_send_json_or_disconnect(ClosedWebSocket(), {"type": "heartbeat"}))  # type: ignore[arg-type]

    def test_receive_json_or_disconnect_treats_closed_socket_as_disconnect(self) -> None:
        from starlette.websockets import WebSocketDisconnect

        from apps.server.src.routes.stream import _receive_json_or_disconnect

        class ClosedWebSocket:
            async def receive_json(self) -> dict:
                raise RuntimeError("WebSocket is not connected. Need to call \"accept\" first.")

        with self.assertRaises(WebSocketDisconnect):
            asyncio.run(_receive_json_or_disconnect(ClosedWebSocket()))  # type: ignore[arg-type]

    def test_resume_uses_latest_view_commit_without_gap_replay(self) -> None:
        from apps.server.src import state

        _reset_state(max_buffer=2, heartbeat_interval_ms=250)
        self.client = TestClient(app)
        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 42, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e1"})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e2"})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "e3"})

        asyncio.run(_seed())
        _save_cached_view_commit(
            session.session_id,
            commit_seq=6,
            source_event_seq=5,
            view_state={"turn_stage": {"round_index": 1, "turn_index": 1}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})

            messages: list[dict] = []
            for _ in range(6):
                msg = ws.receive_json()
                messages.append(msg)
                commits = [m for m in messages if m.get("type") == "view_commit"]
                if commits and commits[-1].get("payload", {}).get("source_event_seq") == 5:
                    break

        gap_errors = [m for m in messages if m.get("type") == "error"]
        replayed_events = [m for m in messages if m.get("type") == "event"]
        commits = [m for m in messages if m.get("type") == "view_commit"]

        self.assertEqual(gap_errors, [])
        self.assertEqual(replayed_events, [])
        self.assertGreaterEqual(len(commits), 1)
        self.assertEqual(commits[-1].get("payload", {}).get("commit_seq"), 6)
        self.assertEqual(commits[-1].get("payload", {}).get("source_event_seq"), 5)

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

    def test_heartbeat_sends_new_cached_view_commit_when_subscriber_misses_event(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 71, "visibility": "public"})
        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            _save_cached_view_commit(
                session.session_id,
                commit_seq=3,
                source_event_seq=2,
                view_state={"turn_stage": {"round_index": 1, "turn_index": 1}},
            )

            messages: list[dict] = []
            commit: dict | None = None
            for _ in range(8):
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "view_commit":
                    commit = msg
                    break

        self.assertIsNotNone(commit, messages)
        self.assertEqual(commit.get("payload", {}).get("commit_seq"), 3)
        self.assertEqual(commit.get("payload", {}).get("source_event_seq"), 2)

    def test_resume_sends_only_latest_view_commit_snapshot(self) -> None:
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
        _save_cached_view_commit(
            session.session_id,
            commit_seq=16,
            source_event_seq=15,
            view_state={"turn_stage": {"round_index": 8, "turn_index": 0}},
        )

        projected_seqs: list[int] = []
        original_project = state.stream_service.project_message_for_viewer

        async def _count_project(message: dict, viewer: object) -> dict | None:
            projected_seqs.append(int(message.get("seq", 0)))
            return await original_project(message, viewer)  # type: ignore[arg-type]

        state.stream_service.project_message_for_viewer = _count_project  # type: ignore[method-assign]
        try:
            path = f"/api/v1/sessions/{session.session_id}/stream"
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_commit_seq": 0})
                commits: list[dict] = []
                for _ in range(20):
                    msg = ws.receive_json()
                    if msg.get("type") != "view_commit":
                        continue
                    commits.append(msg)
                    if msg.get("payload", {}).get("commit_seq") == 16:
                        break
        finally:
            state.stream_service.project_message_for_viewer = original_project  # type: ignore[method-assign]

        self.assertGreaterEqual(len(commits), 1)
        self.assertEqual(commits[-1].get("payload", {}).get("commit_seq"), 16)
        self.assertEqual(commits[-1].get("payload", {}).get("source_event_seq"), 15)
        self.assertEqual(projected_seqs, [])
        self.assertIn("view_state", commits[-1].get("payload", {}))

    def test_resume_resends_latest_view_commit_for_client_repair(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 3031, "visibility": "public"})
        _save_cached_view_commit(
            session.session_id,
            commit_seq=9,
            source_event_seq=8,
            view_state={"turn_stage": {"round_index": 3, "turn_index": 1}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            initial = ws.receive_json()
            self.assertEqual(initial.get("type"), "view_commit")
            self.assertEqual(initial.get("payload", {}).get("commit_seq"), 9)

            ws.send_json({"type": "resume", "last_commit_seq": 0})
            after_resume = ws.receive_json()

        self.assertEqual(after_resume.get("type"), "view_commit")
        self.assertEqual(after_resume.get("payload", {}).get("commit_seq"), 9)

    def test_heartbeat_periodically_resends_latest_view_commit_for_client_repair(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 30311, "visibility": "public"})
        _save_cached_view_commit(
            session.session_id,
            commit_seq=11,
            source_event_seq=10,
            view_state={"turn_stage": {"round_index": 4, "turn_index": 2}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            initial = ws.receive_json()
            self.assertEqual(initial.get("type"), "view_commit")
            self.assertEqual(initial.get("payload", {}).get("commit_seq"), 11)

            repair: dict | None = None
            for _ in range(8):
                msg = ws.receive_json()
                if msg.get("type") == "view_commit":
                    repair = msg
                    break

        self.assertIsNotNone(repair)
        self.assertEqual(repair.get("payload", {}).get("commit_seq"), 11)

    def test_sender_suppresses_stale_view_commit_after_latest_snapshot(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 3032, "visibility": "public"})
        cached = _save_cached_view_commit(
            session.session_id,
            commit_seq=5,
            source_event_seq=4,
            view_state={"turn_stage": {"round_index": 2, "turn_index": 0}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            initial = ws.receive_json()
            self.assertEqual(initial.get("type"), "view_commit")
            self.assertEqual(initial.get("payload", {}).get("commit_seq"), 5)

            stale = dict(cached)
            stale["commit_seq"] = 4
            asyncio.run(state.stream_service.publish_view_commit(session.session_id, stale))
            messages = [ws.receive_json() for _ in range(4)]

        delivered_commit_seqs = [
            int(message.get("payload", {}).get("commit_seq", 0) or 0)
            for message in messages
            if message.get("type") == "view_commit"
        ]
        self.assertNotIn(4, delivered_commit_seqs)

    def test_resume_snapshot_without_runtime_transition(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 304, "visibility": "public"})

        async def _seed() -> None:
            await state.stream_service.publish(session.session_id, "event", {"event_type": "round_start", "round_index": 1})
            await state.stream_service.publish(session.session_id, "event", {"event_type": "turn_start", "turn_index": 1})

        asyncio.run(_seed())
        _save_cached_view_commit(
            session.session_id,
            commit_seq=4,
            source_event_seq=3,
            view_state={"turn_stage": {"round_index": 1, "turn_index": 1}},
        )

        transition_calls: list[str] = []
        original_once = state.runtime_service._run_engine_transition_once_sync

        def _fail_transition(*args, **kwargs):  # type: ignore[no-untyped-def]
            transition_calls.append("transition")
            raise AssertionError("resume must not advance runtime")

        state.runtime_service._run_engine_transition_once_sync = _fail_transition  # type: ignore[method-assign]
        try:
            path = f"/api/v1/sessions/{session.session_id}/stream"
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_commit_seq": 0})
                commit: dict | None = None
                for _ in range(8):
                    msg = ws.receive_json()
                    if msg.get("type") != "view_commit":
                        continue
                    commit = msg
                    if msg.get("payload", {}).get("commit_seq") == 4:
                        break
        finally:
            state.runtime_service._run_engine_transition_once_sync = original_once  # type: ignore[method-assign]

        self.assertIsNotNone(commit)
        self.assertEqual(commit.get("payload", {}).get("source_event_seq"), 3)
        self.assertEqual(transition_calls, [])

    def test_connection_uses_latest_view_commit_instead_of_stream_catch_up(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 305, "visibility": "public"})

        _save_cached_view_commit(
            session.session_id,
            commit_seq=6,
            source_event_seq=5,
            viewer="player",
            player_id=1,
            seat=1,
            view_state={
                "prompt": {
                    "active": {
                        "request_id": "r_seat1",
                        "request_type": "final_character",
                        "player_id": 1,
                        "legal_choices": [{"choice_id": "6", "label": "박수"}],
                    }
                },
                "turn_stage": {"round_index": 1, "turn_index": 0},
            },
            runtime={
                "status": "waiting_input",
                "round_index": 1,
                "turn_index": 0,
                "active_frame_id": "round:test:draft:p1",
                "active_module_id": "round:test:draft:p1:prompt",
                "active_module_type": "DraftModule",
                "module_path": ["round:test:draft:p1", "round:test:draft:p1:prompt"],
            },
        )

        latest = asyncio.run(
            state.stream_service.latest_view_commit_message_for_viewer(
                session.session_id,
                ViewerContext(role="seat", session_id=session.session_id, player_id=1),
            )
        )

        self.assertIsNotNone(latest)
        self.assertEqual(latest.get("type"), "view_commit")
        self.assertEqual(latest.get("payload", {}).get("commit_seq"), 6)
        self.assertEqual(latest.get("payload", {}).get("source_event_seq"), 5)
        self.assertEqual(
            latest.get("payload", {}).get("view_state", {}).get("prompt", {}).get("active", {}).get("legal_choices"),
            [{"choice_id": "6", "label": "박수"}],
        )

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
                    "view_commit_seq_seen": 0,
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

    def test_seat_decision_repairs_missing_pending_prompt_from_latest_view_commit(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 19})
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=session.join_tokens[1])
        session_token = joined["session_token"]
        view_commit = _save_cached_view_commit(
            session.session_id,
            commit_seq=7,
            source_event_seq=11,
            viewer="player",
            player_id=1,
            seat=1,
            view_state={
                "turn_stage": {"round_index": 1, "turn_index": 2},
                "prompt": {
                    "active": {
                        "request_id": "r_repair_from_commit_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 5000,
                        "prompt_instance_id": 3,
                        "choices": [{"choice_id": "roll", "label": "Roll"}],
                        "public_context": {"round_index": 1, "turn_index": 2},
                    }
                },
            },
        )
        asyncio.run(state.stream_service.publish_view_commit(session.session_id, view_commit))

        path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
        with self.client.websocket_connect(path) as ws:
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_repair_from_commit_1",
                    "player_id": 1,
                    "choice_id": "roll",
                    "choice_payload": {},
                    "prompt_instance_id": 3,
                    "view_commit_seq_seen": 7,
                }
            )

            messages: list[dict] = []
            for _ in range(10):
                msg = ws.receive_json()
                messages.append(msg)
                if (
                    msg.get("type") == "decision_ack"
                    and msg.get("payload", {}).get("request_id") == "r_repair_from_commit_1"
                ):
                    break

        acks = [
            m
            for m in messages
            if m.get("type") == "decision_ack" and m.get("payload", {}).get("request_id") == "r_repair_from_commit_1"
        ]
        self.assertGreaterEqual(len(acks), 1)
        self.assertEqual(acks[-1].get("payload", {}).get("status"), "accepted")
        self.assertIsNone(acks[-1].get("payload", {}).get("reason"))

    def test_seat_decision_wakes_runtime_after_accepted_ack(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_seat1_human_others_ai(), config={"seed": 23})
        joined = state.session_service.join_session(session.session_id, seat=1, join_token=session.join_tokens[1])
        session_token = joined["session_token"]
        original_submit = state.prompt_service.submit_decision
        original_process = state.runtime_service.process_command_once
        process_calls: list[tuple[str, int, str, int, str | None]] = []

        def _fake_submit_decision(_message: dict) -> dict:
            return {
                "status": "accepted",
                "reason": None,
                "session_id": session.session_id,
                "command_seq": 42,
            }

        async def _fake_process_command_once(
            *,
            session_id: str,
            command_seq: int,
            consumer_name: str,
            seed: int,
            policy_mode: str | None = None,
        ) -> dict:
            process_calls.append((session_id, command_seq, consumer_name, seed, policy_mode))
            return {"status": "committed"}

        state.prompt_service.submit_decision = _fake_submit_decision  # type: ignore[method-assign]
        state.runtime_service.process_command_once = _fake_process_command_once  # type: ignore[method-assign]
        try:
            path = f"/api/v1/sessions/{session.session_id}/stream?token={session_token}"
            with self.client.websocket_connect(path) as ws:
                ws.send_json(
                    {
                        "type": "decision",
                        "request_id": "r_wakeup_1",
                        "player_id": 1,
                        "choice_id": "roll",
                        "choice_payload": {},
                        "view_commit_seq_seen": 0,
                    }
                )

                messages: list[dict] = []
                for _ in range(10):
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "decision_ack" and msg.get("payload", {}).get("request_id") == "r_wakeup_1":
                        break
        finally:
            state.prompt_service.submit_decision = original_submit  # type: ignore[method-assign]
            state.runtime_service.process_command_once = original_process  # type: ignore[method-assign]

        acks = [m for m in messages if m.get("type") == "decision_ack" and m.get("payload", {}).get("request_id") == "r_wakeup_1"]
        self.assertGreaterEqual(len(acks), 1)
        self.assertEqual(acks[-1].get("payload", {}).get("status"), "accepted")
        self.assertEqual(process_calls, [(session.session_id, 42, "runtime_wakeup", 23, None)])

    def test_accepted_decision_schedules_runtime_wakeup_without_awaiting_processing(self) -> None:
        from apps.server.src.routes import stream

        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        calls: list[tuple[str, int, str, int, str | None]] = []

        class _Session:
            config = {"seed": 31}
            resolved_parameters = {"runtime": {}}

        class _SessionService:
            def get_session(self, _session_id: str) -> _Session:
                return _Session()

        class _RuntimeService:
            async def process_command_once(
                self,
                *,
                session_id: str,
                command_seq: int,
                consumer_name: str,
                seed: int,
                policy_mode: str | None = None,
            ) -> dict:
                started.set()
                await release.wait()
                calls.append((session_id, command_seq, consumer_name, seed, policy_mode))
                finished.set()
                return {"status": "committed"}

        async def _scenario() -> None:
            schedule_task = asyncio.create_task(
                stream._wake_runtime_after_accepted_decision(
                    decision_state={
                        "status": "accepted",
                        "session_id": "sess_async_wakeup",
                        "command_seq": 77,
                    },
                    session_id="sess_async_wakeup",
                    session_service=_SessionService(),
                    runtime_service=_RuntimeService(),
                )
            )
            await asyncio.wait_for(schedule_task, timeout=0.05)
            await asyncio.wait_for(started.wait(), timeout=0.05)
            self.assertFalse(finished.is_set())
            release.set()
            await asyncio.wait_for(finished.wait(), timeout=0.2)

        asyncio.run(_scenario())
        self.assertEqual(calls, [("sess_async_wakeup", 77, "runtime_wakeup", 31, None)])

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
                    "view_commit_seq_seen": 0,
                }
            )
            ws.send_json(
                {
                    "type": "decision",
                    "request_id": "r_retry_1",
                    "player_id": 1,
                    "choice_id": "roll",
                    "choice_payload": {},
                    "view_commit_seq_seen": 0,
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

    def test_resume_returns_latest_view_commit_parameter_manifest_change(self) -> None:
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
        _save_cached_view_commit(
            session.session_id,
            commit_seq=3,
            source_event_seq=3,
            view_state={"parameter_manifest": {"manifest_hash": "hash_new"}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})
            commit: dict | None = None
            for _ in range(4):
                msg = ws.receive_json()
                if msg.get("type") != "view_commit":
                    continue
                commit = msg
                if msg.get("payload", {}).get("view_state", {}).get("parameter_manifest", {}).get("manifest_hash") == "hash_new":
                    break

        self.assertIsNotNone(commit)
        self.assertEqual(commit.get("payload", {}).get("view_state", {}).get("parameter_manifest", {}).get("manifest_hash"), "hash_new")

    def test_resume_returns_flat_parameter_manifest_shape_without_mutation(self) -> None:
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
        _save_cached_view_commit(
            session.session_id,
            commit_seq=3,
            source_event_seq=3,
            view_state={"parameter_manifest": {"manifest_hash": "flat_hash_new", "board": {"tile_count": 40}}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})
            manifest: dict = {}
            for _ in range(4):
                msg = ws.receive_json()
                if msg.get("type") != "view_commit":
                    continue
                manifest = msg.get("payload", {}).get("view_state", {}).get("parameter_manifest", {})
                if manifest.get("manifest_hash") == "flat_hash_new":
                    break

        self.assertEqual(manifest.get("manifest_hash"), "flat_hash_new")
        self.assertEqual(manifest.get("board", {}).get("tile_count"), 40)

    def test_resume_does_not_replay_decision_event_order_for_live_ui(self) -> None:
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
        _save_cached_view_commit(
            session.session_id,
            commit_seq=4,
            source_event_seq=5,
            view_state={"board": {"players": [{"player_id": 1, "tile_index": 5}]}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})
            commit: dict | None = None
            replayed_events: list[dict] = []
            for _ in range(8):
                msg = ws.receive_json()
                if msg.get("type") == "event":
                    replayed_events.append(msg)
                if msg.get("type") == "view_commit":
                    commit = msg
                if commit is not None:
                    break

        self.assertEqual(replayed_events, [])
        self.assertIsNotNone(commit)
        self.assertEqual(commit.get("payload", {}).get("source_event_seq"), 5)

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

        seat1_viewer = ViewerContext(role="seat", player_id=1)
        seat2_viewer = ViewerContext(role="seat", player_id=2)
        spectator_viewer = ViewerContext(role="spectator")

        self.assertIsNotNone(project_stream_message_for_viewer(draft_requested, seat1_viewer))
        self.assertIsNone(project_stream_message_for_viewer(draft_requested, seat2_viewer))
        self.assertIsNone(project_stream_message_for_viewer(draft_requested, spectator_viewer))

        self.assertIsNotNone(project_stream_message_for_viewer(draft_resolved, seat1_viewer))
        self.assertIsNone(project_stream_message_for_viewer(draft_resolved, seat2_viewer))
        self.assertIsNone(project_stream_message_for_viewer(draft_resolved, spectator_viewer))

        filtered_seat2_draft = project_stream_message_for_viewer(draft_pick, seat2_viewer)
        filtered_spectator_draft = project_stream_message_for_viewer(draft_pick, spectator_viewer)
        self.assertIsNotNone(filtered_seat2_draft)
        self.assertIsNotNone(filtered_spectator_draft)
        self.assertNotIn("picked_card", filtered_seat2_draft["payload"])
        self.assertNotIn("picked_card", filtered_spectator_draft["payload"])

        self.assertIsNotNone(project_stream_message_for_viewer(final_choice, seat1_viewer))
        self.assertIsNone(project_stream_message_for_viewer(final_choice, seat2_viewer))
        self.assertIsNone(project_stream_message_for_viewer(final_choice, spectator_viewer))

    def test_resume_view_commit_includes_manifest_with_non_default_topology_and_seat_profile(self) -> None:
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
        _save_cached_view_commit(
            session_id,
            commit_seq=1,
            source_event_seq=1,
            view_state={"parameter_manifest": started.json()["data"]["parameter_manifest"]},
        )

        path = f"/api/v1/sessions/{session_id}/stream"
        with self.client.websocket_connect(path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})
            manifest: dict = {}
            for _ in range(80):
                msg = ws.receive_json()
                if msg.get("type") != "view_commit":
                    continue
                manifest = msg.get("payload", {}).get("view_state", {}).get("parameter_manifest", {})
                if manifest:
                    break

        self.assertEqual(manifest.get("manifest_hash"), expected_hash)
        self.assertEqual(manifest.get("board", {}).get("topology"), "line")
        self.assertEqual(manifest.get("seats", {}).get("allowed"), [1, 2, 3])

    def test_reconnect_sends_latest_manifest_view_commit_after_hash_change_end_to_end(self) -> None:
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
        first_manifest = started.json()["data"]["parameter_manifest"]
        _save_cached_view_commit(
            session_id,
            commit_seq=1,
            source_event_seq=1,
            view_state={"parameter_manifest": first_manifest},
        )

        first_commit_seq = 0
        ws_path = f"/api/v1/sessions/{session_id}/stream"
        with self.client.websocket_connect(ws_path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": 0})
            for _ in range(120):
                msg = ws.receive_json()
                if msg.get("type") != "view_commit":
                    continue
                manifest = msg.get("payload", {}).get("view_state", {}).get("parameter_manifest", {})
                if manifest.get("manifest_hash"):
                    first_commit_seq = int(msg.get("payload", {}).get("commit_seq", 0))
                    break

        self.assertGreater(first_commit_seq, 0)

        _save_cached_view_commit(
            session_id,
            commit_seq=2,
            source_event_seq=2,
            view_state={
                "parameter_manifest": {
                    "manifest_hash": "hash_e2e_changed",
                    "board": {"topology": "line", "tile_count": 40},
                    "seats": {"allowed": [1, 2, 3]},
                }
            },
        )

        with self.client.websocket_connect(ws_path) as ws:
            ws.send_json({"type": "resume", "last_commit_seq": first_commit_seq})
            changed_manifest: dict = {}
            for _ in range(80):
                msg = ws.receive_json()
                if msg.get("type") != "view_commit":
                    continue
                changed_manifest = msg.get("payload", {}).get("view_state", {}).get("parameter_manifest", {})
                if changed_manifest.get("manifest_hash") == "hash_e2e_changed":
                    break

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

    def test_reconnect_soak_preserves_latest_commit_monotonicity_across_multiple_resumes(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(_all_ai_seats(), config={"seed": 303, "visibility": "public"})

        _save_cached_view_commit(
            session.session_id,
            commit_seq=24,
            source_event_seq=12,
            view_state={"turn_stage": {"round_index": 12, "turn_index": 0}},
        )

        path = f"/api/v1/sessions/{session.session_id}/stream"

        def _latest_commit_after(last_commit_seq: int, target_latest_commit_seq: int) -> int:
            with self.client.websocket_connect(path) as ws:
                ws.send_json({"type": "resume", "last_commit_seq": last_commit_seq})
                latest_commit_seq = 0
                for _ in range(200):
                    msg = ws.receive_json()
                    if msg.get("type") != "view_commit":
                        continue
                    commit_seq = int(msg.get("payload", {}).get("commit_seq", 0))
                    if commit_seq <= 0:
                        continue
                    latest_commit_seq = commit_seq
                    if commit_seq >= target_latest_commit_seq:
                        break
            return latest_commit_seq

        first_seen = _latest_commit_after(last_commit_seq=0, target_latest_commit_seq=24)
        self.assertEqual(first_seen, 24)

        _save_cached_view_commit(
            session.session_id,
            commit_seq=36,
            source_event_seq=18,
            view_state={"turn_stage": {"round_index": 18, "turn_index": 0}},
        )
        second_seen = _latest_commit_after(last_commit_seq=24, target_latest_commit_seq=36)
        self.assertEqual(second_seen, 36)

        _save_cached_view_commit(
            session.session_id,
            commit_seq=46,
            source_event_seq=23,
            view_state={"turn_stage": {"round_index": 23, "turn_index": 0}},
        )
        third_seen = _latest_commit_after(last_commit_seq=36, target_latest_commit_seq=46)
        self.assertEqual(third_seen, 46)


if __name__ == "__main__":
    unittest.main()
