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
    state.runtime_service = RuntimeService(
        session_service=state.session_service,
        stream_service=state.stream_service,
        prompt_service=state.prompt_service,
    )


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
        },
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class SessionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state()
        self.client = TestClient(app)

    def test_runtime_status_shape(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        self.assertIn("parameter_manifest", created_data)
        self.assertIn("manifest_hash", created_data["parameter_manifest"])
        session_id = created_data["session_id"]

        fetched = self.client.get(f"/api/v1/sessions/{session_id}")
        self.assertEqual(fetched.status_code, 200)
        fetched_data = fetched.json()["data"]
        self.assertIn("parameter_manifest", fetched_data)
        self.assertEqual(
            fetched_data["parameter_manifest"]["manifest_hash"],
            created_data["parameter_manifest"]["manifest_hash"],
        )

        runtime = self.client.get(f"/api/v1/sessions/{session_id}/runtime-status")
        self.assertEqual(runtime.status_code, 200)
        payload = runtime.json()["data"]["runtime"]
        self.assertIn("status", payload)

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
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
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
        self.assertEqual(data["event_count"], 4)
        self.assertEqual(data["events"][-2]["seq"], 3)
        self.assertEqual(data["events"][-1]["seq"], 4)
        self.assertEqual(data["events"][-2].get("payload", {}).get("event_type"), "round_start")
        self.assertEqual(data["events"][-1].get("payload", {}).get("event_type"), "turn_start")
        self.assertIn("server_time_ms", data["events"][0])
        self.assertIn("view_state", data["events"][-1].get("payload", {}))
        self.assertIn("players", data["events"][-1].get("payload", {}).get("view_state", {}))

    def test_start_response_includes_parameter_manifest(self) -> None:
        created = self.client.post("/api/v1/sessions", json=_all_ai_payload())
        self.assertEqual(created.status_code, 200)
        created_data = created.json()["data"]
        session_id = created_data["session_id"]
        host_token = created_data["host_token"]

        started = self.client.post(
            f"/api/v1/sessions/{session_id}/start",
            json={"host_token": host_token},
        )
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
        self.assertEqual(started_manifest["seats"]["allowed"], [1, 2])
        self.assertEqual(started_manifest["board"]["topology"], "line")
        self.assertEqual(started_manifest["economy"]["starting_cash"], 55)
        self.assertEqual(started_manifest["resources"]["starting_shards"], 7)
        self.assertEqual(started_manifest["dice"]["values"], [2, 4, 8])
        self.assertEqual(started_manifest["dice"]["max_cards_per_turn"], 1)

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
