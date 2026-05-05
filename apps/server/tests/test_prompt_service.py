from __future__ import annotations

import threading
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

    def test_attaches_prompt_fingerprint_to_accepted_decision(self) -> None:
        pending = self.service.create_prompt(
            "s1",
            {
                "request_id": "r1fp",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                "public_context": {"round_index": 1, "turn_index": 0},
            },
        )
        self.assertIn("prompt_fingerprint", pending.payload)

        result = self.service.submit_decision({"request_id": "r1fp", "player_id": 1, "choice_id": "roll"})
        self.assertEqual(result["status"], "accepted")
        decision = self.service.wait_for_decision("r1fp", timeout_ms=1)

        self.assertIsNotNone(decision)
        self.assertEqual(decision["prompt_fingerprint"], pending.payload["prompt_fingerprint"])

    def test_rejects_prompt_fingerprint_mismatch(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r1fp_mismatch",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        result = self.service.submit_decision(
            {
                "request_id": "r1fp_mismatch",
                "player_id": 1,
                "choice_id": "roll",
                "prompt_fingerprint": "stale-client-fingerprint",
            }
        )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "prompt_fingerprint_mismatch")

    def test_rejects_illegal_choice_for_any_prompt_with_legal_choices(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r1_illegal",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        result = self.service.submit_decision(
            {"request_id": "r1_illegal", "player_id": 1, "choice_id": "teleport"}
        )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "choice_not_legal")

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

    def test_rejects_missing_choice_id(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r2b",
                "request_type": "movement",
                "player_id": 2,
                "timeout_ms": 30000,
            },
        )
        result = self.service.submit_decision({"request_id": "r2b", "player_id": 2})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "missing_choice_id")

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

    def test_get_pending_prompt_returns_copy(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "pending_copy",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        pending = self.service.get_pending_prompt("pending_copy")
        self.assertIsNotNone(pending)
        assert pending is not None
        pending.payload["legal_choices"] = []

        reloaded = self.service.get_pending_prompt("pending_copy")
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.payload["legal_choices"][0]["choice_id"], "roll")

    def test_already_resolved_request_returns_stale(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r4",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )
        accepted = self.service.submit_decision(
            {"request_id": "r4", "player_id": 1, "choice_id": "roll"}
        )
        self.assertEqual(accepted["status"], "accepted")

        stale = self.service.submit_decision(
            {"request_id": "r4", "player_id": 1, "choice_id": "roll"}
        )
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["reason"], "already_resolved")

    def test_timeout_pending_is_idempotent_per_request(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r5",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 1,
            },
        )
        first = self.service.timeout_pending(now_ms=10**15, session_id="s1")
        second = self.service.timeout_pending(now_ms=10**15 + 1, session_id="s1")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)

    def test_wait_for_decision_returns_submitted_payload(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r6",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )

        def _submit() -> None:
            self.service.submit_decision({"request_id": "r6", "player_id": 1, "choice_id": "roll"})

        thread = threading.Thread(target=_submit, daemon=True)
        thread.start()
        decision = self.service.wait_for_decision("r6", timeout_ms=1000)
        thread.join(timeout=1.0)

        self.assertIsNotNone(decision)
        self.assertEqual(decision["choice_id"], "roll")
        replayed = self.service.wait_for_decision("r6", timeout_ms=1)
        self.assertIsNotNone(replayed)
        self.assertEqual(replayed["choice_id"], "roll")

    def test_wait_for_decision_times_out_and_expire_prompt_cleans_up(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r7",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )
        decision = self.service.wait_for_decision("r7", timeout_ms=10)
        self.assertIsNone(decision)
        expired = self.service.expire_prompt("r7", reason="prompt_timeout")
        self.assertIsNotNone(expired)
        stale = self.service.submit_decision({"request_id": "r7", "player_id": 1, "choice_id": "roll"})
        self.assertEqual(stale["status"], "stale")


if __name__ == "__main__":
    unittest.main()
