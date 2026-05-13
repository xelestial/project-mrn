from __future__ import annotations

import time
from typing import Any

from apps.server.src.infra.structured_log import log_event


class SessionLoop:
    """Drain one session's command inbox through the runtime command boundary."""

    def __init__(
        self,
        *,
        command_store: Any,
        session_service: Any,
        runtime_service: Any,
        consumer_name: str = "runtime_wakeup",
        command_scan_limit: int = 32,
    ) -> None:
        self._command_store = command_store
        self._session_service = session_service
        self._runtime_service = runtime_service
        self._consumer_name = str(consumer_name or "runtime_wakeup")
        self._command_scan_limit = max(1, int(command_scan_limit))

    async def run_until_idle(
        self,
        *,
        session_id: str,
        trigger: str,
        max_commands: int = 8,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        processed_count = 0
        observed_count = 0
        last_command_seq: int | None = None
        max_to_process = max(1, int(max_commands))

        while processed_count < max_to_process:
            self._refresh_sessions()
            command = self._next_command(session_id)
            if command is None:
                return self._result(
                    "idle",
                    session_id=session_id,
                    trigger=trigger,
                    started=started,
                    processed_count=processed_count,
                    observed_count=observed_count,
                    last_command_seq=last_command_seq,
                )

            command_seq = self._command_seq(command)
            command_type = str(command.get("type") or "").strip()
            last_command_seq = command_seq
            if command_seq <= 0:
                return self._result(
                    "blocked",
                    session_id=session_id,
                    trigger=trigger,
                    started=started,
                    processed_count=processed_count,
                    observed_count=observed_count,
                    last_command_seq=last_command_seq,
                    reason="invalid_command_seq",
                )

            if command_type == "decision_resolved":
                self._save_offset(session_id, command_seq)
                observed_count += 1
                continue

            if command_type != "decision_submitted":
                return self._result(
                    "blocked",
                    session_id=session_id,
                    trigger=trigger,
                    started=started,
                    processed_count=processed_count,
                    observed_count=observed_count,
                    last_command_seq=last_command_seq,
                    reason="unsupported_command_type",
                    command_type=command_type,
                )

            before_offset = self._load_offset(session_id)
            result = await self._process_command(session_id=session_id, command_seq=command_seq)
            result_status = str((result or {}).get("status") or "").strip()
            processed_count += 1

            if result_status == "running_elsewhere":
                return self._result(
                    "deferred",
                    session_id=session_id,
                    trigger=trigger,
                    started=started,
                    processed_count=processed_count,
                    observed_count=observed_count,
                    last_command_seq=last_command_seq,
                    reason=(result or {}).get("reason") or "running_elsewhere",
                    runtime_result=result or {},
                )

            after_offset = self._load_offset(session_id)
            if after_offset <= before_offset:
                return self._result(
                    "blocked",
                    session_id=session_id,
                    trigger=trigger,
                    started=started,
                    processed_count=processed_count,
                    observed_count=observed_count,
                    last_command_seq=last_command_seq,
                    reason="consumer_offset_not_advanced",
                    runtime_result=result or {},
                )

        return self._result(
            "yielded",
            session_id=session_id,
            trigger=trigger,
            started=started,
            processed_count=processed_count,
            observed_count=observed_count,
            last_command_seq=last_command_seq,
            reason="max_commands_reached",
        )

    def _next_command(self, session_id: str) -> dict[str, Any] | None:
        last_seq = self._load_offset(session_id)
        list_after = getattr(self._command_store, "list_commands_after", None)
        if callable(list_after):
            commands = list_after(session_id, last_seq, limit=self._command_scan_limit)
        else:
            list_commands = getattr(self._command_store, "list_commands", None)
            commands = list_commands(session_id) if callable(list_commands) else []
            commands = [command for command in commands if self._command_seq(command) > last_seq]
        if not commands:
            return None
        return sorted(commands, key=self._command_seq)[0]

    async def _process_command(self, *, session_id: str, command_seq: int) -> dict[str, Any]:
        session = self._session_service.get_session(session_id)
        runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
        return await self._runtime_service.process_command_once(
            session_id=session_id,
            command_seq=int(command_seq),
            consumer_name=self._consumer_name,
            seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
            policy_mode=runtime_cfg.get("policy_mode"),
        )

    def _load_offset(self, session_id: str) -> int:
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        if not callable(load_offset):
            return 0
        return max(0, int(load_offset(self._consumer_name, session_id)))

    def _save_offset(self, session_id: str, seq: int) -> None:
        save_offset = getattr(self._command_store, "save_consumer_offset", None)
        if callable(save_offset):
            save_offset(self._consumer_name, session_id, int(seq))

    def _refresh_sessions(self) -> None:
        refresh = getattr(self._session_service, "refresh_from_store", None)
        if callable(refresh):
            refresh()

    @staticmethod
    def _command_seq(command: dict[str, Any]) -> int:
        try:
            return int(command.get("seq", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _result(
        status: str,
        *,
        session_id: str,
        trigger: str,
        started: float,
        processed_count: int,
        observed_count: int,
        last_command_seq: int | None,
        **extra: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": status,
            "session_id": session_id,
            "trigger": trigger,
            "processed_count": int(processed_count),
            "observed_count": int(observed_count),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        if last_command_seq is not None:
            payload["last_command_seq"] = int(last_command_seq)
        payload.update(extra)
        log_event("session_loop_drain_finished", **payload)
        return payload
