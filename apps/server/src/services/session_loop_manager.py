from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Awaitable, Callable

from apps.server.src.infra.structured_log import log_event


class SessionLoopManager:
    """Own one scheduled command-drain task per session."""

    def __init__(
        self,
        *,
        session_loop: Any,
        task_factory: Callable[[Awaitable[None]], asyncio.Task[None]] | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_delay_sec: float = 0.05,
        retry_deadline_sec: float = 30.0,
        max_commands_per_wakeup: int = 8,
    ) -> None:
        self._session_loop = session_loop
        self._task_factory = task_factory
        self._sleeper = sleeper
        self._retry_delay_sec = max(0.001, float(retry_delay_sec))
        self._retry_deadline_sec = max(self._retry_delay_sec, float(retry_deadline_sec))
        self._max_commands_per_wakeup = max(1, int(max_commands_per_wakeup))
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def wake(
        self,
        *,
        session_id: str,
        command_ref: dict[str, Any] | None = None,
        trigger: str,
    ) -> dict[str, Any]:
        existing_task = self._tasks.get(session_id)
        command_seq = _command_seq(command_ref or {})
        if existing_task is not None and not existing_task.done():
            log_event(
                "session_loop_wakeup_deduped",
                session_id=session_id,
                command_seq=command_seq,
                trigger=trigger,
            )
            result: dict[str, Any] = {"status": "deduped"}
            if command_seq is not None:
                result["command_seq"] = command_seq
            return result

        task = self._create_task(self._run(session_id=session_id, trigger=trigger))
        self._tasks[session_id] = task

        def _drop_completed_task(done_task: asyncio.Task[None]) -> None:
            if self._tasks.get(session_id) is done_task:
                self._tasks.pop(session_id, None)

        task.add_done_callback(_drop_completed_task)
        log_event(
            "session_loop_wakeup_scheduled",
            session_id=session_id,
            command_seq=command_seq,
            trigger=trigger,
        )
        result = {"status": "scheduled"}
        if command_seq is not None:
            result["command_seq"] = command_seq
        return result

    async def process_session_once(
        self,
        *,
        session_id: str,
        trigger: str,
        max_commands: int | None = None,
    ) -> dict[str, Any]:
        return await self._session_loop.run_until_idle(
            session_id=session_id,
            trigger=trigger,
            max_commands=max_commands or self._max_commands_per_wakeup,
        )

    async def _run(self, *, session_id: str, trigger: str) -> None:
        started = time.perf_counter()
        try:
            while True:
                result = await self.process_session_once(session_id=session_id, trigger=trigger)
                status = str((result or {}).get("status") or "")
                if status not in {"deferred", "yielded"}:
                    break
                elapsed = time.perf_counter() - started
                if elapsed >= self._retry_deadline_sec:
                    event_name = (
                        "session_loop_yielded_retry_exhausted"
                        if status == "yielded"
                        else "session_loop_deferred_retry_exhausted"
                    )
                    log_event(
                        event_name,
                        session_id=session_id,
                        trigger=trigger,
                        duration_ms=int(elapsed * 1000),
                        reason=(result or {}).get("reason"),
                    )
                    break
                if status == "deferred":
                    await self._sleeper(self._retry_delay_sec)
        except Exception as exc:  # pragma: no cover - defensive background path
            log_event(
                "session_loop_wakeup_failed",
                session_id=session_id,
                trigger=trigger,
                error_type=exc.__class__.__name__,
                error=repr(exc),
                traceback=traceback.format_exc(),
            )
        finally:
            log_event(
                "session_loop_wakeup_finished",
                session_id=session_id,
                trigger=trigger,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    def _create_task(self, awaitable: Awaitable[None]) -> asyncio.Task[None]:
        if self._task_factory is not None:
            return self._task_factory(awaitable)
        return asyncio.create_task(awaitable)


def _command_seq(command_ref: dict[str, Any]) -> int | None:
    for field_name in ("command_seq", "seq"):
        value = command_ref.get(field_name)
        try:
            command_seq = int(value)
        except (TypeError, ValueError):
            continue
        if command_seq > 0:
            return command_seq
    return None
