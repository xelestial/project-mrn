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
from apps.server.src.domain.protocol_identity import assert_no_public_identity_numeric_leaks
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
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


def _reset_state() -> None:
    from apps.server.src import state

    state.runtime_settings = RuntimeSettings()
    state.session_service = SessionService()
    state.stream_service = StreamService()
    state.prompt_service = PromptService()
    state.runtime_service = RuntimeService(
        session_service=state.session_service,
        stream_service=state.stream_service,
        prompt_service=state.prompt_service,
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


def _external_ai_payload() -> dict:
    return {
        "seats": [
            {
                "seat": 1,
                "seat_type": "ai",
                "ai_profile": "balanced",
                "participant_client": "external_ai",
                "participant_config": {"endpoint": "http://bot-worker.local/seat-1"},
            },
            {"seat": 2, "seat_type": "human"},
        ],
        "config": {
            "seed": 42,
            "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
            "participants": {
                "external_ai": {
                    "transport": "http",
                    "contract_version": "v1",
                    "expected_worker_id": "bot-worker-1",
                    "auth_token": "worker-secret",
                    "auth_header_name": "X-Worker-Auth",
                    "auth_scheme": "Token",
                    "timeout_ms": 9000,
                    "retry_count": 2,
                    "backoff_ms": 100,
                    "fallback_mode": "local_ai",
                    "healthcheck_path": "/health",
                    "healthcheck_ttl_ms": 5000,
                    "required_capabilities": ["choice_id_response", "healthcheck"],
                    "headers": {"Authorization": "Bearer test-token"},
                }
            },
        },
    }


def _priority_scored_external_ai_payload() -> dict:
    return {
        "seats": [
            {
                "seat": 1,
                "seat_type": "ai",
                "ai_profile": "balanced",
                "participant_client": "external_ai",
                "participant_config": {"endpoint": "http://priority-worker.local/seat-1"},
            },
            {"seat": 2, "seat_type": "human"},
        ],
        "config": {
            "seed": 42,
            "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
            "participants": {
                "external_ai": {
                    "transport": "http",
                    "worker_profile": "priority_scored",
                }
            },
        },
    }


def _three_ai_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": 42,
            "seat_limits": {"min": 1, "max": 3, "allowed": [1, 2, 3]},
        },
    }


def _three_ai_line_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": 77,
            "board_topology": "line",
            "seat_limits": {"min": 1, "max": 3, "allowed": [1, 2, 3]},
        },
    }


