from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


class CommandStreamWakeupWorker:
    def __init__(
        self,
        *,
        command_store,
        session_service,
        runtime_service,
        poll_interval_ms: int = 250,
        consumer_name: str = "runtime_wakeup",
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._command_store = command_store
        self._session_service = session_service
        self._runtime_service = runtime_service
        self._poll_interval_ms = max(50, int(poll_interval_ms))
        self._consumer_name = str(consumer_name or "runtime_wakeup")
        self._sleeper = sleeper
        self._last_processed_seq: dict[str, int] = {}

    async def run_once(self, *, session_id: str | None = None) -> list[dict]:
        self._refresh_sessions()
        session_ids = [session_id] if session_id else self._active_session_ids()
        wakeups: list[dict] = []
        for current_session_id in session_ids:
            if not current_session_id:
                continue
            last_seq = self._load_offset(current_session_id)
            for command in self._command_store.list_commands(current_session_id):
                seq = int(command.get("seq", 0))
                if seq <= last_seq:
                    continue
                status = self._runtime_service.runtime_status(current_session_id)
                if status.get("status") in {"recovery_required", "idle", "running_elsewhere", "waiting_input"}:
                    if self._is_stale_waiting_command(status, command):
                        self._save_offset(current_session_id, seq)
                        last_seq = seq
                        continue
                    processed = await self._process_or_start_runtime(current_session_id, seq)
                    if not processed:
                        self._save_offset(current_session_id, seq)
                    last_seq = seq
                    wakeups.append(
                        {
                            "session_id": current_session_id,
                            "command_seq": seq,
                            "command_type": command.get("type"),
                            "runtime_status": status.get("status"),
                        }
                    )
                elif status.get("status") == "running":
                    self._save_offset(current_session_id, seq)
                    last_seq = seq
        return wakeups

    async def run(
        self,
        *,
        max_iterations: int | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> dict[str, int]:
        iterations = 0
        wakeup_count = 0
        while stop_event is None or not stop_event.is_set():
            wakeups = await self.run_once()
            iterations += 1
            wakeup_count += len(wakeups)
            if max_iterations is not None and iterations >= max(0, int(max_iterations)):
                break
            await self._sleeper(self._poll_interval_ms / 1000.0)
        return {"iterations": iterations, "wakeup_count": wakeup_count}

    def _active_session_ids(self) -> list[str]:
        result: list[str] = []
        for session in self._session_service.list_sessions():
            status = getattr(session, "status", "")
            status_value = getattr(status, "value", status)
            if str(status_value) == "in_progress":
                result.append(str(session.session_id))
        return result

    def _refresh_sessions(self) -> None:
        refresh = getattr(self._session_service, "refresh_from_store", None)
        if callable(refresh):
            refresh()

    async def _start_runtime(self, session_id: str) -> None:
        session = self._session_service.get_session(session_id)
        runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
        await self._runtime_service.start_runtime(
            session_id=session_id,
            seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
            policy_mode=runtime_cfg.get("policy_mode"),
        )

    async def _process_or_start_runtime(self, session_id: str, seq: int) -> bool:
        self._refresh_sessions()
        if callable(getattr(self._runtime_service, "process_command_once", None)):
            session = self._session_service.get_session(session_id)
            runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
            await self._runtime_service.process_command_once(
                session_id=session_id,
                command_seq=int(seq),
                consumer_name=self._consumer_name,
                seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
                policy_mode=runtime_cfg.get("policy_mode"),
            )
            self._last_processed_seq[session_id] = int(seq)
            return True
        await self._start_runtime(session_id)
        return False

    def _load_offset(self, session_id: str) -> int:
        if callable(getattr(self._command_store, "load_consumer_offset", None)):
            return int(self._command_store.load_consumer_offset(self._consumer_name, session_id))
        return self._last_processed_seq.get(session_id, 0)

    def _save_offset(self, session_id: str, seq: int) -> None:
        if callable(getattr(self._command_store, "save_consumer_offset", None)):
            self._command_store.save_consumer_offset(self._consumer_name, session_id, seq)
        self._last_processed_seq[session_id] = int(seq)

    @staticmethod
    def _is_stale_waiting_command(status: dict, command: dict) -> bool:
        if status.get("status") != "waiting_input":
            return False
        waiting_request_id = CommandStreamWakeupWorker._waiting_prompt_request_id(status)
        command_request_id = CommandStreamWakeupWorker._command_request_id(command)
        if waiting_request_id and command_request_id and command_request_id != waiting_request_id:
            return True
        return CommandStreamWakeupWorker._module_identity_mismatch(status, command)

    @staticmethod
    def _waiting_prompt_request_id(status: dict) -> str:
        recovery = status.get("recovery_checkpoint")
        if not isinstance(recovery, dict):
            return ""
        checkpoint = recovery.get("checkpoint")
        if not isinstance(checkpoint, dict):
            return ""
        return str(checkpoint.get("waiting_prompt_request_id") or "").strip()

    @staticmethod
    def _command_request_id(command: dict) -> str:
        payload = command.get("payload")
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("request_id") or "").strip()

    @staticmethod
    def _module_identity_mismatch(status: dict, command: dict) -> bool:
        payload = command.get("payload")
        if not isinstance(payload, dict):
            return False
        recovery = status.get("recovery_checkpoint")
        if not isinstance(recovery, dict):
            return False
        checkpoint = recovery.get("checkpoint")
        if not isinstance(checkpoint, dict):
            return False
        field_pairs = (
            ("frame_id", "active_frame_id"),
            ("module_id", "active_module_id"),
            ("module_type", "active_module_type"),
            ("module_cursor", "active_module_cursor"),
        )
        for command_field, checkpoint_field in field_pairs:
            command_value = str(payload.get(command_field) or "").strip()
            checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
            if command_value and checkpoint_value and command_value != checkpoint_value:
                return True
        return False
