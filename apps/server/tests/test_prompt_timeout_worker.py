from __future__ import annotations

import asyncio
import unittest

from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorkerLoop
from apps.server.src.workers.prompt_timeout_worker_app import build_parser


class PromptTimeoutWorkerLoopTests(unittest.TestCase):
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


class _WorkerStub:
    def __init__(self, *, results: list[list[dict]]) -> None:
        self._results = list(results)
        self.calls: list[str | None] = []

    async def run_once(self, *, session_id: str | None = None) -> list[dict]:
        self.calls.append(session_id)
        if not self._results:
            return []
        return self._results.pop(0)


if __name__ == "__main__":
    unittest.main()
