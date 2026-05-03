from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Sequence

from apps.server.src.infra.structured_log import log_event


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MRN command stream wakeup worker.")
    parser.add_argument("--health", action="store_true", help="Check Redis/worker readiness and exit.")
    parser.add_argument("--once", action="store_true", help="Run one command scan and exit.")
    parser.add_argument("--session-id", default=None, help="Limit command wakeup processing to one session.")
    parser.add_argument("--max-iterations", type=int, default=None, help="Run at most this many loop iterations.")
    return parser


def health_from_state() -> dict[str, object]:
    os.environ.setdefault("MRN_RESTART_RECOVERY_POLICY", "keep")
    from apps.server.src import state

    if state.redis_connection is None or state.command_wakeup_worker is None:
        raise RuntimeError("redis_required_for_command_wakeup_worker")
    redis_health = state.redis_connection.health_check()
    ok = bool(redis_health.get("ok") is True)
    return {
        "ok": ok,
        "role": "command-wakeup-worker",
        "redis": redis_health,
    }


async def run_from_state(
    *,
    once: bool = False,
    session_id: str | None = None,
    max_iterations: int | None = None,
) -> dict[str, int]:
    os.environ.setdefault("MRN_RESTART_RECOVERY_POLICY", "keep")
    from apps.server.src import state

    if state.redis_connection is None or state.command_wakeup_worker is None:
        raise RuntimeError("redis_required_for_command_wakeup_worker")
    if once:
        wakeups = await state.command_wakeup_worker.run_once(session_id=session_id)
        summary = {"iterations": 1, "wakeup_count": len(wakeups)}
    else:
        summary = await state.command_wakeup_worker.run(max_iterations=max_iterations)
    log_event(
        "command_wakeup_worker_completed" if once or max_iterations is not None else "command_wakeup_worker_stopped",
        session_id=session_id,
        iterations=summary["iterations"],
        wakeup_count=summary["wakeup_count"],
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if bool(args.health):
            payload = health_from_state()
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0 if payload.get("ok") is True else 2
        summary = asyncio.run(
            run_from_state(
                once=bool(args.once),
                session_id=args.session_id,
                max_iterations=args.max_iterations,
            )
        )
    except KeyboardInterrupt:
        return 130
    except RuntimeError as exc:
        print(str(exc))
        return 2
    print(f"iterations={summary['iterations']} wakeup_count={summary['wakeup_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