def _two_seat_matrix_payload() -> dict:
    return {
        "seats": [
            {"seat": 1, "seat_type": "human"},
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": 120,
            "board_topology": "line",
            "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
            "starting_cash": 55,
            "starting_shards": 7,
            "dice_values": [2, 4, 8],
            "dice_max_cards_per_turn": 1,
            "rules": {
                "end": {
                    "f_threshold": 1,
                    "monopolies_to_trigger_end": 0,
                    "tiles_to_trigger_end": 1,
                    "alive_players_at_most": 1,
                }
            },
        },
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class SessionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state()
        self.client = TestClient(app)

    def test_runtime_status_shape(self) -> None:
        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        self.assertIn("parameter_manifest", created_data)
        self.assertIn("initial_active_by_card", created_data)
        self.assertIn("manifest_hash", created_data["parameter_manifest"])
        session_id = created_data["session_id"]

        fetched = self.client.get(f"/api/v1/sessions/{session_id}")
        self.assertEqual(fetched.status_code, 200)
        fetched_data = fetched.json()["data"]
        self.assertIn("parameter_manifest", fetched_data)
        self.assertEqual(fetched_data["initial_active_by_card"], created_data["initial_active_by_card"])
        self.assertEqual(
            fetched_data["parameter_manifest"]["manifest_hash"],
            created_data["parameter_manifest"]["manifest_hash"],
        )

        runtime = self.client.get(f"/api/v1/sessions/{session_id}/runtime-status")
        self.assertEqual(runtime.status_code, 200)
        payload = runtime.json()["data"]["runtime"]
        self.assertIn("status", payload)

    def test_private_session_replay_and_runtime_status_require_token(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()["error"]["code"], "SPECTATOR_NOT_ALLOWED")

        runtime = self.client.get(f"/api/v1/sessions/{session_id}/runtime-status")
        self.assertEqual(runtime.status_code, 401)
        self.assertEqual(runtime.json()["error"]["code"], "SPECTATOR_NOT_ALLOWED")

        replay_with_token = self.client.get(f"/api/v1/sessions/{session_id}/replay", params={"token": session_token})
        self.assertEqual(replay_with_token.status_code, 200)
        runtime_with_token = self.client.get(
            f"/api/v1/sessions/{session_id}/runtime-status",
            params={"token": session_token},
        )
        self.assertEqual(runtime_with_token.status_code, 200)

    def test_authenticated_runtime_status_starts_recovery_runtime(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
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
                json={"host_token": data["host_token"]},
            )
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)
        self.assertEqual(state.runtime_service.runtime_status(session_id).get("status"), "recovery_required")

        calls: list[tuple[str, int, str | None]] = []

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            calls.append((session_id, seed, policy_mode))

        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        try:
            response = self.client.get(
                f"/api/v1/sessions/{session_id}/runtime-status",
                params={"token": session_token},
            )
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [(session_id, 120, None)])

    def test_authenticated_runtime_status_defers_recovery_when_commands_are_unprocessed(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        original_start = state.runtime_service.start_runtime
        original_has_commands = state.command_recovery_service.has_unprocessed_runtime_commands

        async def _noop_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            del session_id, seed, policy_mode

        state.runtime_service.start_runtime = _noop_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": data["host_token"]},
            )
        finally:
            state.runtime_service.start_runtime = original_start  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)
        self.assertEqual(state.runtime_service.runtime_status(session_id).get("status"), "recovery_required")

        calls: list[tuple[str, int, str | None]] = []

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            calls.append((session_id, seed, policy_mode))

        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        state.command_recovery_service.has_unprocessed_runtime_commands = lambda _session_id: True  # type: ignore[method-assign]
        try:
            response = self.client.get(
                f"/api/v1/sessions/{session_id}/runtime-status",
                params={"token": session_token},
            )
        finally:
            state.runtime_service.start_runtime = original_start  # type: ignore[assignment]
            state.command_recovery_service.has_unprocessed_runtime_commands = original_has_commands  # type: ignore[method-assign]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [])

    def test_authenticated_runtime_status_defers_pending_command_before_plain_recovery(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        original_start = state.runtime_service.start_runtime
        original_pending = state.command_recovery_service.pending_resume_command
        async def _noop_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            del session_id, seed, policy_mode

        state.runtime_service.start_runtime = _noop_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": data["host_token"]},
            )
        finally:
            state.runtime_service.start_runtime = original_start  # type: ignore[assignment]
        self.assertEqual(started.status_code, 200)
        self.assertEqual(state.runtime_service.runtime_status(session_id).get("status"), "recovery_required")

        start_calls: list[tuple[str, int, str | None]] = []

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            start_calls.append((session_id, seed, policy_mode))

        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        state.command_recovery_service.pending_resume_command = lambda _session_id: {"seq": 7, "type": "decision_submitted"}  # type: ignore[method-assign]
        try:
            response = self.client.get(
                f"/api/v1/sessions/{session_id}/runtime-status",
                params={"token": session_token},
            )
        finally:
            state.runtime_service.start_runtime = original_start  # type: ignore[assignment]
            state.command_recovery_service.pending_resume_command = original_pending  # type: ignore[method-assign]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_calls, [])

    def test_authenticated_runtime_status_does_not_start_recovery_for_waiting_checkpoint(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        original_status = state.runtime_service.runtime_status
        original_pending = state.command_recovery_service.pending_resume_command
        original_start = state.runtime_service.start_runtime
        start_calls: list[tuple[str, int, str | None]] = []

        def _fake_runtime_status(_session_id: str) -> dict:
            return {
                "status": "recovery_required",
                "reason": "runtime_task_missing_after_restart",
                "recovery_checkpoint": {
                    "available": True,
                    "checkpoint": {
                        "waiting_prompt_request_id": f"{session_id}:r1:t1:p1:hidden_trick_card:65",
                        "waiting_prompt_player_id": 1,
                        "runtime_active_prompt": {
                            "request_id": f"{session_id}:r1:t1:p1:hidden_trick_card:65",
                            "request_type": "hidden_trick_card",
                            "player_id": 1,
                            "legal_choices": [{"choice_id": "use_trick"}],
                        },
                    },
                    "current_state": {"tiles": [], "players": []},
                },
            }

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            start_calls.append((session_id, seed, policy_mode))

        state.runtime_service.runtime_status = _fake_runtime_status  # type: ignore[method-assign]
        state.command_recovery_service.pending_resume_command = lambda _session_id: None  # type: ignore[method-assign]
        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        try:
            response = self.client.get(
                f"/api/v1/sessions/{session_id}/runtime-status",
                params={"token": session_token},
            )
        finally:
            state.runtime_service.runtime_status = original_status  # type: ignore[method-assign]
            state.command_recovery_service.pending_resume_command = original_pending  # type: ignore[method-assign]
            state.runtime_service.start_runtime = original_start  # type: ignore[assignment]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_calls, [])

    def test_authenticated_runtime_status_defers_waiting_input_pending_command(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        session_id = data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        original_status = state.runtime_service.runtime_status
        original_pending = state.command_recovery_service.pending_resume_command

        def _fake_runtime_status(_session_id: str) -> dict:
            return {"status": "waiting_input", "reason": "pending_human_decision"}

        state.runtime_service.runtime_status = _fake_runtime_status  # type: ignore[method-assign]
        state.command_recovery_service.pending_resume_command = lambda _session_id: {"seq": 9, "type": "decision_submitted"}  # type: ignore[method-assign]
        try:
            response = self.client.get(
                f"/api/v1/sessions/{session_id}/runtime-status",
                params={"token": session_token},
            )
        finally:
            state.runtime_service.runtime_status = original_status  # type: ignore[method-assign]
            state.command_recovery_service.pending_resume_command = original_pending  # type: ignore[method-assign]

        self.assertEqual(response.status_code, 200)

    def test_public_session_allows_spectator_replay_and_runtime_status(self) -> None:
        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["data"]["session_id"]

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["data"]["visibility"], "spectator")

        runtime = self.client.get(f"/api/v1/sessions/{session_id}/runtime-status")
        self.assertEqual(runtime.status_code, 200)

    def test_create_session_exposes_participant_client_descriptor(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_external_ai_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        ai_seat = next(seat for seat in data["seats"] if seat["seat"] == 1)
        self.assertEqual(ai_seat["participant_client"], "external_ai")
        self.assertEqual(ai_seat["participant_config"]["transport"], "http")
        self.assertEqual(ai_seat["participant_config"]["contract_version"], "v1")
        self.assertEqual(ai_seat["participant_config"]["expected_worker_id"], "bot-worker-1")
        self.assertEqual(ai_seat["participant_config"]["auth_token"], "worker-secret")
        self.assertEqual(ai_seat["participant_config"]["auth_header_name"], "X-Worker-Auth")
        self.assertEqual(ai_seat["participant_config"]["auth_scheme"], "Token")
        self.assertEqual(ai_seat["participant_config"]["timeout_ms"], 9000)
        self.assertEqual(ai_seat["participant_config"]["retry_count"], 2)
        self.assertEqual(ai_seat["participant_config"]["backoff_ms"], 100)
        self.assertEqual(ai_seat["participant_config"]["fallback_mode"], "local_ai")
        self.assertEqual(ai_seat["participant_config"]["healthcheck_path"], "/health")
        self.assertEqual(ai_seat["participant_config"]["healthcheck_ttl_ms"], 5000)
        self.assertEqual(ai_seat["participant_config"]["required_capabilities"], ["choice_id_response", "healthcheck"])
        self.assertEqual(ai_seat["participant_config"]["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(ai_seat["participant_config"]["endpoint"], "http://bot-worker.local/seat-1")

    def test_create_session_exposes_worker_profile_driven_external_defaults(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_priority_scored_external_ai_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        ai_seat = next(seat for seat in data["seats"] if seat["seat"] == 1)
        self.assertEqual(ai_seat["participant_client"], "external_ai")
        self.assertEqual(ai_seat["participant_config"]["worker_profile"], "priority_scored")
        self.assertEqual(ai_seat["participant_config"]["required_worker_adapter"], "priority_score_v1")
        self.assertEqual(ai_seat["participant_config"]["required_policy_class"], "PriorityScoredPolicy")
        self.assertEqual(ai_seat["participant_config"]["required_decision_style"], "priority_scored_contract")
        self.assertIn("priority_scored_choice", ai_seat["participant_config"]["required_capabilities"])

    def test_get_missing_session_returns_normalized_error_category(self) -> None:
        missing = self.client.get("/api/v1/sessions/sess_missing_404")
        self.assertEqual(missing.status_code, 404)
        error = missing.json().get("error", {})
        self.assertEqual(error.get("code"), "SESSION_NOT_FOUND")
        self.assertEqual(error.get("category"), "session")
        self.assertFalse(error.get("retryable"))

    def test_create_session_supports_non_default_seat_profile(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_three_ai_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        self.assertEqual(len(data["seats"]), 3)
        manifest = data["parameter_manifest"]
        self.assertEqual(manifest["seats"]["max"], 3)
        self.assertEqual(manifest["seats"]["allowed"], [1, 2, 3])

    def test_create_session_supports_non_default_seat_and_topology_profile(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_three_ai_line_payload())
        self.assertEqual(created.status_code, 200)
        data = created.json()["data"]
        self.assertEqual(len(data["seats"]), 3)
        manifest = data["parameter_manifest"]
        self.assertEqual(manifest["seats"]["max"], 3)
        self.assertEqual(manifest["seats"]["allowed"], [1, 2, 3])
        self.assertEqual(manifest["board"]["topology"], "line")

    def test_create_session_rejects_invalid_board_topology(self) -> None:
        payload = _three_ai_payload()
        payload["config"]["board_topology"] = "hex"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 400)

    def test_replay_endpoint_returns_buffered_messages(self) -> None:
        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        session_id = created.json()["data"]["session_id"]

        async def _seed_events() -> None:
            from apps.server.src import state

            await state.stream_service.publish(
                session_id,
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "snapshot": {
                        "players": [
                            {"player_id": 1},
                            {"player_id": 2},
                            {"player_id": 3},
                            {"player_id": 4},
                        ],
                        "board": {
                            "marker_owner_player_id": 2,
                        },
                    },
                },
            )
            await state.stream_service.publish(session_id, "event", {"event_type": "round_start"})
            await state.stream_service.publish(session_id, "event", {"event_type": "turn_start"})

        asyncio.run(_seed_events())

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        data = replay.json()["data"]
        self.assertEqual(data["schema_name"], "mrn.redacted_replay_export")
        self.assertEqual(data["visibility"], "spectator")
        self.assertTrue(data["browser_safe"])
        self.assertEqual(data["event_count"], 4)
        source_events = [event for event in data["events"] if event.get("type") == "event"]
        view_commits = [event for event in data["events"] if event.get("type") == "view_commit"]
        self.assertEqual([event.get("payload", {}).get("event_type") for event in source_events], [
            "session_created",
            "turn_end_snapshot",
            "round_start",
            "turn_start",
        ])
        self.assertEqual(view_commits, [])
        self.assertIn("server_time_ms", data["events"][0])
        self.assertNotIn("view_state", source_events[-1].get("payload", {}))
        self.assertNotIn("view_state", data)
        self.assertNotIn("final_state", data)
        self.assertNotIn("streams", data)
        self.assertNotIn("analysis", data)

    def test_view_commit_endpoint_returns_cached_view_state_for_authenticated_seat(self) -> None:
        payload = _two_seat_matrix_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        join_token = created_data["join_tokens"]["1"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": join_token, "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        _save_cached_view_commit(
            session_id,
            commit_seq=1,
            source_event_seq=1,
            view_state={"board": {"round": 1}},
        )
        _save_cached_view_commit(
            session_id,
            commit_seq=1,
            source_event_seq=1,
            viewer="player",
            player_id=1,
            seat=1,
            view_state={
                "board": {"round": 1},
                "prompt": {
                    "active": {
                        "request_id": "req_trick",
                        "request_type": "trick_to_use",
                        "player_id": 1,
                        "legal_choices": [{"choice_id": "card-11", "title": "재뿌리기"}],
                    }
                },
                "hand_tray": {"cards": [{"deck_index": 11, "name": "재뿌리기", "is_usable": True}]},
            },
            runtime={
                "status": "waiting_input",
                "round_index": 1,
                "turn_index": 0,
                "active_frame_id": "frame:prompt",
                "active_module_id": "module:prompt",
                "active_module_type": "TrickPromptModule",
                "module_path": ["frame:prompt", "module:prompt"],
            },
        )

        spectator = self.client.get(f"/api/v1/sessions/{session_id}/view-commit")
        self.assertEqual(spectator.status_code, 200)
        spectator_data = spectator.json()["data"]
        self.assertEqual(spectator_data["viewer"]["role"], "spectator")
        self.assertNotIn("prompt", spectator_data["view_state"])
        self.assertNotIn("hand_tray", spectator_data["view_state"])

        seat = self.client.get(f"/api/v1/sessions/{session_id}/view-commit?token={session_token}")
        self.assertEqual(seat.status_code, 200)
        seat_data = seat.json()["data"]
        self.assertEqual(seat_data["viewer"]["player_id"], 1)
        self.assertEqual(seat_data["view_state"]["prompt"]["active"]["request_id"], "req_trick")
        self.assertEqual(seat_data["view_state"]["hand_tray"]["cards"][0]["name"], "재뿌리기")

    def test_view_commit_endpoint_returns_404_without_cached_commit(self) -> None:
        payload = _two_seat_matrix_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        session_id = created.json()["data"]["session_id"]

        response = self.client.get(f"/api/v1/sessions/{session_id}/view-commit")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "VIEW_COMMIT_NOT_FOUND")

    def test_replay_endpoint_uses_single_snapshot_projection_path(self) -> None:
        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        session_id = created.json()["data"]["session_id"]

        async def _seed_many_events() -> None:
            from apps.server.src import state

            await state.stream_service.publish(
                session_id,
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "snapshot": {
                        "players": [{"player_id": 1}, {"player_id": 2}],
                        "board": {"marker_owner_player_id": 1},
                    },
                },
            )
            for index in range(20):
                await state.stream_service.publish(
                    session_id,
                    "event",
                    {"event_type": "turn_start", "turn_index": index + 1},
                )

        asyncio.run(_seed_many_events())

        from apps.server.src import state

        original = state.stream_service.project_message_for_viewer

        async def _fail_per_message_projection(*_args, **_kwargs):
            raise AssertionError("replay export must not rebuild projection per event")

        state.stream_service.project_message_for_viewer = _fail_per_message_projection  # type: ignore[method-assign]
        try:
            replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        finally:
            state.stream_service.project_message_for_viewer = original  # type: ignore[method-assign]

        self.assertEqual(replay.status_code, 200)
        data = replay.json()["data"]
        self.assertEqual(data["event_count"], 22)
        self.assertNotIn("view_state", data)
        self.assertEqual(data["events"][-1].get("type"), "event")
        self.assertNotIn("view_state", data["events"][-1].get("payload", {}))

    def test_runtime_status_does_not_return_live_view_state_for_authenticated_seat(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        joined = self.client.post(
            f"/api/v1/sessions/{session_id}/join",
            json={"seat": 1, "join_token": created_data["join_tokens"]["1"], "display_name": "P1"},
        )
        self.assertEqual(joined.status_code, 200)
        session_token = joined.json()["data"]["session_token"]

        async def _seed_private_prompt() -> None:
            from apps.server.src import state

            await state.stream_service.publish(
                session_id,
                "prompt",
                module_prompt({
                    "request_id": "req_runtime_trick",
                    "request_type": "trick_to_use",
                    "player_id": 1,
                    "legal_choices": [{"choice_id": "card-11", "title": "재뿌리기"}],
                    "public_context": {
                        "full_hand": [{"deck_index": 11, "name": "재뿌리기", "is_usable": True}],
                    },
                }),
            )

        asyncio.run(_seed_private_prompt())

        runtime = self.client.get(
            f"/api/v1/sessions/{session_id}/runtime-status",
            params={"token": session_token},
        )

        self.assertEqual(runtime.status_code, 200)
        recovery = runtime.json()["data"]["runtime"].get("recovery_checkpoint", {})
        self.assertNotIn("view_state", recovery)

    def test_replay_endpoint_rejects_invalid_session_token(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        session_id = created.json()["data"]["session_id"]

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay?token=bad-token")

        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()["error"]["code"], "INVALID_SESSION_TOKEN")

    def test_debug_prompt_requires_admin_token(self) -> None:
        from apps.server.src import state

        state.runtime_settings = RuntimeSettings(admin_token="admin-secret")
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        session_id = created.json()["data"]["session_id"]
        payload = {
            "request_id": "debug_req",
            "request_type": "debug_choice",
            "player_id": 1,
            "choices": [{"choice_id": "ok", "label": "OK"}],
        }

        rejected = self.client.post(f"/api/v1/sessions/{session_id}/prompts/debug", json=payload)
        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(rejected.json()["error"]["code"], "ADMIN_UNAUTHORIZED")

        accepted = self.client.post(
            f"/api/v1/sessions/{session_id}/prompts/debug",
            json=payload,
            headers={"X-Admin-Token": "admin-secret"},
        )
        self.assertEqual(accepted.status_code, 200)

    def test_external_ai_decision_callback_accepts_prompt_and_wakes_runtime(self) -> None:
        from apps.server.src import state

        class _RecordingCommandRouter:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def wake_after_accept(self, *, command_ref: dict, session_id: str, trigger: str) -> dict:
                self.calls.append(
                    {
                        "command_ref": dict(command_ref),
                        "session_id": session_id,
                        "trigger": trigger,
                    }
                )
                return {"status": "scheduled", "command_seq": command_ref.get("command_seq")}

        router = _RecordingCommandRouter()
        state.runtime_settings = RuntimeSettings(admin_token="admin-secret")
        state.command_router = router  # type: ignore[assignment]
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        session_data = created.json()["data"]
        session_id = session_data["session_id"]
        seat = session_data["seats"][0]
        state.prompt_service.create_prompt(
            session_id,
            {
                "request_id": "ai_req_1",
                "request_type": "movement",
                "player_id": 1,
                "provider": "ai",
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )

        accepted = self.client.post(
            f"/api/v1/sessions/{session_id}/external-ai/decisions",
            json={"request_id": "ai_req_1", "player_id": 1, "choice_id": "roll"},
            headers={"X-Admin-Token": "admin-secret"},
        )

        self.assertEqual(accepted.status_code, 200)
        data = accepted.json()["data"]
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(router.calls[0]["session_id"], session_id)
        self.assertEqual(router.calls[0]["trigger"], "accepted_decision")
        snapshot = asyncio.run(state.stream_service.snapshot(session_id))
        ack = next(message for message in snapshot if message.type == "decision_ack")
        self.assertEqual(ack.payload["provider"], "ai")
        self.assertEqual(ack.payload["request_id"], "ai_req_1")
        self.assertEqual(ack.payload["player_id_alias_role"], "legacy_compatibility_alias")
        self.assertEqual(ack.payload["primary_player_id"], seat["public_player_id"])
        self.assertEqual(ack.payload["primary_player_id_source"], "public")

    def test_external_ai_decision_callback_accepts_public_player_and_request_identity(self) -> None:
        from apps.server.src import state

        state.runtime_settings = RuntimeSettings(admin_token="admin-secret")
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        session_data = created.json()["data"]
        session_id = session_data["session_id"]
        seat = session_data["seats"][0]
        public_player_id = seat["public_player_id"]
        pending = state.prompt_service.create_prompt(
            session_id,
            {
                "request_id": "ai_req_public_1",
                "request_type": "movement",
                "player_id": 1,
                "provider": "ai",
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )
        public_request_id = str(pending.payload["public_request_id"])

        accepted = self.client.post(
            f"/api/v1/sessions/{session_id}/external-ai/decisions",
            json={
                "request_id": public_request_id,
                "public_player_id": public_player_id,
                "choice_id": "roll",
            },
            headers={"X-Admin-Token": "admin-secret"},
        )

        self.assertEqual(accepted.status_code, 200)
        data = accepted.json()["data"]
        self.assertEqual(data["status"], "accepted")
        snapshot = asyncio.run(state.stream_service.snapshot(session_id))
        ack = next(message for message in snapshot if message.type == "decision_ack")
        self.assertEqual(ack.payload["provider"], "ai")
        self.assertEqual(ack.payload["request_id"], public_request_id)
        self.assertEqual(ack.payload["player_id"], 1)
        self.assertEqual(ack.payload["player_id_alias_role"], "legacy_compatibility_alias")
        self.assertEqual(ack.payload["primary_player_id"], seat["public_player_id"])
        self.assertEqual(ack.payload["primary_player_id_source"], "public")
        self.assertEqual(ack.payload["public_player_id"], seat["public_player_id"])
        self.assertEqual(ack.payload["seat_id"], seat["seat_id"])
        self.assertEqual(ack.payload["viewer_id"], seat["viewer_id"])
        assert_no_public_identity_numeric_leaks(ack.payload, boundary="external_ai_decision_ack")
        decision = state.prompt_service.wait_for_decision("ai_req_public_1", timeout_ms=0, session_id=session_id)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["request_id"], public_request_id)
        self.assertEqual(decision["legacy_request_id"], "ai_req_public_1")
        self.assertEqual(decision["public_request_id"], public_request_id)
        assert_no_public_identity_numeric_leaks(decision, boundary="external_ai_decision_record")

    def test_external_ai_decision_callback_accepts_top_level_public_player_id(self) -> None:
        from apps.server.src import state

        state.runtime_settings = RuntimeSettings(admin_token="admin-secret")
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        session_data = created.json()["data"]
        session_id = session_data["session_id"]
        seat = session_data["seats"][0]
        public_player_id = seat["public_player_id"]
        pending = state.prompt_service.create_prompt(
            session_id,
            {
                "request_id": "ai_req_public_player_top_level_1",
                "request_type": "movement",
                "player_id": 1,
                "provider": "ai",
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )
        public_request_id = str(pending.payload["public_request_id"])

        accepted = self.client.post(
            f"/api/v1/sessions/{session_id}/external-ai/decisions",
            json={
                "request_id": public_request_id,
                "player_id": public_player_id,
                "choice_id": "roll",
            },
            headers={"X-Admin-Token": "admin-secret"},
        )

        self.assertEqual(accepted.status_code, 200)
        data = accepted.json()["data"]
        self.assertEqual(data["status"], "accepted")
        snapshot = asyncio.run(state.stream_service.snapshot(session_id))
        ack = next(message for message in snapshot if message.type == "decision_ack")
        self.assertEqual(ack.payload["player_id"], 1)
        self.assertEqual(ack.payload["public_player_id"], public_player_id)
        self.assertEqual(ack.payload["primary_player_id"], public_player_id)
        self.assertEqual(ack.payload["primary_player_id_source"], "public")

    def test_start_response_includes_parameter_manifest(self) -> None:
        from apps.server.src import state

        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]

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
        started_data = started.json()["data"]
        self.assertIn("parameter_manifest", started_data)
        self.assertIn("manifest_hash", started_data["parameter_manifest"])

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        events = replay.json()["data"]["events"]
        event_types = [
            event.get("payload", {}).get("event_type")
            for event in events
            if event.get("type") == "event"
        ]
        self.assertIn("parameter_manifest", event_types)

    def test_start_replay_session_start_includes_initial_active_faces(self) -> None:
        from apps.server.src import state

        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]

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

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        events = replay.json()["data"]["events"]
        session_start = next(
            event for event in events
            if event.get("type") == "event" and event.get("payload", {}).get("event_type") == "session_start"
        )
        active_by_card = session_start.get("payload", {}).get("active_by_card", {})
        start_players = session_start.get("payload", {}).get("players", [])
        snapshot = session_start.get("payload", {}).get("snapshot", {})
        snapshot_players = snapshot.get("players", [])
        snapshot_board = snapshot.get("board", {})
        snapshot_tiles = snapshot.get("board", {}).get("tiles", [])

        self.assertEqual(len(active_by_card), 8)
        self.assertTrue(all(str(active_by_card.get(str(slot)) or active_by_card.get(slot) or "").strip() for slot in range(1, 9)))
        self.assertEqual([player.get("legacy_player_id") for player in start_players], [1, 2, 3, 4])
        self.assertTrue(all(str(player.get("public_player_id") or "").startswith("ply_") for player in start_players))
        self.assertTrue(all(str(player.get("seat_id") or "").startswith("seat_") for player in start_players))
        self.assertTrue(all(str(player.get("viewer_id") or "").startswith("view_") for player in start_players))
        self.assertEqual([player.get("player_id") for player in snapshot_players], [1, 2, 3, 4])
        self.assertNotIn("legacy_player_id", snapshot_players[0])
        self.assertTrue(all(str(player.get("public_player_id") or "").startswith("ply_") for player in snapshot_players))
        self.assertTrue(all(str(player.get("seat_id") or "").startswith("seat_") for player in snapshot_players))
        self.assertTrue(all(str(player.get("viewer_id") or "").startswith("view_") for player in snapshot_players))
        self.assertEqual(snapshot_board.get("marker_owner_player_id"), 1)
        self.assertEqual(snapshot_board.get("marker_owner_legacy_player_id"), 1)
        self.assertTrue(str(snapshot_board.get("marker_owner_public_player_id") or "").startswith("ply_"))
        self.assertTrue(str(snapshot_board.get("marker_owner_seat_id") or "").startswith("seat_"))
        self.assertTrue(str(snapshot_board.get("marker_owner_viewer_id") or "").startswith("view_"))
        self.assertEqual(len(snapshot_tiles), 40)
        self.assertEqual(snapshot_tiles[0].get("pawn_player_ids"), [1, 2, 3, 4])
        self.assertEqual(snapshot_tiles[0].get("pawn_legacy_player_ids"), [1, 2, 3, 4])
        self.assertTrue(all(str(value or "").startswith("ply_") for value in snapshot_tiles[0].get("pawn_public_player_ids", [])))
        self.assertTrue(all(str(value or "").startswith("seat_") for value in snapshot_tiles[0].get("pawn_seat_ids", [])))
        self.assertTrue(all(str(value or "").startswith("view_") for value in snapshot_tiles[0].get("pawn_viewer_ids", [])))

    def test_start_replay_parameter_manifest_also_carries_initial_active_faces(self) -> None:
        from apps.server.src import state

        payload = _all_ai_payload()
        payload["config"]["visibility"] = "public"
        created = self.client.post("/api/v1/sessions", json=payload)
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]

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

        replay = self.client.get(f"/api/v1/sessions/{session_id}/replay")
        self.assertEqual(replay.status_code, 200)
        events = replay.json()["data"]["events"]
        parameter_manifest = next(
            event for event in events
            if event.get("type") == "event" and event.get("payload", {}).get("event_type") == "parameter_manifest"
        )
        active_by_card = parameter_manifest.get("payload", {}).get("active_by_card", {})

        self.assertEqual(len(active_by_card), 8)
        self.assertTrue(all(str(active_by_card.get(str(slot)) or active_by_card.get(slot) or "").strip() for slot in range(1, 9)))

    def test_start_response_reflects_extended_parameter_matrix_manifest(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]
        manifest = created_data["parameter_manifest"]
        self.assertEqual(manifest["seats"]["allowed"], [1, 2])
        self.assertEqual(manifest["board"]["topology"], "line")
        self.assertEqual(manifest["economy"]["starting_cash"], 55)
        self.assertEqual(manifest["resources"]["starting_shards"], 7)
        self.assertEqual(manifest["dice"]["values"], [2, 4, 8])
        self.assertEqual(manifest["dice"]["max_cards_per_turn"], 1)
        self.assertEqual(manifest["rules"]["end"]["f_threshold"], 1.0)
        self.assertEqual(manifest["rules"]["end"]["tiles_to_trigger_end"], 1)
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
        started_manifest = started.json()["data"]["parameter_manifest"]
        started_active_by_card = started.json()["data"]["initial_active_by_card"]
        self.assertEqual(started_manifest["seats"]["allowed"], [1, 2])
        self.assertEqual(started_manifest["board"]["topology"], "line")
        self.assertEqual(started_manifest["economy"]["starting_cash"], 55)
        self.assertEqual(started_manifest["resources"]["starting_shards"], 7)
        self.assertEqual(started_manifest["dice"]["values"], [2, 4, 8])
        self.assertEqual(started_manifest["dice"]["max_cards_per_turn"], 1)
        self.assertEqual(started_manifest["rules"]["end"]["f_threshold"], 1.0)
        self.assertEqual(started_manifest["rules"]["end"]["tiles_to_trigger_end"], 1)
        self.assertEqual(len(started_active_by_card), 8)
        self.assertTrue(
            all(str(started_active_by_card.get(str(slot)) or started_active_by_card.get(slot) or "").strip() for slot in range(1, 9))
        )

    def test_start_session_starts_runtime_when_human_seat_is_connected(self) -> None:
        from apps.server.src import state

        created = self.client.post("/api/v1/sessions", json=_two_seat_matrix_payload())
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

        state.session_service.mark_connected(session_id, 1, True)
        calls: list[tuple[str, int, str | None]] = []
        original = state.runtime_service.start_runtime

        async def _fake_start_runtime(session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
            calls.append((session_id, seed, policy_mode))

        state.runtime_service.start_runtime = _fake_start_runtime  # type: ignore[assignment]
        try:
            started = self.client.post(
                f"/api/v1/sessions/{session_id}/start",
                json={"host_token": host_token},
            )
            self.assertEqual(started.status_code, 200)
        finally:
            state.runtime_service.start_runtime = original  # type: ignore[assignment]

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], session_id)


if __name__ == "__main__":
    unittest.main()
