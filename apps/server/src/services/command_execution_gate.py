from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from apps.server.src.infra.structured_log import log_event


class CommandExecutionGate:
    """Local in-process command execution gate for one session."""

    def __init__(self, *, runtime_task_provider: Callable[[str], Any | None]) -> None:
        self._runtime_task_provider = runtime_task_provider
        self._active_command_sessions: set[str] = set()
        self._lock = threading.Lock()

    def begin(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._active_command_sessions:
                return False
            self._active_command_sessions.add(session_id)
            return True

    def active(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._active_command_sessions

    def end(self, session_id: str) -> None:
        with self._lock:
            self._active_command_sessions.discard(session_id)

    def runtime_task_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        task = self._runtime_task_provider(session_id)
        if task is None or task.done():
            return None
        log_event(
            "runtime_command_deferred_active_runtime_task",
            session_id=session_id,
            command_seq=int(command_seq),
            consumer_name=consumer_name,
            stage=stage,
        )
        return {
            "status": "running_elsewhere",
            "reason": "runtime_task_already_active",
            "processed_command_seq": int(command_seq),
            "processed_command_consumer": consumer_name,
        }
