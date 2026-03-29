from __future__ import annotations

import unittest

from apps.server.src.services.prompt_service import PromptService


class PromptServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PromptService()

    def test_accepts_valid_decision(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )
        result = self.service.submit_decision({"request_id": "r1", "player_id": 1, "choice_id": "roll"})
        self.assertEqual(result["status"], "accepted")

    def test_rejects_player_mismatch(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r2",
                "request_type": "movement",
                "player_id": 2,
                "timeout_ms": 30000,
            },
        )
        result = self.service.submit_decision({"request_id": "r2", "player_id": 1, "choice_id": "roll"})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "player_mismatch")

    def test_timeout_pending_by_session(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r3",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 1,
            },
        )
        timed_out = self.service.timeout_pending(now_ms=10**15, session_id="s1")
        self.assertEqual(len(timed_out), 1)
        self.assertEqual(timed_out[0].request_id, "r3")

    def test_rejects_duplicate_pending_request_id(self) -> None:
        payload = {
            "request_id": "dup1",
            "request_type": "movement",
            "player_id": 1,
            "timeout_ms": 30000,
        }
        self.service.create_prompt("s1", payload)
        with self.assertRaises(ValueError):
            self.service.create_prompt("s1", payload)


if __name__ == "__main__":
    unittest.main()
