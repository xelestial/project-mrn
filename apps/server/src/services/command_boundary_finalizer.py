from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable

from apps.server.src.infra.structured_log import log_event


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


@dataclass(frozen=True, slots=True)
class CommandBoundaryFinalization:
    redis_commit_count: int
    view_commit_count: int
    total_ms: int
    timings: dict[str, int]

    def result_fields(self) -> dict[str, int]:
        return {
            "command_boundary_finalization_ms": self.total_ms,
            **self.timings,
        }


class CommandBoundaryFinalizer:
    def __init__(
        self,
        *,
        authoritative_store: object,
        emit_latest_view_commit: Callable[[Any, str], object],
        materialize_prompt_boundaries: Callable[[Any, str, dict], object],
        logger: Callable[..., None] = log_event,
    ) -> None:
        self._authoritative_store = authoritative_store
        self._emit_latest_view_commit = emit_latest_view_commit
        self._materialize_prompt_boundaries = materialize_prompt_boundaries
        self._logger = logger

    def finalize(
        self,
        *,
        loop: Any,
        session_id: str,
        boundary_store: object,
        processed_command_seq: int,
        terminal_status: str,
        terminal_boundary_reason: str,
    ) -> CommandBoundaryFinalization:
        started = time.perf_counter()
        phase_started = started
        timings: dict[str, int] = {}

        def mark_phase(name: str) -> None:
            nonlocal phase_started
            now = time.perf_counter()
            timings[name] = int((now - phase_started) * 1000)
            phase_started = now

        deferred_commit = self._deferred_commit(boundary_store)
        mark_phase("deferred_commit_copy_ms")
        redis_commit_count = 0
        view_commit_count = 0

        if deferred_commit is not None:
            commit_session_id = str(deferred_commit.pop("session_id"))
            self._authoritative_store.commit_transition(commit_session_id, **deferred_commit)
            mark_phase("authoritative_commit_ms")
            redis_commit_count = 1

            if deferred_commit.get("view_commits"):
                view_commit_count = 1
            self._emit_latest_view_commit(loop, session_id)
            mark_phase("view_commit_emit_ms")

            current_state = deferred_commit.get("current_state")
            if str(terminal_status or "") == "waiting_input" and isinstance(current_state, dict):
                self._materialize_prompt_boundaries(loop, session_id, current_state)
            mark_phase("prompt_materialize_ms")

        total_ms = _duration_ms(started)
        if deferred_commit is not None:
            self._logger(
                "runtime_command_boundary_finalization_timing",
                session_id=session_id,
                processed_command_seq=processed_command_seq,
                terminal_status=terminal_status,
                terminal_boundary_reason=terminal_boundary_reason,
                redis_commit_count=redis_commit_count,
                view_commit_count=view_commit_count,
                total_ms=total_ms,
                **timings,
            )
        return CommandBoundaryFinalization(
            redis_commit_count=redis_commit_count,
            view_commit_count=view_commit_count,
            total_ms=total_ms,
            timings=timings,
        )

    @staticmethod
    def _deferred_commit(boundary_store: object) -> dict | None:
        deferred_commit = getattr(boundary_store, "deferred_commit", None)
        if not callable(deferred_commit):
            return None
        value = deferred_commit()
        return copy.deepcopy(value) if isinstance(value, dict) else None
