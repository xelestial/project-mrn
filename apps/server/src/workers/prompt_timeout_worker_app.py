from __future__ import annotations

import argparse
import asyncio
import os
from typing import Sequence

from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorkerLoop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MRN prompt timeout worker.")
    parser.add_argument("--once", action="store_true", help="Run one timeout scan and exit.")
    parser.add_argument("--session-id", default=None, help="Limit timeout processing to one session.")
    parser.add_argument("--poll-interval-ms", type=int, default=None, help="Worker poll interval in milliseconds.")
    parser.add_argument("--max-iterations", type=int, default=None, help="Run at most this many loop iterations.")
    return parser


async def run_from_state(
    *,
    once: bool = False,
    session_id: str | None = None,
    poll_interval_ms: int | None = None,
    max_iterations: int | None = None,
) -> dict[str, int]:
    os.environ.setdefault("MRN_RESTART_RECOVERY_POLICY", "keep")
    from apps.server.src import state

    if state.redis_connection is None:
        raise RuntimeError("redis_required_for_standalone_timeout_worker")
    loop = PromptTimeoutWorkerLoop(
        worker=state.prompt_timeout_worker,
        poll_interval_ms=poll_interval_ms or state.runtime_settings.prompt_timeout_worker_poll_interval_ms,
        session_id=session_id,
    )
    if once:
        results = await loop.run_once()
        summary = {"iterations": 1, "timeout_count": len(results)}
    else:
        summary = await loop.run(max_iterations=max_iterations)
    log_event(
        "prompt_timeout_worker_completed" if once or max_iterations is not None else "prompt_timeout_worker_stopped",
        session_id=session_id,
        iterations=summary["iterations"],
        timeout_count=summary["timeout_count"],
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = asyncio.run(
            run_from_state(
                once=bool(args.once),
                session_id=args.session_id,
                poll_interval_ms=args.poll_interval_ms,
                max_iterations=args.max_iterations,
            )
        )
    except KeyboardInterrupt:
        return 130
    except RuntimeError as exc:
        print(str(exc))
        return 2
    print(f"iterations={summary['iterations']} timeout_count={summary['timeout_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
