from __future__ import annotations

import copy
import unittest

from apps.server.src.services.command_boundary_finalizer import CommandBoundaryFinalizer


class _AuthoritativeStore:
    def __init__(self) -> None:
        self.commits: list[tuple[str, dict]] = []

    def commit_transition(self, session_id: str, **payload) -> None:  # noqa: ANN003
        self.commits.append((session_id, copy.deepcopy(payload)))


class _BoundaryStore:
    def __init__(self, deferred_commit: dict | None) -> None:
        self._deferred_commit = copy.deepcopy(deferred_commit)

    def deferred_commit(self) -> dict | None:
        return copy.deepcopy(self._deferred_commit)


class CommandBoundaryFinalizerTests(unittest.TestCase):
    def test_finalizes_deferred_commit_and_materializes_waiting_prompt(self) -> None:
        authoritative_store = _AuthoritativeStore()
        order: list[str] = []
        emitted: list[tuple[object, str]] = []
        materialized: list[tuple[object, str, dict]] = []
        events: list[tuple[str, dict]] = []
        boundary_store = _BoundaryStore(
            {
                "session_id": "s1",
                "current_state": {"session_id": "s1", "pending_prompt_request_id": "req_1"},
                "checkpoint": {"latest_commit_seq": 5},
                "view_state": {},
                "view_commits": {"spectator": {"commit_seq": 5}},
                "command_consumer_name": "runtime_wakeup",
                "command_seq": 7,
                "runtime_event_payload": {},
                "runtime_event_server_time_ms": 123,
                "expected_previous_commit_seq": 4,
            }
        )

        result = CommandBoundaryFinalizer(
            authoritative_store=authoritative_store,
            emit_latest_view_commit=lambda loop, session_id: (
                order.append("view_commit_emit"),
                emitted.append((loop, session_id)),
            ),
            materialize_prompt_boundaries=lambda loop, session_id, state: (
                order.append("prompt_materialize"),
                materialized.append((loop, session_id, copy.deepcopy(state))),
            ),
            logger=lambda event, **fields: events.append((event, dict(fields))),
        ).finalize(
            loop=None,
            session_id="s1",
            boundary_store=boundary_store,
            processed_command_seq=7,
            terminal_status="waiting_input",
            terminal_boundary_reason="prompt_required",
        )

        self.assertEqual(result.redis_commit_count, 1)
        self.assertEqual(result.view_commit_count, 1)
        self.assertIn("deferred_commit_copy_ms", result.timings)
        self.assertIn("authoritative_commit_ms", result.timings)
        self.assertEqual(authoritative_store.commits[0][0], "s1")
        self.assertEqual(authoritative_store.commits[0][1]["command_seq"], 7)
        self.assertEqual(emitted, [(None, "s1")])
        self.assertEqual(materialized, [(None, "s1", {"session_id": "s1", "pending_prompt_request_id": "req_1"})])
        self.assertEqual(order, ["prompt_materialize", "view_commit_emit"])
        self.assertEqual(events[0][0], "runtime_command_boundary_finalization_timing")
        self.assertEqual(events[0][1]["processed_command_seq"], 7)

    def test_no_deferred_commit_does_not_emit_or_materialize(self) -> None:
        authoritative_store = _AuthoritativeStore()
        emitted: list[tuple[object, str]] = []
        materialized: list[tuple[object, str, dict]] = []
        events: list[tuple[str, dict]] = []

        result = CommandBoundaryFinalizer(
            authoritative_store=authoritative_store,
            emit_latest_view_commit=lambda loop, session_id: emitted.append((loop, session_id)),
            materialize_prompt_boundaries=lambda loop, session_id, state: materialized.append(
                (loop, session_id, copy.deepcopy(state))
            ),
            logger=lambda event, **fields: events.append((event, dict(fields))),
        ).finalize(
            loop=None,
            session_id="s1",
            boundary_store=_BoundaryStore(None),
            processed_command_seq=7,
            terminal_status="committed",
            terminal_boundary_reason="committed",
        )

        self.assertEqual(result.redis_commit_count, 0)
        self.assertEqual(result.view_commit_count, 0)
        self.assertEqual(authoritative_store.commits, [])
        self.assertEqual(emitted, [])
        self.assertEqual(materialized, [])
        self.assertEqual(events, [])

    def test_commit_guard_blocks_deferred_commit_side_effects(self) -> None:
        authoritative_store = _AuthoritativeStore()
        emitted: list[tuple[object, str]] = []
        materialized: list[tuple[object, str, dict]] = []
        events: list[tuple[str, dict]] = []
        boundary_store = _BoundaryStore(
            {
                "session_id": "s1",
                "current_state": {"session_id": "s1", "pending_prompt_request_id": "req_1"},
                "checkpoint": {"latest_commit_seq": 5},
                "view_state": {},
                "view_commits": {"spectator": {"commit_seq": 5}},
                "command_consumer_name": "runtime_wakeup",
                "command_seq": 7,
                "runtime_event_payload": {},
                "runtime_event_server_time_ms": 123,
                "expected_previous_commit_seq": 4,
            }
        )

        result = CommandBoundaryFinalizer(
            authoritative_store=authoritative_store,
            emit_latest_view_commit=lambda loop, session_id: emitted.append((loop, session_id)),
            materialize_prompt_boundaries=lambda loop, session_id, state: materialized.append(
                (loop, session_id, copy.deepcopy(state))
            ),
            commit_guard=lambda session_id: {
                "reason": "runtime_lease_lost_before_commit",
                "lease_owner": "other-runtime-worker",
                "guard_session_id": session_id,
            },
            logger=lambda event, **fields: events.append((event, dict(fields))),
        ).finalize(
            loop=None,
            session_id="s1",
            boundary_store=boundary_store,
            processed_command_seq=7,
            terminal_status="waiting_input",
            terminal_boundary_reason="prompt_required",
        )

        self.assertEqual(result.redis_commit_count, 0)
        self.assertEqual(result.view_commit_count, 0)
        self.assertEqual(result.blocked_reason, "runtime_lease_lost_before_commit")
        self.assertEqual(result.blocked_fields["lease_owner"], "other-runtime-worker")
        self.assertEqual(authoritative_store.commits, [])
        self.assertEqual(emitted, [])
        self.assertEqual(materialized, [])
        self.assertEqual(events[0][0], "runtime_command_boundary_commit_blocked")
        self.assertEqual(events[0][1]["processed_command_seq"], 7)
