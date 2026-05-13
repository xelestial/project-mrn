from __future__ import annotations

import threading
import unittest

from apps.server.src.services.prompt_service import PromptService


class LostDeletePromptStore:
    def __init__(self, pending: dict[str, object]) -> None:
        self.pending = pending
        self.delete_calls = 0
        self.resolved: list[dict[str, object]] = []
        self.lifecycle: list[dict[str, object]] = []
        self.deleted_decisions: list[tuple[str, str | None]] = []

    def list_pending(self) -> list[dict[str, object]]:
        return [self.pending]

    def get_pending(self, request_id: str, session_id: str | None = None) -> dict[str, object] | None:
        return self.pending

    def delete_pending(self, request_id: str, session_id: str | None = None) -> bool:
        self.delete_calls += 1
        return False

    def save_resolved(self, request_id: str, payload: dict[str, object], session_id: str | None = None) -> None:
        self.resolved.append(payload)

    def save_lifecycle(self, request_id: str, payload: dict[str, object], session_id: str | None = None) -> None:
        self.lifecycle.append(payload)

    def delete_decision(self, request_id: str, session_id: str | None = None) -> None:
        self.deleted_decisions.append((request_id, session_id))


class CountingPromptStore:
    def __init__(self) -> None:
        self.list_resolved_calls = 0
        self.get_decision_calls = 0
        self.get_pending_calls = 0

    def list_resolved(self) -> dict[str, dict[str, object]]:
        self.list_resolved_calls += 1
        return {}

    def get_decision(self, request_id: str, session_id: str | None = None) -> dict[str, object] | None:
        self.get_decision_calls += 1
        return None

    def get_pending(self, request_id: str, session_id: str | None = None) -> dict[str, object] | None:
        self.get_pending_calls += 1
        return None


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

    def test_records_prompt_lifecycle_from_create_to_accept(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r1_lifecycle",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                "public_context": {"round_index": 2, "turn_index": 5},
            },
        )

        created = self.service.get_prompt_lifecycle("r1_lifecycle")
        self.assertIsNotNone(created)
        assert created is not None
        self.assertEqual(created["state"], "created")
        self.assertEqual(created["session_id"], "s1")
        self.assertEqual(created["player_id"], 1)
        self.assertEqual(created["request_type"], "movement")
        self.assertEqual(created["prompt"]["legal_choice_ids"], ["roll"])
        self.assertEqual(created["prompt"]["public_context"], {"round_index": 2, "turn_index": 5})

        delivered = self.service.mark_prompt_delivered("r1_lifecycle", stream_seq=12, commit_seq=7)
        self.assertIsNotNone(delivered)
        assert delivered is not None
        self.assertEqual(delivered["state"], "delivered")
        self.assertEqual(delivered["stream_seq"], 12)
        self.assertEqual(delivered["commit_seq"], 7)

        result = self.service.submit_decision(
            {
                "request_id": "r1_lifecycle",
                "player_id": 1,
                "choice_id": "roll",
                "view_commit_seq_seen": 7,
            }
        )
        self.assertEqual(result["status"], "accepted")

        accepted = self.service.get_prompt_lifecycle("r1_lifecycle")
        self.assertIsNotNone(accepted)
        assert accepted is not None
        self.assertEqual(accepted["state"], "accepted")
        self.assertEqual(accepted["decision"]["choice_id"], "roll")
        self.assertEqual(accepted["decision"]["view_commit_seq_seen"], 7)

    def test_records_rejected_and_expired_prompt_lifecycle(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r1_lifecycle_reject",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        rejected = self.service.submit_decision(
            {"request_id": "r1_lifecycle_reject", "player_id": 2, "choice_id": "roll"}
        )
        self.assertEqual(rejected["status"], "rejected")
        lifecycle = self.service.get_prompt_lifecycle("r1_lifecycle_reject")
        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle["state"], "rejected")
        self.assertEqual(lifecycle["reason"], "player_mismatch")

        expired = self.service.expire_prompt("r1_lifecycle_reject", reason="manual_cleanup")
        self.assertIsNotNone(expired)
        lifecycle = self.service.get_prompt_lifecycle("r1_lifecycle_reject")
        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle["state"], "expired")
        self.assertEqual(lifecycle["reason"], "manual_cleanup")

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

    def test_allows_same_pending_request_id_across_sessions(self) -> None:
        payload = {
            "request_id": "shared_pending_batch:p0",
            "request_type": "burden_exchange",
            "player_id": 1,
            "timeout_ms": 30000,
            "legal_choices": [{"choice_id": "yes"}],
        }
        first = self.service.create_prompt("s1", payload)
        second = self.service.create_prompt("s2", payload)

        self.assertEqual(first.session_id, "s1")
        self.assertEqual(second.session_id, "s2")

        accepted = self.service.submit_decision(
            {
                "session_id": "s1",
                "request_id": "shared_pending_batch:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )

        self.assertEqual(accepted["status"], "accepted")
        self.assertFalse(self.service.has_pending_for_session("s1"))
        self.assertTrue(self.service.has_pending_for_session("s2"))
        remaining = self.service.submit_decision(
            {
                "session_id": "s2",
                "request_id": "shared_pending_batch:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )
        self.assertEqual(remaining["status"], "accepted")

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

    def test_resolved_request_id_is_scoped_by_session(self) -> None:
        payload = {
            "request_id": "shared_batch_prompt:p0",
            "request_type": "burden_exchange",
            "player_id": 1,
            "timeout_ms": 30000,
            "legal_choices": [{"choice_id": "yes"}],
        }
        self.service.create_prompt("s1", payload)
        first = self.service.submit_decision(
            {
                "session_id": "s1",
                "request_id": "shared_batch_prompt:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )
        self.assertEqual(first["status"], "accepted")

        recreated = self.service.create_prompt("s2", payload)
        self.assertEqual(recreated.session_id, "s2")
        second = self.service.submit_decision(
            {
                "session_id": "s2",
                "request_id": "shared_batch_prompt:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )
        self.assertEqual(second["status"], "accepted")

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

    def test_timeout_pending_skips_stale_store_snapshot_when_delete_loses_race(self) -> None:
        store = LostDeletePromptStore(
            {
                "session_id": "s-race",
                "request_id": "r-race",
                "request_type": "movement",
                "player_id": 1,
                "payload": {
                    "request_id": "r-race",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 1,
                },
                "created_at_ms": 1,
                "timeout_ms": 1,
            }
        )
        service = PromptService(prompt_store=store)

        timed_out = service.timeout_pending(now_ms=10**15, session_id="s-race")

        self.assertEqual(timed_out, [])
        self.assertEqual(store.delete_calls, 1)
        self.assertEqual(store.resolved, [])
        self.assertEqual(store.lifecycle, [])
        self.assertEqual(store.deleted_decisions, [])

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

    def test_wait_for_decision_zero_timeout_is_immediate_probe(self) -> None:
        self.service.create_prompt(
            "s1",
            {
                "request_id": "r8",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )
        waiters_before = dict(self.service._waiters)

        decision = self.service.wait_for_decision("r8", timeout_ms=0, session_id="s1")

        self.assertIsNone(decision)
        self.assertEqual(self.service._waiters, waiters_before)

    def test_wait_for_decision_does_not_prune_resolved_hash_for_probe(self) -> None:
        store = CountingPromptStore()
        service = PromptService(prompt_store=store)

        decision = service.wait_for_decision("missing", timeout_ms=0, session_id="s1")

        self.assertIsNone(decision)
        self.assertEqual(store.get_decision_calls, 1)
        self.assertEqual(store.get_pending_calls, 0)
        self.assertEqual(store.list_resolved_calls, 0)


if __name__ == "__main__":
    unittest.main()
