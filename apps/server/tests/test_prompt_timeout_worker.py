from __future__ import annotations

import asyncio
import unittest

from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorker, PromptTimeoutWorkerLoop
from apps.server.src.workers.prompt_timeout_worker_app import build_parser, health_from_state


class PromptTimeoutWorkerLoopTests(unittest.TestCase):
    def test_worker_wakes_runtime_after_timeout_command_is_accepted(self) -> None:
        prompt_service = _PromptServiceStub()
        command_router = _CommandRouterStub()
        worker = PromptTimeoutWorker(
            prompt_service=prompt_service,
            runtime_service=_RuntimeServiceStub(),
            stream_service=_StreamServiceStub(),
            command_router=command_router,
        )

        results = asyncio.run(worker.run_once(now_ms=1_000, session_id="sess_timeout"))

        self.assertEqual(
            results,
            [{"session_id": "sess_timeout", "request_id": "req_timeout", "player_id": 1, "fallback_choice_id": "dice"}],
        )
        self.assertEqual(prompt_service.recorded_request_ids, ["req_timeout"])
        self.assertEqual(
            command_router.wake_calls,
            [
                {
                    "command_ref": {
                        "status": "accepted",
                        "session_id": "sess_timeout",
                        "command_seq": 5,
                    },
                    "session_id": "sess_timeout",
                    "trigger": "timeout_fallback",
                }
            ],
        )

    def test_worker_does_not_wake_runtime_for_incomplete_batch_timeout(self) -> None:
        prompt_service = _PromptServiceStub(command_seq=None)
        command_router = _CommandRouterStub()
        worker = PromptTimeoutWorker(
            prompt_service=prompt_service,
            runtime_service=_RuntimeServiceStub(),
            stream_service=_StreamServiceStub(),
            command_router=command_router,
        )

        asyncio.run(worker.run_once(now_ms=1_000, session_id="sess_timeout"))

        self.assertEqual(command_router.wake_calls, [])

    def test_loop_runs_configured_iterations_without_websocket_heartbeat(self) -> None:
        worker = _WorkerStub(results=[[{"request_id": "r1"}], [], [{"request_id": "r2"}]])
        sleeps: list[float] = []

        async def _sleep(seconds: float) -> None:
            sleeps.append(seconds)

        loop = PromptTimeoutWorkerLoop(worker=worker, poll_interval_ms=125, sleeper=_sleep)

        summary = asyncio.run(loop.run(max_iterations=3))

        self.assertEqual(summary, {"iterations": 3, "timeout_count": 2})
        self.assertEqual(worker.calls, [None, None, None])
        self.assertEqual(sleeps, [0.125, 0.125])

    def test_loop_passes_session_scope_to_worker(self) -> None:
        worker = _WorkerStub(results=[[]])
        loop = PromptTimeoutWorkerLoop(worker=worker, poll_interval_ms=50, session_id="sess_1")

        results = asyncio.run(loop.run_once())

        self.assertEqual(results, [])
        self.assertEqual(worker.calls, ["sess_1"])

    def test_cli_parser_supports_once_mode(self) -> None:
        args = build_parser().parse_args(
            ["--once", "--session-id", "sess_2", "--poll-interval-ms", "500", "--max-iterations", "4"]
        )

        self.assertTrue(args.once)
        self.assertEqual(args.session_id, "sess_2")
        self.assertEqual(args.poll_interval_ms, 500)
        self.assertEqual(args.max_iterations, 4)

    def test_cli_parser_supports_health_mode(self) -> None:
        args = build_parser().parse_args(["--health"])

        self.assertTrue(args.health)

    def test_health_mode_reports_redis_readiness(self) -> None:
        from apps.server.src import state

        original_redis = state.redis_connection
        state.redis_connection = _HealthRedis(ok=True)  # type: ignore[assignment]
        try:
            payload = health_from_state()
        finally:
            state.redis_connection = original_redis  # type: ignore[assignment]

        self.assertEqual(
            payload,
            {
                "ok": True,
                "role": "prompt-timeout-worker",
                "redis": {"ok": True, "cluster_hash_tag": "mrn-test", "cluster_hash_tag_valid": True},
            },
        )


class _WorkerStub:
    def __init__(self, *, results: list[list[dict]]) -> None:
        self._results = list(results)
        self.calls: list[str | None] = []

    async def run_once(self, *, session_id: str | None = None) -> list[dict]:
        self.calls.append(session_id)
        if not self._results:
            return []
        return self._results.pop(0)


class _PendingPrompt:
    session_id = "sess_timeout"
    request_id = "req_timeout"
    player_id = 1
    payload = {
        "request_id": "req_timeout",
        "request_type": "movement",
        "player_id": 1,
        "legal_choices": [{"choice_id": "dice"}],
    }


class _PromptServiceStub:
    def __init__(self, *, command_seq: int | None = 5) -> None:
        self.command_seq = command_seq
        self.recorded_request_ids: list[str] = []
        self.cleaned: list[str | None] = []

    def timeout_pending(self, *, now_ms: int | None, session_id: str | None) -> list[_PendingPrompt]:
        return [_PendingPrompt()]

    def record_timeout_fallback_decision(
        self,
        pending: _PendingPrompt,
        *,
        choice_id: str,
        submitted_at_ms: int | None = None,
    ) -> dict:
        self.recorded_request_ids.append(pending.request_id)
        return {"status": "accepted", "session_id": pending.session_id, "command_seq": self.command_seq}

    def cleanup_orphaned_pending(self, **_kwargs) -> None:
        return None


class _RuntimeServiceStub:
    async def execute_prompt_fallback(self, **_kwargs) -> dict:
        return {"status": "executed", "choice_id": "dice", "executed_at_ms": 1_001}


class _StreamServiceStub:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, dict]] = []

    async def publish(self, session_id: str, message_type: str, payload: dict) -> None:
        self.messages.append((session_id, message_type, payload))


class _CommandRouterStub:
    def __init__(self) -> None:
        self.wake_calls: list[dict] = []

    def wake_after_accept(self, *, command_ref: dict, session_id: str, trigger: str) -> dict:
        self.wake_calls.append(
            {
                "command_ref": command_ref,
                "session_id": session_id,
                "trigger": trigger,
            }
        )
        return {"status": "scheduled", "command_seq": command_ref.get("command_seq")}


class _HealthRedis:
    def __init__(self, *, ok: bool) -> None:
        self.ok = ok

    def health_check(self) -> dict[str, object]:
        return {"ok": self.ok, "cluster_hash_tag": "mrn-test", "cluster_hash_tag_valid": True}


if __name__ == "__main__":
    unittest.main()
