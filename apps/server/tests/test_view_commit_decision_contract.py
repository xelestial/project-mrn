from __future__ import annotations

import unittest

from apps.server.src.routes import stream
from apps.server.src.services.prompt_service import PromptService


class ViewCommitDecisionContractTests(unittest.TestCase):
    def test_decision_route_has_no_view_commit_rejection_helper(self) -> None:
        self.assertFalse(hasattr(stream, "_decision_view_commit_rejection_reason"))
        self.assertFalse(hasattr(stream, "_repair_missing_pending_prompt_from_view_commit"))

    def test_prompt_decision_acceptance_does_not_require_view_commit_seq_seen(self) -> None:
        service = PromptService()
        service.create_prompt(
            "session_1",
            {
                "request_id": "req_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 5000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        result = service.submit_decision(
            {
                "type": "decision",
                "session_id": "session_1",
                "request_id": "req_1",
                "player_id": 1,
                "choice_id": "roll",
                "choice_payload": {},
            }
        )

        self.assertEqual(result["status"], "accepted")
        self.assertIsNone(result["reason"])

    def test_missing_pending_prompt_is_not_reconstructed_from_view_state(self) -> None:
        service = PromptService()

        result = service.submit_decision(
            {
                "type": "decision",
                "session_id": "session_1",
                "request_id": "req_missing",
                "player_id": 1,
                "choice_id": "roll",
                "choice_payload": {},
                "view_commit_seq_seen": 7,
            }
        )

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reason"], "request_not_pending")
