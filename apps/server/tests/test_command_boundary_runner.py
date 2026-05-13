from __future__ import annotations

import unittest

from apps.server.src.services.command_boundary_runner import CommandBoundaryRunner


class CommandBoundaryRunnerTests(unittest.TestCase):
    def test_runner_owns_boundary_store_transition_loop_and_finalization(self) -> None:
        original_store = object()
        boundary_store = _BoundaryStore()
        calls: list[tuple[str, object]] = []

        def store_factory(authoritative_store: object, *, session_id: str, base_commit_seq: int) -> _BoundaryStore:
            calls.append(("store_factory", (authoritative_store, session_id, base_commit_seq)))
            return boundary_store

        def latest_view_commit_seq(session_id: str) -> int:
            calls.append(("latest_view_commit_seq", session_id))
            return 14

        def prepare_transition_context(*args: object, **kwargs: object) -> dict:
            calls.append(("prepare", kwargs.get("game_state_store_override")))
            self.assertIs(kwargs.get("game_state_store_override"), boundary_store)
            self.assertFalse(kwargs.get("publish_external_side_effects"))
            return {"prepared": True}

        def run_transition_once(*args: object, **kwargs: object) -> dict:
            calls.append(("transition", kwargs.get("game_state_store_override")))
            self.assertIs(kwargs.get("game_state_store_override"), boundary_store)
            self.assertEqual(kwargs.get("transition_context"), {"prepared": True})
            if len([call for call in calls if call[0] == "transition"]) == 1:
                self.assertEqual(args[5], "runtime_wakeup")
                self.assertEqual(args[6], 7)
                return {
                    "status": "running",
                    "reason": "continue",
                    "runtime_module": {"module_type": "MoveModule", "module_id": "m1"},
                }
            self.assertIsNone(args[5])
            self.assertIsNone(args[6])
            return {
                "status": "waiting_input",
                "reason": "prompt_required",
                "module_type": "TrickWindowModule",
                "module_id": "m2",
            }

        def finalizer_factory(**kwargs: object) -> _Finalizer:
            calls.append(("finalizer_factory", kwargs.get("authoritative_store")))
            self.assertIs(kwargs.get("authoritative_store"), original_store)
            return _Finalizer(calls)

        runner = CommandBoundaryRunner(
            game_state_store=original_store,
            latest_view_commit_seq=latest_view_commit_seq,
            prepare_transition_context=prepare_transition_context,
            run_transition_once=run_transition_once,
            emit_latest_view_commit=lambda *args, **kwargs: None,
            materialize_prompt_boundaries=lambda *args, **kwargs: None,
            commit_guard=lambda session_id: None,
            store_factory=store_factory,
            finalizer_factory=finalizer_factory,
        )

        result = runner.run(
            loop=None,
            session_id="s1",
            seed=42,
            policy_mode=None,
            max_transitions=5,
            first_command_consumer_name="runtime_wakeup",
            first_command_seq=7,
        )

        self.assertEqual(result["status"], "waiting_input")
        self.assertEqual(result["transitions"], 2)
        self.assertEqual(result["module_transition_count"], 2)
        self.assertEqual(result["redis_commit_count"], 1)
        self.assertEqual(result["view_commit_count"], 1)
        self.assertEqual(result["internal_state_stage_count"], 2)
        self.assertEqual(result["processed_command_seq"], 7)
        self.assertEqual(
            result["module_trace"],
            [
                {
                    "index": 1,
                    "status": "running",
                    "reason": "continue",
                    "runtime_module": {"module_type": "MoveModule", "module_id": "m1"},
                },
                {
                    "index": 2,
                    "status": "waiting_input",
                    "reason": "prompt_required",
                    "module_type": "TrickWindowModule",
                    "module_id": "m2",
                },
            ],
        )
        self.assertIn(("finalize", ("s1", 7, "waiting_input", "prompt_required")), calls)


class _BoundaryStore:
    redis_commit_count = 3
    view_commit_count = 4
    internal_state_stage_count = 2


class _Finalizer:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls

    def finalize(
        self,
        *,
        loop: object,
        session_id: str,
        boundary_store: _BoundaryStore,
        processed_command_seq: int,
        terminal_status: str,
        terminal_boundary_reason: str,
    ) -> "_Finalization":
        del loop, boundary_store
        self._calls.append(
            (
                "finalize",
                (session_id, processed_command_seq, terminal_status, terminal_boundary_reason),
            )
        )
        return _Finalization()


class _Finalization:
    redis_commit_count = 1
    view_commit_count = 1
    blocked_reason = None
    blocked_fields = None

    def result_fields(self) -> dict:
        return {"processed_command_seq": 7}


if __name__ == "__main__":
    unittest.main()
