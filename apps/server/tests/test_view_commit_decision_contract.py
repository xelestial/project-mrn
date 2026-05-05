from __future__ import annotations

import unittest

from apps.server.src.routes.stream import _decision_view_commit_rejection_reason


class ViewCommitDecisionContractTests(unittest.TestCase):
    def test_rejects_missing_view_commit_seq_seen(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_1", "player_id": 1},
            _latest_commit(commit_seq=4, request_id="req_1", player_id=1, prompt_commit_seq=4),
        )

        self.assertEqual(reason, "missing_view_commit_seq_seen")

    def test_rejects_decision_older_than_active_prompt_commit(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_1", "player_id": 1, "view_commit_seq_seen": 3},
            _latest_commit(commit_seq=5, request_id="req_1", player_id=1, prompt_commit_seq=4),
        )

        self.assertEqual(reason, "stale_view_commit_seq")

    def test_rejects_mismatched_active_prompt_request(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_old", "player_id": 1, "view_commit_seq_seen": 5},
            _latest_commit(commit_seq=5, request_id="req_new", player_id=1, prompt_commit_seq=5),
        )

        self.assertEqual(reason, "stale_prompt_request")

    def test_accepts_current_prompt_decision(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_1", "player_id": 1, "view_commit_seq_seen": 5},
            _latest_commit(commit_seq=5, request_id="req_1", player_id=1, prompt_commit_seq=4),
        )

        self.assertIsNone(reason)


def _latest_commit(*, commit_seq: int, request_id: str, player_id: int, prompt_commit_seq: int) -> dict:
    return {
        "type": "view_commit",
        "seq": commit_seq,
        "session_id": "s1",
        "payload": {
            "commit_seq": commit_seq,
            "view_state": {
                "prompt": {
                    "active": {
                        "request_id": request_id,
                        "player_id": player_id,
                        "view_commit_seq": prompt_commit_seq,
                    },
                },
            },
        },
    }
