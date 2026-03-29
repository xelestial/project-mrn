from __future__ import annotations

import unittest

from apps.server.src.services.session_service import SessionService, SessionStateError


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

    def test_join_and_start_session(self) -> None:
        session = self.service.create_session(_default_seats())
        join_1 = self.service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        join_4 = self.service.join_session(session.session_id, 4, session.join_tokens[4], "P4")
        self.assertEqual(join_1["seat"], 1)
        self.assertEqual(join_4["seat"], 4)

        started = self.service.start_session(session.session_id, session.host_token)
        self.assertEqual(started.status.value, "in_progress")
        self.assertIsNotNone(started.started_at)

    def test_verify_session_token(self) -> None:
        session = self.service.create_session(_default_seats())
        join_1 = self.service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        auth = self.service.verify_session_token(session.session_id, join_1["session_token"])
        self.assertEqual(auth["role"], "seat")
        self.assertEqual(auth["seat"], 1)
        self.assertEqual(auth["player_id"], 1)
        spectator = self.service.verify_session_token(session.session_id, None)
        self.assertEqual(spectator["role"], "spectator")

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

    def test_is_all_ai(self) -> None:
        human_mix = self.service.create_session(_default_seats())
        self.assertFalse(self.service.is_all_ai(human_mix.session_id))
        all_ai = self.service.create_session(_all_ai_seats())
        self.assertTrue(self.service.is_all_ai(all_ai.session_id))


if __name__ == "__main__":
    unittest.main()
