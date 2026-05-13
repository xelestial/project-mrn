from __future__ import annotations

import inspect
import time
from typing import Any

from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.realtime_persistence import ViewCommitSequenceConflict


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class SessionCommandExecutor:
    """Own the command-processing lifecycle for one command boundary."""

    def __init__(self, *, runtime_boundary: Any) -> None:
        self._runtime_boundary = runtime_boundary

    async def process_command_once(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        seed: int = 42,
        policy_mode: str | None = None,
    ) -> dict[str, Any]:
        boundary = self._runtime_boundary
        process_started = time.perf_counter()
        command_seq = int(command_seq)
        lease_renewer: Any = None
        lease_acquired = False

        task_guard = boundary.runtime_task_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage="before_begin",
        )
        if task_guard is not None:
            return task_guard

        if not boundary.begin_command_processing(session_id):
            return {
                "status": "running_elsewhere",
                "reason": "command_processing_already_active",
                "processed_command_seq": command_seq,
                "processed_command_consumer": consumer_name,
            }

        try:
            task_guard = boundary.runtime_task_processing_guard(
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=command_seq,
                stage="after_begin",
            )
            if task_guard is not None:
                return task_guard

            pre_guard = boundary.command_processing_guard(
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=command_seq,
                stage="before_lease",
            )
            if pre_guard is not None:
                return pre_guard

            if not boundary.acquire_runtime_lease(session_id):
                return {
                    "status": "running_elsewhere",
                    "lease_owner": boundary.runtime_lease_owner(session_id),
                }
            lease_acquired = True

            lease_renewer = boundary.start_runtime_lease_renewer(
                session_id=session_id,
                reason="session_command_executor",
                command_seq=command_seq,
                consumer_name=consumer_name,
            )

            post_guard = boundary.command_processing_guard(
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=command_seq,
                stage="after_lease",
            )
            if post_guard is not None:
                return post_guard

            boundary.mark_command_processing_started(
                session_id=session_id,
                command_seq=command_seq,
                consumer_name=consumer_name,
            )
            pre_executor_ms = _duration_ms(process_started)
            executor_started = time.perf_counter()
            result = await boundary.run_command_boundary(
                session_id=session_id,
                seed=seed,
                policy_mode=policy_mode,
                consumer_name=consumer_name,
                command_seq=command_seq,
            )
            executor_wall_ms = _duration_ms(executor_started)
            boundary.record_command_process_timing(
                session_id=session_id,
                command_seq=command_seq,
                consumer_name=consumer_name,
                result=result,
                process_started=process_started,
                pre_executor_ms=pre_executor_ms,
                executor_wall_ms=executor_wall_ms,
            )
            await _maybe_await(boundary.apply_command_process_result(session_id=session_id, result=result))
            return result
        except ViewCommitSequenceConflict as exc:
            return await _maybe_await(
                boundary.handle_command_commit_conflict(
                    session_id=session_id,
                    command_seq=command_seq,
                    consumer_name=consumer_name,
                    exc=exc,
                )
            )
        except Exception as exc:
            await _maybe_await(boundary.handle_command_failure(session_id=session_id, exc=exc))
            raise
        finally:
            if lease_renewer is not None:
                boundary.stop_runtime_lease_renewer(lease_renewer)
            if lease_acquired:
                boundary.release_runtime_lease(session_id)
            boundary.end_command_processing(session_id)


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
        self._command_executor = SessionCommandExecutor(runtime_boundary=runtime_service)
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
        return await self._command_executor.process_command_once(
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
