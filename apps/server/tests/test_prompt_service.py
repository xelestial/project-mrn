from __future__ import annotations

import threading
import unittest

from apps.server.src.services.batch_collector import BatchCollectorResult
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


class FailingCommandStore:
    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict,
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> None:
        return None


class CapturingCommandStore:
    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []

    def append_command(
        self,
        session_id: str,
        command_type: str,
        payload: dict,
        *,
        request_id: str | None = None,
        server_time_ms: int | None = None,
    ) -> dict[str, object]:
        command = {
            "seq": len(self.commands) + 1,
            "session_id": session_id,
            "type": command_type,
            "request_id": request_id,
            "payload": dict(payload),
            "server_time_ms": server_time_ms,
        }
        self.commands.append(command)
        return command


class BatchCollectorStub:
    def __init__(self, results: list[BatchCollectorResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, object]] = []

    def record_response(self, **kwargs) -> BatchCollectorResult:
        self.calls.append(kwargs)
        if not self.results:
            raise AssertionError("unexpected collector call")
        return self.results.pop(0)


def _batch_prompt(*, player_id: int) -> dict[str, object]:
    return {
        "request_id": f"batch:1:p{player_id}",
        "request_type": "burden_exchange",
        "player_id": player_id,
        "timeout_ms": 30000,
        "legal_choices": [{"choice_id": "yes"}, {"choice_id": "no"}],
        "runner_kind": "module",
        "resume_token": f"resume_p{player_id}",
        "frame_id": "frame:1",
        "module_id": "module:1",
        "module_type": "ResupplyModule",
        "module_cursor": "await_resupply_batch:1",
        "batch_id": "batch:1",
        "missing_player_ids": [1, 2],
        "resume_tokens_by_player_id": {"1": "resume_p1", "2": "resume_p2"},
    }


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

    def test_create_prompt_adds_opaque_identity_companions_to_lifecycle(self) -> None:
        pending = self.service.create_prompt(
            "s1",
            {
                "request_id": "s1:r2:t3:p1:movement:5",
                "request_type": "movement",
                "player_id": 1,
                "prompt_instance_id": 5,
                "timeout_ms": 30000,
            },
        )

        self.assertEqual(pending.request_id, "s1:r2:t3:p1:movement:5")
        self.assertEqual(pending.payload["legacy_request_id"], pending.request_id)
        self.assertTrue(str(pending.payload["public_request_id"]).startswith("req_"))
        self.assertTrue(str(pending.payload["public_prompt_instance_id"]).startswith("pin_"))
        self.assertNotEqual(pending.payload["public_request_id"], pending.request_id)

        result = self.service.submit_decision(
            {
                "request_id": pending.request_id,
                "player_id": 1,
                "choice_id": "roll",
            }
        )

        self.assertEqual(result["status"], "accepted")
        lifecycle = self.service.get_prompt_lifecycle(pending.request_id, session_id="s1")
        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle["prompt"]["legacy_request_id"], pending.request_id)
        self.assertEqual(lifecycle["prompt"]["public_request_id"], pending.payload["public_request_id"])
        self.assertEqual(lifecycle["prompt"]["public_prompt_instance_id"], pending.payload["public_prompt_instance_id"])
        self.assertEqual(lifecycle["decision"]["legacy_request_id"], pending.request_id)
        self.assertEqual(lifecycle["decision"]["public_request_id"], pending.payload["public_request_id"])
        self.assertEqual(
            lifecycle["decision"]["public_prompt_instance_id"],
            pending.payload["public_prompt_instance_id"],
        )

    def test_submit_decision_accepts_public_request_id_alias(self) -> None:
        pending = self.service.create_prompt(
            "s1",
            {
                "request_id": "s1:r2:t3:p1:movement:6",
                "request_type": "movement",
                "player_id": 1,
                "prompt_instance_id": 6,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )
        public_request_id = str(pending.payload["public_request_id"])

        result = self.service.submit_decision(
            {
                "session_id": "s1",
                "request_id": public_request_id,
                "player_id": 1,
                "choice_id": "roll",
            }
        )

        self.assertEqual(result["status"], "accepted")
        self.assertIsNone(self.service.get_pending_prompt(pending.request_id, session_id="s1"))
        self.assertIsNone(self.service.get_pending_prompt(public_request_id, session_id="s1"))
        decision = self.service.wait_for_decision(pending.request_id, timeout_ms=0, session_id="s1")
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["request_id"], pending.request_id)
        self.assertEqual(decision["public_request_id"], public_request_id)
        decision_by_public = self.service.wait_for_decision(public_request_id, timeout_ms=0, session_id="s1")
        self.assertIsNotNone(decision_by_public)
        assert decision_by_public is not None
        self.assertEqual(decision_by_public["request_id"], pending.request_id)
        self.assertEqual(decision_by_public["public_request_id"], public_request_id)
        lifecycle = self.service.get_prompt_lifecycle(pending.request_id, session_id="s1")
        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle["request_id"], pending.request_id)
        self.assertEqual(lifecycle["decision"]["request_id"], pending.request_id)
        self.assertEqual(lifecycle["decision"]["public_request_id"], public_request_id)

    def test_module_decision_command_carries_prompt_instance_id_for_public_request_alias(self) -> None:
        command_store = CapturingCommandStore()
        service = PromptService(command_store=command_store)
        pending = service.create_prompt(
            "s1",
            {
                **_batch_prompt(player_id=1),
                "request_id": "batch:explicit:prompt:p1",
                "prompt_instance_id": 31,
            },
        )
        public_request_id = str(pending.payload["public_request_id"])

        result = service.submit_decision(
            {
                "session_id": "s1",
                "request_id": public_request_id,
                "player_id": 1,
                "choice_id": "yes",
            }
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(command_store.commands[0]["payload"]["request_id"], pending.request_id)
        self.assertEqual(command_store.commands[0]["payload"]["prompt_instance_id"], 31)

    def test_simultaneous_batch_decisions_wait_for_collector_completion(self) -> None:
        collector = BatchCollectorStub(
            [
                BatchCollectorResult(status="pending", remaining_player_ids=[2]),
                BatchCollectorResult(
                    status="completed",
                    remaining_player_ids=[],
                    command={"seq": 9, "session_id": "s1", "type": "batch_complete"},
                ),
            ]
        )
        service = PromptService(batch_collector=collector)
        for player_id in [1, 2]:
            service.create_prompt("s1", _batch_prompt(player_id=player_id))

        first = service.submit_decision(
            {"session_id": "s1", "request_id": "batch:1:p1", "player_id": 1, "choice_id": "yes"}
        )
        second = service.submit_decision(
            {"session_id": "s1", "request_id": "batch:1:p2", "player_id": 2, "choice_id": "no"}
        )

        self.assertEqual(first["status"], "accepted")
        self.assertIsNone(first["command_seq"])
        self.assertEqual(first["batch_status"], "pending")
        self.assertEqual(first["remaining_player_ids"], [2])
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(second["command_seq"], 9)
        self.assertEqual(second["batch_status"], "completed")
        self.assertEqual([call["player_id"] for call in collector.calls], [1, 2])
        self.assertEqual(service.wait_for_decision("batch:1:p1", timeout_ms=0, session_id="s1")["choice_id"], "yes")

    def test_simultaneous_batch_timeout_fallback_uses_collector(self) -> None:
        collector = BatchCollectorStub(
            [
                BatchCollectorResult(
                    status="completed",
                    remaining_player_ids=[],
                    command={"seq": 11, "session_id": "s1", "type": "batch_complete"},
                )
            ]
        )
        service = PromptService(batch_collector=collector)
        pending = service.create_prompt("s1", _batch_prompt(player_id=1))

        decision = service.record_timeout_fallback_decision(pending, choice_id="yes", submitted_at_ms=123)

        self.assertEqual(decision["status"], "accepted")
        self.assertEqual(decision["command_seq"], 11)
        self.assertEqual(decision["batch_status"], "completed")
        self.assertEqual(collector.calls[0]["response"]["provider"], "timeout_fallback")

    def test_records_prompt_lifecycle_from_create_to_resolve(self) -> None:
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

        resolved = self.service.get_prompt_lifecycle("r1_lifecycle")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved["state"], "resolved")
        self.assertEqual(resolved["decision"]["choice_id"], "roll")
        self.assertEqual(resolved["decision"]["view_commit_seq_seen"], 7)
        self.assertEqual(
            [event["state"] for event in resolved["state_history"]],
            ["created", "delivered", "decision_received", "accepted", "resolved"],
        )
        self.assertEqual(resolved["resolved_at_ms"], resolved["updated_at_ms"])

    def test_failed_command_append_records_stale_without_deleting_active_prompt(self) -> None:
        service = PromptService(command_store=FailingCommandStore())
        service.create_prompt(
            "s1",
            {
                "request_id": "r_stale_active",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
            },
        )

        result = service.submit_decision(
            {
                "session_id": "s1",
                "request_id": "r_stale_active",
                "player_id": 1,
                "choice_id": "roll",
                "view_commit_seq_seen": 3,
            }
        )

        self.assertEqual(result, {"status": "stale", "reason": "command_append_failed"})
        self.assertIsNotNone(service.get_pending_prompt("r_stale_active", session_id="s1"))
        lifecycle = service.get_prompt_lifecycle("r_stale_active", session_id="s1")
        self.assertIsNotNone(lifecycle)
        assert lifecycle is not None
        self.assertEqual(lifecycle["state"], "stale")
        self.assertEqual(
            [event["state"] for event in lifecycle["state_history"]],
            ["created", "decision_received", "stale"],
        )
        self.assertEqual(lifecycle["stale_decisions"][0]["choice_id"], "roll")

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
