from __future__ import annotations

import re
import unittest

from apps.server.src.services.session_service import SessionNotFoundError, SessionService, SessionStateError


def _default_seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 4, "seat_type": "human"},
    ]


def _all_ai_seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
    ]


class SessionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SessionService()

    def test_create_session_has_tokens_for_humans(self) -> None:
        session = self.service.create_session(_default_seats(), config={"seed": 42})
        self.assertEqual(session.status.value, "waiting")
        self.assertIn(1, session.join_tokens)
        self.assertIn(4, session.join_tokens)
        self.assertNotIn(2, session.join_tokens)
        self.assertIn("manifest_hash", session.parameter_manifest)
        self.assertIn("source_fingerprints", session.parameter_manifest)

    def test_join_and_start_session(self) -> None:
        session = self.service.create_session(_default_seats())
        join_1 = self.service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        join_4 = self.service.join_session(session.session_id, 4, session.join_tokens[4], "P4")
        self.assertEqual(join_1["seat"], 1)
        self.assertEqual(join_4["seat"], 4)
        self.assertFalse(self.service.get_session(session.session_id).seats[0].connected)

        started = self.service.start_session(session.session_id, session.host_token)
        self.assertEqual(started.status.value, "in_progress")
        self.assertIsNotNone(started.started_at)

    def test_verify_session_token(self) -> None:
        session = self.service.create_session(_default_seats(), config={"visibility": "public"})
        join_1 = self.service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        auth = self.service.verify_session_token(session.session_id, join_1["session_token"])
        self.assertEqual(auth["role"], "seat")
        self.assertEqual(auth["seat"], 1)
        self.assertEqual(auth["player_id"], 1)
        spectator = self.service.verify_session_token(session.session_id, None)
        self.assertEqual(spectator["role"], "spectator")

    def test_join_exposes_distinct_protocol_identity_fields(self) -> None:
        session = self.service.create_session(_default_seats())

        join_1 = self.service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        auth = self.service.verify_session_token(session.session_id, join_1["session_token"])
        public = self.service.to_public(session)
        seat_payload = public["seats"][0]

        self.assertEqual(join_1["player_id"], 1)
        self.assertEqual(join_1["legacy_player_id"], 1)
        self.assertEqual(join_1["seat_index"], 1)
        self.assertEqual(join_1["turn_order_index"], 1)
        self.assertEqual(join_1["player_label"], "P1")
        self.assertRegex(join_1["public_player_id"], r"^ply_[0-9a-f-]{36}$")
        self.assertRegex(join_1["seat_id"], r"^seat_[0-9a-f-]{36}$")
        self.assertRegex(join_1["viewer_id"], r"^view_[0-9a-f-]{36}$")
        self.assertNotEqual(join_1["public_player_id"], str(join_1["player_id"]))
        self.assertEqual(auth["public_player_id"], join_1["public_player_id"])
        self.assertEqual(auth["seat_id"], join_1["seat_id"])
        self.assertEqual(auth["viewer_id"], join_1["viewer_id"])
        self.assertEqual(seat_payload["public_player_id"], join_1["public_player_id"])
        self.assertEqual(seat_payload["seat_id"], join_1["seat_id"])
        self.assertEqual(seat_payload["seat_index"], 1)
        self.assertEqual(seat_payload["player_label"], "P1")

    def test_created_session_exposes_protocol_identity_for_every_seat(self) -> None:
        session = self.service.create_session(_all_ai_seats())

        public = self.service.to_public(session)

        seen_player_ids = set()
        seen_seat_ids = set()
        for index, seat_payload in enumerate(public["seats"], start=1):
            self.assertRegex(seat_payload["public_player_id"], r"^ply_[0-9a-f-]{36}$")
            self.assertRegex(seat_payload["seat_id"], r"^seat_[0-9a-f-]{36}$")
            self.assertRegex(seat_payload["viewer_id"], r"^view_[0-9a-f-]{36}$")
            self.assertEqual(seat_payload["seat_index"], index)
            self.assertEqual(seat_payload["turn_order_index"], index)
            self.assertEqual(seat_payload["player_label"], f"P{index}")
            seen_player_ids.add(seat_payload["public_player_id"])
            seen_seat_ids.add(seat_payload["seat_id"])
        self.assertEqual(len(seen_player_ids), 4)
        self.assertEqual(len(seen_seat_ids), 4)

    def test_store_backed_session_identity_fields_survive_reload(self) -> None:
        store = _MemorySessionStore()
        owner = SessionService(session_store=store)
        session = owner.create_session(_default_seats())
        join_1 = owner.join_session(session.session_id, 1, session.join_tokens[1], "P1")

        reloaded = SessionService(session_store=store)
        auth = reloaded.verify_session_token(session.session_id, join_1["session_token"])
        seat_payload = reloaded.to_public(reloaded.get_session(session.session_id))["seats"][0]

        self.assertTrue(re.match(r"^ply_[0-9a-f-]{36}$", auth["public_player_id"]))
        self.assertEqual(auth["public_player_id"], join_1["public_player_id"])
        self.assertEqual(auth["seat_id"], join_1["seat_id"])
        self.assertEqual(seat_payload["public_player_id"], join_1["public_player_id"])
        self.assertEqual(seat_payload["seat_id"], join_1["seat_id"])

    def test_private_session_rejects_missing_spectator_token(self) -> None:
        session = self.service.create_session(_default_seats())
        with self.assertRaises(SessionStateError):
            self.service.verify_session_token(session.session_id, None)

    def test_start_rejected_when_humans_not_joined(self) -> None:
        session = self.service.create_session(_default_seats())
        with self.assertRaises(SessionStateError):
            self.service.start_session(session.session_id, session.host_token)

    def test_join_rejected_with_wrong_token(self) -> None:
        session = self.service.create_session(_default_seats())
        with self.assertRaises(SessionStateError):
            self.service.join_session(session.session_id, 1, "wrong")

    def test_reject_invalid_seat_count(self) -> None:
        with self.assertRaises(SessionStateError):
            self.service.create_session([{"seat": 1, "seat_type": "human"}])

    def test_reject_seat_outside_configured_range(self) -> None:
        with self.assertRaises(SessionStateError):
            self.service.create_session(
                _default_seats(),
                config={"seat_limits": {"min": 2, "max": 3, "allowed": [1, 2, 3]}},
            )

    def test_manifest_hash_changes_on_parameter_override(self) -> None:
        base = self.service.create_session(_all_ai_seats(), config={"seed": 1})
        changed = self.service.create_session(_all_ai_seats(), config={"seed": 1, "starting_cash": 30})
        self.assertNotEqual(
            base.parameter_manifest.get("manifest_hash"),
            changed.parameter_manifest.get("manifest_hash"),
        )

    def test_manifest_hash_changes_on_board_topology_override(self) -> None:
        base = self.service.create_session(_all_ai_seats(), config={"seed": 1, "board_topology": "ring"})
        changed = self.service.create_session(_all_ai_seats(), config={"seed": 1, "board_topology": "line"})
        self.assertNotEqual(
            base.parameter_manifest.get("manifest_hash"),
            changed.parameter_manifest.get("manifest_hash"),
        )

    def test_is_all_ai(self) -> None:
        human_mix = self.service.create_session(_default_seats())
        self.assertFalse(self.service.is_all_ai(human_mix.session_id))
        all_ai = self.service.create_session(_all_ai_seats())
        self.assertTrue(self.service.is_all_ai(all_ai.session_id))

    def test_ai_seat_can_declare_external_participant_client(self) -> None:
        session = self.service.create_session(
            [
                {
                    "seat": 1,
                    "seat_type": "ai",
                    "ai_profile": "balanced",
                    "participant_client": "external_ai",
                    "participant_config": {"transport": "loopback", "endpoint": "local://bot-worker-1"},
                },
                {"seat": 2, "seat_type": "human"},
            ]
        )

        ai_seat = session.seats[0]
        self.assertEqual(ai_seat.participant_client.value, "external_ai")
        self.assertEqual(ai_seat.participant_config["endpoint"], "local://bot-worker-1")

    def test_external_ai_seat_inherits_participant_defaults_from_resolved_parameters(self) -> None:
        session = self.service.create_session(
            [
                {
                    "seat": 1,
                    "seat_type": "ai",
                    "ai_profile": "balanced",
                    "participant_client": "external_ai",
                    "participant_config": {"endpoint": "http://seat-specific.local/decide"},
                },
                {"seat": 2, "seat_type": "human"},
            ],
            config={
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
                        "headers": {"Authorization": "Bearer token"},
                    }
                },
            },
        )

        ai_seat = session.seats[0]
        self.assertEqual(ai_seat.participant_config["transport"], "http")
        self.assertEqual(ai_seat.participant_config["contract_version"], "v1")
        self.assertEqual(ai_seat.participant_config["expected_worker_id"], "bot-worker-1")
        self.assertEqual(ai_seat.participant_config["auth_token"], "worker-secret")
        self.assertEqual(ai_seat.participant_config["auth_header_name"], "X-Worker-Auth")
        self.assertEqual(ai_seat.participant_config["auth_scheme"], "Token")
        self.assertEqual(ai_seat.participant_config["timeout_ms"], 9000)
        self.assertEqual(ai_seat.participant_config["retry_count"], 2)
        self.assertEqual(ai_seat.participant_config["backoff_ms"], 100)
        self.assertEqual(ai_seat.participant_config["fallback_mode"], "local_ai")
        self.assertEqual(ai_seat.participant_config["healthcheck_path"], "/health")
        self.assertEqual(ai_seat.participant_config["healthcheck_ttl_ms"], 5000)
        self.assertEqual(ai_seat.participant_config["required_capabilities"], ["choice_id_response", "healthcheck"])

    def test_external_ai_seat_inherits_worker_profile_defaults(self) -> None:
        session = self.service.create_session(
            [
                {
                    "seat": 1,
                    "seat_type": "ai",
                    "ai_profile": "balanced",
                    "participant_client": "external_ai",
                    "participant_config": {"endpoint": "http://seat-specific.local/decide"},
                },
                {"seat": 2, "seat_type": "human"},
            ],
            config={
                "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
                "participants": {
                    "external_ai": {
                        "transport": "http",
                        "worker_profile": "priority_scored",
                    }
                },
            },
        )

        ai_seat = session.seats[0]
        self.assertEqual(ai_seat.participant_config["worker_profile"], "priority_scored")
        self.assertEqual(ai_seat.participant_config["required_worker_adapter"], "priority_score_v1")
        self.assertEqual(ai_seat.participant_config["required_policy_class"], "PriorityScoredPolicy")
        self.assertEqual(ai_seat.participant_config["required_decision_style"], "priority_scored_contract")
        self.assertIn("priority_scored_choice", ai_seat.participant_config["required_capabilities"])
        self.assertEqual(ai_seat.participant_config["endpoint"], "http://seat-specific.local/decide")

    def test_reject_human_seat_with_non_human_participant_client(self) -> None:
        with self.assertRaises(SessionStateError):
            self.service.create_session(
                [
                    {"seat": 1, "seat_type": "human", "participant_client": "external_ai"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ]
            )

    def test_store_backed_get_session_refreshes_deleted_sessions_from_store(self) -> None:
        store = _MemorySessionStore()
        owner = SessionService(session_store=store)
        session = owner.create_session(_all_ai_seats())
        stale_reader = SessionService(session_store=store)

        self.assertEqual(stale_reader.get_session(session.session_id).session_id, session.session_id)

        owner.delete_session(session.session_id)

        with self.assertRaises(SessionNotFoundError):
            stale_reader.get_session(session.session_id)

    def test_store_backed_create_session_does_not_resurrect_deleted_cached_sessions(self) -> None:
        store = _MemorySessionStore()
        owner = SessionService(session_store=store)
        deleted = owner.create_session(_all_ai_seats())
        stale_creator = SessionService(session_store=store)

        owner.delete_session(deleted.session_id)
        created = stale_creator.create_session(_all_ai_seats())

        persisted_ids = {payload["session_id"] for payload in store.load_sessions()}
        self.assertEqual(persisted_ids, {created.session_id})


class _MemorySessionStore:
    def __init__(self) -> None:
        self.sessions: list[dict] = []

    def load_sessions(self) -> list[dict]:
        return [dict(session) for session in self.sessions]

    def save_sessions(self, sessions: list[dict]) -> None:
        self.sessions = [dict(session) for session in sessions]


if __name__ == "__main__":
    unittest.main()
