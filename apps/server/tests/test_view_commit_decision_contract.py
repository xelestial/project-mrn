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

    def test_accepts_current_prompt_even_when_seen_commit_lags_prompt_commit(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_1", "player_id": 1, "view_commit_seq_seen": 3},
            _latest_commit(commit_seq=5, request_id="req_1", player_id=1, prompt_commit_seq=4),
        )

        self.assertIsNone(reason)

    def test_rejects_mismatched_active_prompt_request(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {"type": "decision", "request_id": "req_old", "player_id": 1, "view_commit_seq_seen": 5},
            _latest_commit(commit_seq=5, request_id="req_new", player_id=1, prompt_commit_seq=5),
        )

        self.assertEqual(reason, "stale_prompt_request")

    def test_rejects_mismatched_prompt_instance_id(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {
                "type": "decision",
                "request_id": "req_1",
                "player_id": 1,
                "prompt_instance_id": 8,
                "resume_token": "resume_9",
                "view_commit_seq_seen": 5,
            },
            _latest_commit(
                commit_seq=5,
                request_id="req_1",
                player_id=1,
                prompt_commit_seq=5,
                prompt_instance_id=9,
                resume_token="resume_9",
            ),
        )

        self.assertEqual(reason, "stale_prompt_instance")

    def test_rejects_mismatched_resume_token(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {
                "type": "decision",
                "request_id": "req_1",
                "player_id": 1,
                "prompt_instance_id": 9,
                "resume_token": "resume_old",
                "view_commit_seq_seen": 5,
            },
            _latest_commit(
                commit_seq=5,
                request_id="req_1",
                player_id=1,
                prompt_commit_seq=5,
                prompt_instance_id=9,
                resume_token="resume_9",
            ),
        )

        self.assertEqual(reason, "stale_prompt_resume_token")

    def test_accepts_current_prompt_decision(self) -> None:
        reason = _decision_view_commit_rejection_reason(
            {
                "type": "decision",
                "request_id": "req_1",
                "player_id": 1,
                "prompt_instance_id": 9,
                "resume_token": "resume_9",
                "view_commit_seq_seen": 5,
            },
            _latest_commit(
                commit_seq=5,
                request_id="req_1",
                player_id=1,
                prompt_commit_seq=4,
                prompt_instance_id=9,
                resume_token="resume_9",
            ),
        )

        self.assertIsNone(reason)


def _latest_commit(
    *,
    commit_seq: int,
    request_id: str,
    player_id: int,
    prompt_commit_seq: int,
    prompt_instance_id: int | None = None,
    resume_token: str | None = None,
) -> dict:
    active_prompt = {
        "request_id": request_id,
        "player_id": player_id,
        "view_commit_seq": prompt_commit_seq,
    }
    if prompt_instance_id is not None:
        active_prompt["prompt_instance_id"] = prompt_instance_id
    if resume_token is not None:
        active_prompt["resume_token"] = resume_token
    return {
        "type": "view_commit",
        "seq": commit_seq,
        "session_id": "s1",
        "payload": {
            "commit_seq": commit_seq,
            "view_state": {
                "prompt": {
                    "active": active_prompt,
                },
            },
        },
    }
