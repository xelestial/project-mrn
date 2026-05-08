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
        self._reprocessed_consumed_commands: set[tuple[str, int, str]] = set()

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
                    if self._is_runtime_resume_command(command):
                        status = self._runtime_service.runtime_status(current_session_id)
                        if self._is_waiting_for_resume_command(status, command):
                            request_id = self._command_request_id(command)
                            reprocess_key = (current_session_id, seq, request_id)
                            if reprocess_key in self._reprocessed_consumed_commands:
                                continue
                            await self._process_or_start_runtime(current_session_id, seq)
                            self._reprocessed_consumed_commands.add(reprocess_key)
                            wakeups.append(
                                {
                                    "session_id": current_session_id,
                                    "command_seq": seq,
                                    "command_type": command.get("type"),
                                    "runtime_status": status.get("status"),
                                    "reprocessed_consumed": True,
                                }
                            )
                            break
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
                    break
                elif status.get("status") == "running":
                    if self._is_runtime_observation_command(command):
                        self._save_offset(current_session_id, seq)
                        last_seq = seq
                    else:
                        break
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
    def _is_runtime_observation_command(command: dict) -> bool:
        return str(command.get("type") or "").strip() == "decision_resolved"

    @staticmethod
    def _is_runtime_resume_command(command: dict) -> bool:
        return str(command.get("type") or "").strip() == "decision_submitted"

    @staticmethod
    def _is_stale_waiting_command(status: dict, command: dict) -> bool:
        if status.get("status") != "waiting_input":
            return False
        if CommandStreamWakeupWorker._has_waiting_request_id_mismatch(status, command):
            return True
        return CommandStreamWakeupWorker._module_identity_mismatch(status, command)

    @staticmethod
    def _is_waiting_for_resume_command(status: dict, command: dict) -> bool:
        if status.get("status") != "waiting_input":
            return False
        waiting_request_ids = CommandStreamWakeupWorker._waiting_prompt_request_ids(status)
        command_request_id = CommandStreamWakeupWorker._command_request_id(command)
        if not waiting_request_ids or not command_request_id or command_request_id not in waiting_request_ids:
            return False
        return not CommandStreamWakeupWorker._module_identity_mismatch(status, command)

    @staticmethod
    def _has_waiting_request_id_mismatch(status: dict, command: dict) -> bool:
        waiting_request_ids = CommandStreamWakeupWorker._waiting_prompt_request_ids(status)
        command_request_id = CommandStreamWakeupWorker._command_request_id(command)
        if waiting_request_ids and command_request_id and command_request_id not in waiting_request_ids:
            return True
        return False

    @staticmethod
    def _waiting_prompt_request_id(status: dict) -> str:
        request_ids = sorted(CommandStreamWakeupWorker._waiting_prompt_request_ids(status))
        return request_ids[0] if request_ids else ""

    @staticmethod
    def _waiting_prompt_request_ids(status: dict) -> set[str]:
        recovery = status.get("recovery_checkpoint")
        if not isinstance(recovery, dict):
            return set()
        checkpoint = recovery.get("checkpoint")
        if not isinstance(checkpoint, dict):
            return set()
        request_ids: set[str] = set()
        request_id = str(checkpoint.get("waiting_prompt_request_id") or "").strip()
        if request_id:
            request_ids.add(request_id)
        active_prompt = checkpoint.get("runtime_active_prompt")
        if isinstance(active_prompt, dict):
            active_request_id = str(active_prompt.get("request_id") or "").strip()
            if active_request_id:
                request_ids.add(active_request_id)

        batch = checkpoint.get("runtime_active_prompt_batch")
        if not isinstance(batch, dict):
            return request_ids
        prompts_by_player_id = batch.get("prompts_by_player_id")
        if not isinstance(prompts_by_player_id, dict):
            return request_ids

        missing_filter: set[int] | None = None
        missing_player_ids = batch.get("missing_player_ids")
        if isinstance(missing_player_ids, list):
            missing_filter = set()
            for raw_player_id in missing_player_ids:
                try:
                    missing_filter.add(int(raw_player_id))
                except (TypeError, ValueError):
                    continue

        for raw_player_id, prompt in prompts_by_player_id.items():
            if missing_filter is not None:
                try:
                    internal_player_id = int(raw_player_id)
                except (TypeError, ValueError):
                    continue
                if internal_player_id not in missing_filter:
                    continue
            if isinstance(prompt, dict):
                prompt_request_id = str(prompt.get("request_id") or "").strip()
            else:
                prompt_request_id = str(getattr(prompt, "request_id", "") or "").strip()
            if prompt_request_id:
                request_ids.add(prompt_request_id)
        return request_ids

    @staticmethod
    def _command_request_id(command: dict) -> str:
        return CommandStreamWakeupWorker._command_payload_field(command, "request_id")

    @staticmethod
    def _command_payload_field(command: dict, name: str) -> str:
        payload = command.get("payload")
        if not isinstance(payload, dict):
            return ""
        decision = payload.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        return str(payload.get(name) or decision.get(name) or "").strip()

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
            command_value = CommandStreamWakeupWorker._command_payload_field(command, command_field)
            checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
            if command_value and checkpoint_value and command_value != checkpoint_value:
                return True
        return False
