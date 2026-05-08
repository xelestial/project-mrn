from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import os
import random
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.domain.protocol_identity import display_identity_fields
from apps.server.src.domain.protocol_ids import int_or_default, turn_label as protocol_turn_label
from apps.server.src.domain.runtime_semantic_guard import validate_checkpoint_payload
from apps.server.src.domain.session_models import ParticipantClientType, SeatConfig, SeatType, SessionStatus
from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.view_state.projector import project_replay_view_state
from apps.server.src.domain.view_state.prompt_selector import build_prompt_view_state
from apps.server.src.domain.view_state.runtime_selector import ROUND_STAGE_BY_MODULE, TURN_STAGE_BY_MODULE
from apps.server.src.infra.game_debug_log import write_game_debug_log
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import (
    DEFAULT_HUMAN_PROMPT_TIMEOUT_MS,
    DecisionGateway,
    DecisionInvocation,
    PromptFingerprintMismatch,
    PromptRequired,
    build_decision_requested_payload,
    build_decision_invocation,
    build_decision_invocation_from_request,
    build_routed_decision_call,
)
from apps.server.src.services.engine_config_factory import EngineConfigFactory
from apps.server.src.services.parameter_service import DEFAULT_EXTERNAL_AI_TIMEOUT_MS
from apps.server.src.services.realtime_persistence import ViewCommitSequenceConflict

_VIEW_COMMIT_SCHEMA_VERSION = 1
_PROMPT_BOUNDARY_PUBLISH_TIMEOUT_SECONDS = 5.0
_PROMPT_BOUNDARY_PUBLISH_ATTEMPTS = 3


def resolve_runtime_runner_kind(runtime: dict | None, settings: RuntimeSettings | None = None) -> str:
    del runtime, settings
    return "module"


def runtime_checkpoint_schema_version_for_runner(runner_kind: str) -> int:
    del runner_kind
    return 3


@dataclass(frozen=True, slots=True)
class RuntimeDecisionResume:
    request_id: str
    player_id: int
    request_type: str
    choice_id: str
    choice_payload: dict
    resume_token: str
    frame_id: str
    module_id: str
    module_type: str
    module_cursor: str
    batch_id: str = ""


class RuntimeDecisionResumeMismatch(ValueError):
    pass


def _derive_batch_id_from_request_id(request_id: str) -> str:
    request_id = str(request_id or "").strip()
    if not request_id.startswith("batch:") or ":p" not in request_id:
        return ""
    batch_id, player_suffix = request_id.rsplit(":p", 1)
    if not player_suffix.isdigit():
        return ""
    return batch_id


def _derive_internal_player_id_from_batch_request_id(request_id: str) -> int | None:
    request_id = str(request_id or "").strip()
    if not request_id.startswith("batch:") or ":p" not in request_id:
        return None
    _, player_suffix = request_id.rsplit(":p", 1)
    if not player_suffix.isdigit():
        return None
    return int(player_suffix)


def _request_prompt_instance_id(request_id: str, request_type: str) -> int:
    request_type = str(request_type or "").strip()
    request_id = str(request_id or "").strip()
    if not request_type or not request_id:
        return 0
    marker = f":{request_type}:"
    if marker not in request_id:
        return 0
    raw_instance_id = request_id.rsplit(marker, 1)[-1]
    try:
        return max(0, int(raw_instance_id))
    except (TypeError, ValueError):
        return 0


def _prior_same_module_resume_prompt_seed(checkpoint: dict | None, resume: RuntimeDecisionResume | None) -> int | None:
    if not isinstance(checkpoint, dict) or resume is None:
        return None
    previous_request_id = str(checkpoint.get("decision_resume_request_id") or "").strip()
    if not previous_request_id or previous_request_id == str(resume.request_id or "").strip():
        return None
    previous_request_type = str(checkpoint.get("decision_resume_request_type") or "").strip()
    if previous_request_type and previous_request_type != str(resume.request_type or "").strip():
        return None
    previous_player_id = checkpoint.get("decision_resume_player_id")
    if previous_player_id not in (None, ""):
        try:
            if int(previous_player_id) != int(resume.player_id):
                return None
        except (TypeError, ValueError):
            return None
    identity_fields = (
        ("decision_resume_frame_id", "frame_id"),
        ("decision_resume_module_id", "module_id"),
        ("decision_resume_module_type", "module_type"),
        ("decision_resume_module_cursor", "module_cursor"),
    )
    for checkpoint_field, resume_field in identity_fields:
        checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
        resume_value = str(getattr(resume, resume_field, "") or "").strip()
        if checkpoint_value and resume_value and checkpoint_value != resume_value:
            return None
    request_type = previous_request_type or str(resume.request_type or "").strip()
    previous_instance_id = _request_prompt_instance_id(previous_request_id, request_type)
    current_instance_id = _request_prompt_instance_id(str(resume.request_id or ""), str(resume.request_type or ""))
    if previous_instance_id <= 0 or current_instance_id <= previous_instance_id:
        return None
    return max(0, previous_instance_id - 1)


def _normalize_decision_choice_payload(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


_ACTIVE_FLIP_BATCH_NOT_APPLICABLE = object()


def _runtime_module_debug_fields(source: dict | None, state: object | None = None) -> dict[str, str]:
    source = dict(source or {})
    runtime_module = source.get("runtime_module")
    runtime_module = dict(runtime_module) if isinstance(runtime_module, dict) else {}
    active_fields = _active_runtime_module_debug_fields(state)
    candidates = {
        "runner_kind": source.get("runner_kind") or runtime_module.get("runner_kind") or active_fields.get("runner_kind"),
        "module_type": source.get("module_type") or runtime_module.get("module_type") or active_fields.get("module_type"),
        "module_id": source.get("module_id") or runtime_module.get("module_id") or active_fields.get("module_id"),
        "frame_id": source.get("frame_id") or runtime_module.get("frame_id") or active_fields.get("frame_id"),
        "module_cursor": source.get("module_cursor") or runtime_module.get("module_cursor") or active_fields.get("module_cursor"),
        "idempotency_key": source.get("idempotency_key")
        or runtime_module.get("idempotency_key")
        or active_fields.get("idempotency_key"),
    }
    return {key: str(value) for key, value in candidates.items() if value not in (None, "")}


def _runtime_continuation_debug_fields(payload: dict | None, decision_resume: object | None = None) -> dict[str, object]:
    payload = dict(payload or {})
    active_prompt = payload.get("runtime_active_prompt")
    active_prompt = dict(active_prompt) if isinstance(active_prompt, dict) else {}
    active_batch = payload.get("runtime_active_prompt_batch")
    active_batch = dict(active_batch) if isinstance(active_batch, dict) else {}
    candidates: dict[str, object] = {
        "waiting_prompt_request_id": payload.get("pending_prompt_request_id"),
        "waiting_prompt_type": payload.get("pending_prompt_type"),
        "waiting_prompt_player_id": payload.get("pending_prompt_player_id"),
        "waiting_prompt_instance_id": payload.get("pending_prompt_instance_id"),
        "prompt_sequence": payload.get("prompt_sequence"),
        "runtime_active_prompt_request_id": active_prompt.get("request_id"),
        "runtime_active_prompt_request_type": active_prompt.get("request_type"),
        "runtime_active_prompt_player_id": active_prompt.get("player_id"),
        "runtime_active_prompt_frame_id": active_prompt.get("frame_id"),
        "runtime_active_prompt_module_id": active_prompt.get("module_id"),
        "runtime_active_prompt_module_type": active_prompt.get("module_type"),
        "runtime_active_prompt_module_cursor": active_prompt.get("module_cursor"),
        "runtime_active_prompt_batch_id": active_batch.get("batch_id"),
        "runtime_active_prompt_batch_request_type": active_batch.get("request_type"),
        "runtime_active_prompt_batch_frame_id": active_batch.get("frame_id"),
        "runtime_active_prompt_batch_module_id": active_batch.get("module_id"),
        "runtime_active_prompt_batch_module_type": active_batch.get("module_type"),
        "runtime_active_prompt_batch_module_cursor": active_batch.get("module_cursor"),
        "runtime_active_prompt_batch_missing_player_ids": active_batch.get("missing_player_ids"),
    }
    if active_prompt:
        candidates["runtime_active_prompt_resume_token_present"] = bool(active_prompt.get("resume_token"))
    if active_batch:
        candidates["runtime_active_prompt_batch_token_count"] = len(
            active_batch.get("resume_tokens_by_player_id") or {}
        )
    if decision_resume is not None:
        candidates.update(
            {
                "decision_resume_request_id": getattr(decision_resume, "request_id", None),
                "decision_resume_request_type": getattr(decision_resume, "request_type", None),
                "decision_resume_player_id": getattr(decision_resume, "player_id", None),
                "decision_resume_choice_id": getattr(decision_resume, "choice_id", None),
                "decision_resume_frame_id": getattr(decision_resume, "frame_id", None),
                "decision_resume_module_id": getattr(decision_resume, "module_id", None),
                "decision_resume_module_type": getattr(decision_resume, "module_type", None),
                "decision_resume_module_cursor": getattr(decision_resume, "module_cursor", None),
                "decision_resume_batch_id": getattr(decision_resume, "batch_id", None),
                "decision_resume_token_present": bool(getattr(decision_resume, "resume_token", "")),
            }
        )
    return {key: value for key, value in candidates.items() if value not in (None, "")}


def _runtime_failure_diagnostics(
    session_id: str,
    exc: BaseException,
    *,
    status: dict | None = None,
) -> dict[str, object]:
    message = str(exc).strip() or "Runtime execution failed"
    diagnostics: dict[str, object] = {
        "session_id": session_id,
        "error": message,
        "exception_type": exc.__class__.__name__,
        "exception_repr": repr(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
    if isinstance(status, dict):
        last_transition = status.get("last_transition")
        if isinstance(last_transition, dict):
            for key in (
                "latest_seq",
                "latest_source_event_seq",
                "latest_commit_seq",
                "active_frame_id",
                "active_module_id",
                "active_module_type",
                "active_module_cursor",
                "pending_action_count",
                "scheduled_action_count",
                "next_scheduled_action_type",
            ):
                value = last_transition.get(key)
                if value not in (None, ""):
                    diagnostics[key] = value
        recovery = status.get("recovery_checkpoint")
        if isinstance(recovery, dict):
            for key in (
                "latest_seq",
                "latest_source_event_seq",
                "latest_commit_seq",
                "active_frame_id",
                "active_module_id",
                "active_module_type",
                "scheduled_action_count",
                "pending_action_count",
            ):
                value = recovery.get(key)
                if value not in (None, ""):
                    diagnostics.setdefault(key, value)
    return diagnostics


def _stream_backend_of(stream_service: object | None) -> object | None:
    if stream_service is None:
        return None
    return getattr(stream_service, "_stream_backend", None)


def _schedule_runtime_stream_task(
    loop: asyncio.AbstractEventLoop | None,
    session_id: str,
    failure_event: str,
    coroutine_factory,
    **log_fields: object,
) -> None:
    if loop is None:
        return
    coro = None
    try:
        coro = coroutine_factory()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception as exc:
        if inspect.iscoroutine(coro):
            coro.close()
        log_event(
            failure_event,
            session_id=session_id,
            error=str(exc).strip() or exc.__class__.__name__,
            exception_type=exc.__class__.__name__,
            exception_repr=repr(exc),
            **log_fields,
        )
        return

    def _log_stream_task_failure(done_future) -> None:
        try:
            done_future.result()
        except Exception as exc:
            log_event(
                failure_event,
                session_id=session_id,
                error=str(exc).strip() or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
                **log_fields,
            )

    future.add_done_callback(_log_stream_task_failure)


def _run_runtime_stream_task_sync(
    loop: asyncio.AbstractEventLoop | None,
    session_id: str,
    failure_event: str,
    coroutine_factory,
    *,
    timeout: float = 5.0,
    attempts: int = 1,
    retry_delay: float = 0.0,
    **log_fields: object,
) -> bool:
    if loop is None:
        return False
    max_attempts = max(1, int(attempts or 1))
    last_exc: Exception | None = None
    for attempt_index in range(1, max_attempts + 1):
        coro = None
        future: concurrent.futures.Future | None = None
        try:
            coro = coroutine_factory()
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            future.result(timeout=max(0.1, float(timeout)))
            return True
        except Exception as exc:
            last_exc = exc
            if future is not None and isinstance(exc, concurrent.futures.TimeoutError):
                future.cancel()
            if future is None and inspect.iscoroutine(coro):
                coro.close()
            if attempt_index < max_attempts:
                if retry_delay > 0:
                    time.sleep(max(0.0, float(retry_delay)))
                continue
            log_event(
                failure_event,
                session_id=session_id,
                error=str(exc).strip() or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
                attempts=max_attempts,
                **log_fields,
            )
            return False
    if last_exc is not None:
        log_event(
            failure_event,
            session_id=session_id,
            error=str(last_exc).strip() or last_exc.__class__.__name__,
            exception_type=last_exc.__class__.__name__,
            exception_repr=repr(last_exc),
            attempts=max_attempts,
            **log_fields,
        )
    return False


def _clear_resolved_runtime_prompt_continuation(state: object | None, step: dict | None) -> None:
    if state is None:
        return
    status = str((step or {}).get("status") or "").strip()
    if status == "waiting_input":
        return
    if hasattr(state, "runtime_active_prompt"):
        state.runtime_active_prompt = None
    if hasattr(state, "runtime_active_prompt_batch"):
        state.runtime_active_prompt_batch = None


def _active_runtime_module_debug_fields(state: object | None) -> dict[str, str]:
    if state is None:
        return {}
    fields: dict[str, object] = {"runner_kind": getattr(state, "runtime_runner_kind", None)}
    frames = getattr(state, "runtime_frame_stack", None)
    if not isinstance(frames, list):
        return {key: str(value) for key, value in fields.items() if value not in (None, "")}
    for frame in reversed(frames):
        active_module_id = getattr(frame, "active_module_id", None)
        if not active_module_id:
            continue
        fields["frame_id"] = getattr(frame, "frame_id", None)
        fields["module_id"] = active_module_id
        for module in getattr(frame, "module_queue", []) or []:
            if getattr(module, "module_id", None) == active_module_id:
                fields["module_type"] = getattr(module, "module_type", None)
                fields["module_cursor"] = getattr(module, "cursor", None)
                fields["idempotency_key"] = getattr(module, "idempotency_key", None)
                break
        break
    return {key: str(value) for key, value in fields.items() if value not in (None, "")}


def _optional_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _snapshot_pulse_specs_from_source_messages(source_messages: list[dict], *, after_seq: int = 0) -> list[dict[str, int | str | None]]:
    specs: list[dict[str, int | str | None]] = []
    for message in source_messages:
        if str(message.get("type") or "") != "event":
            continue
        seq = _optional_int(message.get("seq")) or 0
        if seq <= int(after_seq or 0):
            continue
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("event_type") or "").strip()
        if event_type == "round_start":
            specs.append({"reason": "round_start_guardrail", "target_player_id": None})
            continue
        if event_type != "turn_start":
            continue
        player_id = _optional_int(payload.get("acting_player_id") or payload.get("player_id"))
        if player_id is None:
            continue
        specs.append({"reason": "turn_start_guardrail", "target_player_id": player_id})
    return specs


class RuntimeService:
    """Background runtime orchestration for mixed-seat (human + AI) sessions."""

    def __init__(
        self,
        session_service,
        stream_service,
        prompt_service=None,
        config_factory: EngineConfigFactory | None = None,
        watchdog_timeout_ms: int = 45000,
        decision_client_factory=None,
        runtime_state_store=None,
        game_state_store=None,
        command_store=None,
    ) -> None:
        self._session_service = session_service
        self._stream_service = stream_service
        self._prompt_service = prompt_service
        self._config_factory = config_factory or EngineConfigFactory()
        self._decision_client_factory = decision_client_factory or _ServerDecisionClientFactory()
        self._runtime_tasks: dict[str, asyncio.Task] = {}
        self._watchdogs: dict[str, asyncio.Task] = {}
        self._status: dict[str, dict] = {}
        self._last_activity_ms: dict[str, int] = {}
        self._fallback_history: dict[str, list[dict]] = {}
        self._watchdog_timeout_ms = int(watchdog_timeout_ms)
        self._session_completed_callbacks: list = []
        self._runtime_state_store = runtime_state_store
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._worker_id = f"runtime_{uuid.uuid4().hex[:12]}"
        self._lease_ttl_ms = max(5000, self._watchdog_timeout_ms * 2)
        self._active_command_sessions: set[str] = set()
        self._command_processing_lock = threading.Lock()
        self._held_runtime_leases: set[str] = set()
        self._runtime_lease_tracking_lock = threading.Lock()
        self._initialize_recovery_state()

    def add_session_completed_callback(self, callback) -> None:
        if callback is None:
            return
        self._session_completed_callbacks.append(callback)

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
        existing = self._runtime_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        recovery = self.recovery_checkpoint(session_id)
        if self.recovery_state_has_waiting_input({"recovery_checkpoint": recovery}):
            self._mark_checkpoint_waiting_input(session_id, reason="checkpoint_waiting_input")
            log_event(
                "runtime_start_deferred_waiting_input_checkpoint",
                session_id=session_id,
                seed=seed,
                policy_mode=policy_mode or "default",
            )
            return
        if not self._acquire_runtime_lease(session_id):
            owner = self._runtime_state_store.lease_owner(session_id) if self._runtime_state_store is not None else None
            self._status[session_id] = {
                "status": "running_elsewhere",
                "reason": "runtime_lease_held",
                "worker_id": self._worker_id,
                "lease_owner": owner,
            }
            self._persist_runtime_state(session_id)
            log_event("runtime_start_skipped_lease_held", session_id=session_id, worker_id=self._worker_id, lease_owner=owner)
            return
        now_ms = self._now_ms()
        self._last_activity_ms[session_id] = now_ms
        runner_kind = self._runner_kind_for_session(session_id)
        self._status[session_id] = {
            "status": "running",
            "watchdog_state": "ok",
            "started_at_ms": now_ms,
            "runner_kind": runner_kind,
            "checkpoint_schema_version": runtime_checkpoint_schema_version_for_runner(runner_kind),
        }
        self._persist_runtime_state(session_id)
        self._runtime_tasks[session_id] = asyncio.create_task(
            self._run_engine_async(session_id=session_id, seed=seed, policy_mode=policy_mode),
            name=f"runtime:{session_id}",
        )
        log_event("runtime_started", session_id=session_id, seed=seed, policy_mode=policy_mode or "default")
        existing_watchdog = self._watchdogs.get(session_id)
        if existing_watchdog is None or existing_watchdog.done():
            self._watchdogs[session_id] = asyncio.create_task(
                self._watchdog_loop(session_id=session_id),
                name=f"runtime_watchdog:{session_id}",
            )

    def stop_runtime(self, session_id: str, reason: str) -> None:
        self._status[session_id] = {"status": "stop_requested", "reason": reason}
        self._persist_runtime_state(session_id)
        log_event("runtime_stop_requested", session_id=session_id, reason=reason)

    def has_unprocessed_runtime_commands(self, session_id: str, consumer_name: str = "runtime_wakeup") -> bool:
        if self._command_store is None:
            return False
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(load_offset) or not callable(list_commands):
            return False
        last_seq = int(load_offset(consumer_name, session_id))
        for command in list_commands(session_id):
            if int(command.get("seq", 0) or 0) > last_seq:
                return True
        return False

    @staticmethod
    def _checkpoint_waiting_prompt_request_ids(checkpoint: dict) -> set[str]:
        request_ids: set[str] = set()
        single_request_id = str(checkpoint.get("waiting_prompt_request_id") or "").strip()
        if single_request_id:
            request_ids.add(single_request_id)

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
                request_id = str(prompt.get("request_id") or "").strip()
            else:
                request_id = str(getattr(prompt, "request_id", "") or "").strip()
            if request_id:
                request_ids.add(request_id)
        return request_ids

    @staticmethod
    def _resume_module_identity_mismatch(checkpoint: dict, resume: RuntimeDecisionResume) -> bool:
        field_pairs = (
            ("frame_id", "active_frame_id"),
            ("module_id", "active_module_id"),
            ("module_type", "active_module_type"),
            ("module_cursor", "active_module_cursor"),
        )
        for resume_field, checkpoint_field in field_pairs:
            resume_value = str(getattr(resume, resume_field, "") or "").strip()
            checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
            if resume_value and checkpoint_value and resume_value != checkpoint_value:
                return True
        return False

    def _checkpoint_still_waits_for_resume(
        self,
        checkpoint: dict,
        decision_resume: RuntimeDecisionResume | None,
    ) -> bool:
        if decision_resume is None:
            return False
        request_id = str(decision_resume.request_id or "").strip()
        if not request_id:
            return False
        if request_id not in self._checkpoint_waiting_prompt_request_ids(checkpoint):
            return False
        return not self._resume_module_identity_mismatch(checkpoint, decision_resume)

    def _command_offset_args_for_commit(
        self,
        *,
        session_id: str,
        checkpoint: dict,
        command_consumer_name: str | None,
        command_seq: int | None,
        decision_resume: RuntimeDecisionResume | None,
    ) -> tuple[str | None, int | None]:
        if not command_consumer_name or command_seq is None:
            return None, None
        if self._checkpoint_still_waits_for_resume(checkpoint, decision_resume):
            log_event(
                "runtime_command_offset_deferred_waiting_prompt",
                session_id=session_id,
                consumer_name=command_consumer_name,
                command_seq=int(command_seq),
                request_id=str(getattr(decision_resume, "request_id", "") or ""),
                player_id=int(getattr(decision_resume, "player_id", 0) or 0),
                module_id=str(getattr(decision_resume, "module_id", "") or ""),
                module_type=str(getattr(decision_resume, "module_type", "") or ""),
                module_cursor=str(getattr(decision_resume, "module_cursor", "") or ""),
            )
            return None, None
        return command_consumer_name, int(command_seq)

    def pending_resume_command(self, session_id: str, consumer_name: str = "runtime_wakeup") -> dict | None:
        if self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        last_consumed_seq = int(load_offset(consumer_name, session_id)) if callable(load_offset) else 0
        recovery = self.recovery_checkpoint(session_id)
        checkpoint = recovery.get("checkpoint") if isinstance(recovery, dict) else None
        if not isinstance(checkpoint, dict):
            return None
        waiting_request_ids = self._checkpoint_waiting_prompt_request_ids(checkpoint)
        if not waiting_request_ids:
            return None
        commands = sorted(list_commands(session_id), key=lambda command: int(command.get("seq", 0) or 0))
        resolved_request_ids = {
            self._command_payload_field(command, "request_id")
            for command in commands
            if str(command.get("type") or "").strip() == "decision_resolved"
        }
        for command in commands:
            if str(command.get("type") or "").strip() != "decision_submitted":
                continue
            if int(command.get("seq", 0) or 0) <= last_consumed_seq:
                continue
            request_id = self._command_payload_field(command, "request_id")
            if request_id not in waiting_request_ids:
                continue
            if request_id in resolved_request_ids and not self._command_is_timeout_fallback(command):
                continue
            if self._command_module_identity_mismatch(checkpoint, command):
                continue
            return dict(command)
        return None

    def _command_for_seq(self, session_id: str, command_seq: int) -> dict | None:
        if self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        target_seq = int(command_seq)
        for command in list_commands(session_id):
            if int(command.get("seq", 0) or 0) == target_seq:
                return dict(command)
        return None

    def _matching_resume_command_for_seq(
        self,
        session_id: str,
        command_seq: int,
        *,
        include_resolved: bool = False,
    ) -> dict | None:
        if self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        recovery = self.recovery_checkpoint(session_id)
        checkpoint = recovery.get("checkpoint") if isinstance(recovery, dict) else None
        if not isinstance(checkpoint, dict):
            return None
        waiting_request_ids = self._checkpoint_waiting_prompt_request_ids(checkpoint)
        if not waiting_request_ids:
            return None
        target_seq = int(command_seq)
        commands = sorted(list_commands(session_id), key=lambda command: int(command.get("seq", 0) or 0))
        resolved_request_ids = {
            self._command_payload_field(command, "request_id")
            for command in commands
            if str(command.get("type") or "").strip() == "decision_resolved"
        }
        for command in commands:
            if int(command.get("seq", 0) or 0) != target_seq:
                continue
            if str(command.get("type") or "").strip() != "decision_submitted":
                return None
            request_id = self._command_payload_field(command, "request_id")
            if request_id not in waiting_request_ids:
                return None
            if not include_resolved and request_id in resolved_request_ids and not self._command_is_timeout_fallback(command):
                return None
            if self._command_module_identity_mismatch(checkpoint, command):
                return None
            return dict(command)
        return None

    def has_pending_resume_command(self, session_id: str, consumer_name: str = "runtime_wakeup") -> bool:
        return self.pending_resume_command(session_id, consumer_name=consumer_name) is not None

    def _load_command_consumer_offset(self, session_id: str, consumer_name: str) -> int | None:
        if self._command_store is None:
            return None
        load_offset = getattr(self._command_store, "load_consumer_offset", None)
        if not callable(load_offset):
            return None
        try:
            return int(load_offset(consumer_name, session_id))
        except Exception as exc:
            log_event(
                "runtime_command_offset_load_failed",
                session_id=session_id,
                consumer_name=consumer_name,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return None

    def _command_processing_guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        if self._command_store is None:
            return None
        target_seq = int(command_seq)
        offset = self._load_command_consumer_offset(session_id, consumer_name)
        if offset is not None and offset >= target_seq:
            matching_waiting_command = self._matching_resume_command_for_seq(session_id, target_seq, include_resolved=True)
            if matching_waiting_command is not None:
                log_event(
                    "runtime_command_offset_conflict_reprocessing",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    request_id=self._command_payload_field(matching_waiting_command, "request_id"),
                )
                return None
            log_event(
                "runtime_command_already_consumed",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                consumer_offset=offset,
                stage=stage,
            )
            return {
                "status": "already_processed",
                "reason": "consumer_offset_already_advanced",
                "processed_command_seq": target_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": offset,
            }
        pending = self.pending_resume_command(session_id, consumer_name=consumer_name)
        target_command = self._command_for_seq(session_id, target_seq)
        target_command_type = str((target_command or {}).get("type") or "").strip()
        if pending is None:
            matching_waiting_command = self._matching_resume_command_for_seq(session_id, target_seq, include_resolved=True)
            if matching_waiting_command is not None:
                log_event(
                    "runtime_command_checkpoint_waiting_reprocessing",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    request_id=self._command_payload_field(matching_waiting_command, "request_id"),
                    request_type=self._command_payload_field(matching_waiting_command, "request_type"),
                    module_id=self._command_payload_field(matching_waiting_command, "module_id"),
                )
                return None
            if target_command is None or target_command_type != "decision_submitted":
                return None
            log_event(
                "runtime_command_no_longer_pending",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                consumer_offset=offset,
                stage=stage,
            )
            self._save_rejected_command_offset(consumer_name, session_id, target_seq)
            return {
                "status": "stale",
                "reason": "command_no_longer_matches_waiting_prompt",
                "processed_command_seq": target_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": target_seq,
            }
        pending_seq = _optional_int(pending.get("seq")) or 0
        if pending_seq != target_seq:
            matching_waiting_command = self._matching_resume_command_for_seq(session_id, target_seq, include_resolved=True)
            if matching_waiting_command is not None:
                log_event(
                    "runtime_command_checkpoint_waiting_reprocessing",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    consumer_offset=offset,
                    stage=stage,
                    request_id=self._command_payload_field(matching_waiting_command, "request_id"),
                    request_type=self._command_payload_field(matching_waiting_command, "request_type"),
                    module_id=self._command_payload_field(matching_waiting_command, "module_id"),
                )
                return None
            if target_command is None or target_command_type != "decision_submitted":
                return None
            if target_seq > pending_seq:
                log_event(
                    "runtime_command_deferred_pending_precedes_target",
                    session_id=session_id,
                    consumer_name=consumer_name,
                    command_seq=target_seq,
                    pending_command_seq=pending_seq,
                    consumer_offset=offset,
                    stage=stage,
                )
                return {
                    "status": "running_elsewhere",
                    "reason": "pending_command_seq_precedes_target",
                    "processed_command_seq": target_seq,
                    "pending_command_seq": pending_seq,
                    "processed_command_consumer": consumer_name,
                    "consumer_offset": offset,
                }
            log_event(
                "runtime_command_pending_changed",
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=target_seq,
                pending_command_seq=pending_seq,
                consumer_offset=offset,
                stage=stage,
            )
            self._save_rejected_command_offset(consumer_name, session_id, target_seq)
            return {
                "status": "stale",
                "reason": "pending_command_seq_changed",
                "processed_command_seq": target_seq,
                "pending_command_seq": pending_seq,
                "processed_command_consumer": consumer_name,
                "consumer_offset": target_seq,
            }
        return None

    def _begin_command_processing(self, session_id: str) -> bool:
        with self._command_processing_lock:
            if session_id in self._active_command_sessions:
                return False
            self._active_command_sessions.add(session_id)
            return True

    def _end_command_processing(self, session_id: str) -> None:
        with self._command_processing_lock:
            self._active_command_sessions.discard(session_id)

    def _runtime_task_processing_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        task = self._runtime_tasks.get(session_id)
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

    def runtime_status(self, session_id: str) -> dict:
        self._refresh_status(session_id)
        task = self._runtime_tasks.get(session_id)
        base = self._load_runtime_state(session_id)
        if task is not None and not task.done():
            base.setdefault("status", "running")
            base["last_activity_ms"] = self._last_activity_ms.get(session_id, base.get("last_activity_ms"))
            base["recent_fallbacks"] = self._recent_fallbacks(session_id)
            return base
        try:
            session = self._session_service.get_session(session_id)
        except Exception:
            session = None
        recovery = self.recovery_checkpoint(session_id)
        checkpoint_waiting_input = self.recovery_state_has_waiting_input({"recovery_checkpoint": recovery})
        if session is not None and session.status == SessionStatus.IN_PROGRESS and checkpoint_waiting_input:
            base = self._mark_checkpoint_waiting_input(session_id, base=base, reason="checkpoint_waiting_input")
        lease_expires_at_ms = int(base.get("lease_expires_at_ms", 0) or 0)
        if session is not None and session.status == SessionStatus.IN_PROGRESS and not checkpoint_waiting_input and (
            base.get("status") in {None, "idle", "running", "stop_requested"} and lease_expires_at_ms <= self._now_ms()
        ):
            base["status"] = "recovery_required"
            base.setdefault("reason", "runtime_task_missing_after_restart")
            self._status[session_id] = dict(base)
            self._persist_runtime_state(session_id)
        base["recent_fallbacks"] = self._recent_fallbacks(session_id)
        if recovery.get("available"):
            base["recovery_checkpoint"] = recovery
        return base

    @staticmethod
    def _payload_has_waiting_prompt(payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        for key in (
            "waiting_prompt_request_id",
            "pending_prompt_request_id",
            "runtime_active_prompt_request_id",
        ):
            if str(payload.get(key) or "").strip():
                return True
        active_prompt = payload.get("runtime_active_prompt")
        if isinstance(active_prompt, dict):
            if str(active_prompt.get("request_id") or "").strip():
                return True
            if active_prompt.get("legal_choices"):
                return True
        active_batch = payload.get("runtime_active_prompt_batch")
        if isinstance(active_batch, dict):
            if str(active_batch.get("batch_id") or "").strip():
                return True
            if active_batch.get("missing_player_ids"):
                return True
            prompts_by_player_id = active_batch.get("prompts_by_player_id")
            if isinstance(prompts_by_player_id, dict) and prompts_by_player_id:
                return True
        return False

    @classmethod
    def recovery_state_has_waiting_input(cls, runtime_state: dict | None) -> bool:
        if not isinstance(runtime_state, dict):
            return False
        recovery = runtime_state.get("recovery_checkpoint")
        if not isinstance(recovery, dict) or not recovery.get("available"):
            return False
        return cls._payload_has_waiting_prompt(recovery.get("checkpoint")) or cls._payload_has_waiting_prompt(
            recovery.get("current_state")
        )

    def _mark_checkpoint_waiting_input(
        self,
        session_id: str,
        *,
        base: dict | None = None,
        reason: str,
    ) -> dict:
        status_payload = {
            key: value
            for key, value in dict(base or self._load_runtime_state(session_id)).items()
            if key != "recovery_checkpoint"
        }
        status_payload["status"] = "waiting_input"
        status_payload["watchdog_state"] = "waiting_input"
        status_payload["reason"] = reason
        self._status[session_id] = dict(status_payload)
        self._persist_runtime_state(session_id)
        return dict(status_payload)

    def public_runtime_status(self, session_id: str) -> dict:
        status = dict(self.runtime_status(session_id))
        recovery = status.get("recovery_checkpoint")
        if isinstance(recovery, dict):
            public_recovery = {
                "available": bool(recovery.get("available")),
                "checkpoint": recovery.get("checkpoint") if isinstance(recovery.get("checkpoint"), dict) else {},
            }
            if isinstance(recovery.get("reason"), str):
                public_recovery["reason"] = recovery["reason"]
            public_recovery["current_state_available"] = isinstance(recovery.get("current_state"), dict)
            status["recovery_checkpoint"] = public_recovery
        return status

    def recovery_checkpoint(self, session_id: str) -> dict:
        if self._game_state_store is None:
            return {"available": False, "reason": "game_state_store_unavailable"}
        checkpoint = self._game_state_store.load_checkpoint(session_id)
        current_state = self._game_state_store.load_current_state(session_id)
        if not isinstance(checkpoint, dict):
            return {"available": False, "reason": "checkpoint_missing"}
        if not isinstance(current_state, dict):
            return {"available": False, "reason": "current_state_missing", "checkpoint": checkpoint}
        return {
            "available": True,
            "checkpoint": checkpoint,
            "current_state": current_state,
        }

    async def execute_prompt_fallback(
        self,
        *,
        session_id: str,
        request_id: str,
        player_id: int,
        fallback_policy: str,
        prompt_payload: dict,
    ) -> dict:
        """Execute timeout fallback seam for future engine-dispatch integration.

        Current baseline records deterministic fallback resolution and keeps runtime activity warm.
        """

        choice_id = self._fallback_choice_id(prompt_payload)
        record = {
            "request_id": request_id,
            "player_id": player_id,
            "fallback_policy": fallback_policy,
            "choice_id": choice_id,
            "executed_at_ms": self._now_ms(),
        }
        self._status.setdefault(session_id, {"status": "idle"})
        self._fallback_history.setdefault(session_id, []).append(record)
        self._touch_activity(session_id)
        if self._runtime_state_store is not None:
            self._runtime_state_store.append_fallback(session_id, record, max_items=20)
        log_event(
            "runtime_fallback_executed",
            session_id=session_id,
            request_id=request_id,
            player_id=player_id,
            fallback_policy=fallback_policy,
            choice_id=choice_id,
        )
        return {"status": "executed", "choice_id": choice_id}

    @staticmethod
    def _fallback_choice_id(prompt_payload: dict) -> str:
        legal_choice_ids: list[str] = []
        legal_choices = prompt_payload.get("legal_choices")
        if isinstance(legal_choices, list):
            for choice in legal_choices:
                if not isinstance(choice, dict):
                    continue
                choice_id = str(choice.get("choice_id") or "").strip()
                if choice_id:
                    legal_choice_ids.append(choice_id)
        if not legal_choice_ids:
            raise ValueError("prompt_fallback_has_no_legal_choice")

        explicit = str(
            prompt_payload.get("fallback_choice_id")
            or prompt_payload.get("default_choice_id")
            or ""
        ).strip()
        if explicit and explicit in legal_choice_ids:
            return explicit
        return legal_choice_ids[0]

    async def process_command_once(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        seed: int = 42,
        policy_mode: str | None = None,
    ) -> dict:
        command_seq = int(command_seq)
        task_guard = self._runtime_task_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage="before_begin",
        )
        if task_guard is not None:
            return task_guard
        if not self._begin_command_processing(session_id):
            return {
                "status": "running_elsewhere",
                "reason": "command_processing_already_active",
                "processed_command_seq": command_seq,
                "processed_command_consumer": consumer_name,
            }
        task_guard = self._runtime_task_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage="after_begin",
        )
        if task_guard is not None:
            self._end_command_processing(session_id)
            return task_guard
        pre_guard = self._command_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage="before_lease",
        )
        if pre_guard is not None:
            self._end_command_processing(session_id)
            return pre_guard
        if not self._acquire_runtime_lease(session_id):
            self._end_command_processing(session_id)
            return {
                "status": "running_elsewhere",
                "lease_owner": self._runtime_state_store.lease_owner(session_id) if self._runtime_state_store is not None else None,
            }
        lease_renewer = self._start_runtime_lease_renewer(
            session_id,
            reason="process_command_once",
            command_seq=command_seq,
            consumer_name=consumer_name,
        )
        try:
            post_guard = self._command_processing_guard(
                session_id=session_id,
                consumer_name=consumer_name,
                command_seq=command_seq,
                stage="after_lease",
            )
            if post_guard is not None:
                return post_guard
            now_ms = self._now_ms()
            self._last_activity_ms[session_id] = now_ms
            self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
            self._persist_runtime_state(session_id)
            loop = asyncio.get_running_loop()
            result = await asyncio.to_thread(
                self._run_engine_transition_loop_sync,
                loop,
                session_id,
                seed,
                policy_mode,
                first_command_consumer_name=consumer_name,
                first_command_seq=command_seq,
            )
            status = str(result.get("status", ""))
            if status == "waiting_input":
                self._status[session_id] = {"status": "waiting_input", "watchdog_state": "waiting_input", "last_transition": result}
            elif status == "completed":
                self._session_service.finish_session(session_id)
                await self._notify_session_completed(session_id)
                self._status[session_id] = {"status": "completed"}
            elif status == "stale":
                persisted_status = self._load_runtime_state(session_id)
                if isinstance(persisted_status, dict) and persisted_status:
                    status_payload = dict(persisted_status)
                    status_payload["last_transition"] = result
                    self._status[session_id] = status_payload
                else:
                    self._status[session_id] = {"status": "idle", "last_transition": result}
            else:
                self._status[session_id] = {"status": "idle", "last_transition": result}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            return result
        except ViewCommitSequenceConflict as exc:
            diagnostics = _runtime_failure_diagnostics(
                session_id,
                exc,
                status=self._status.get(session_id),
            )
            persisted_status = self._load_runtime_state(session_id)
            persisted_status_value = str(persisted_status.get("status") or "")
            recovery = self.recovery_checkpoint(session_id)
            if persisted_status_value in {"waiting_input", "completed"}:
                status_payload = dict(persisted_status)
                status_payload["last_transition"] = {
                    "status": "commit_conflict",
                    "reason": "view_commit_seq_conflict",
                    "processed_command_seq": command_seq,
                    "processed_command_consumer": consumer_name,
                }
                self._status[session_id] = status_payload
                self._persist_runtime_state(session_id)
            else:
                status_payload = {
                    "status": "recovery_required",
                    "watchdog_state": "recovery_required",
                    "reason": "view_commit_seq_conflict_recovered",
                    "exception_type": diagnostics["exception_type"],
                    "exception_repr": diagnostics["exception_repr"],
                    "last_transition": {
                        "status": "commit_conflict",
                        "reason": "view_commit_seq_conflict",
                        "processed_command_seq": command_seq,
                        "processed_command_consumer": consumer_name,
                    },
                }
                if self.recovery_state_has_waiting_input({"recovery_checkpoint": recovery}):
                    self._mark_checkpoint_waiting_input(
                        session_id,
                        base=status_payload,
                        reason="view_commit_seq_conflict_recovered",
                    )
                else:
                    self._status[session_id] = status_payload
                    self._persist_runtime_state(session_id)
            self._touch_activity(session_id)
            log_event(
                "runtime_transition_commit_conflict",
                **diagnostics,
                command_seq=command_seq,
                consumer_name=consumer_name,
            )
            return {
                "status": "commit_conflict",
                "reason": "view_commit_seq_conflict",
                "processed_command_seq": command_seq,
                "processed_command_consumer": consumer_name,
            }
        except Exception as exc:
            diagnostics = _runtime_failure_diagnostics(
                session_id,
                exc,
                status=self._status.get(session_id),
            )
            self._status[session_id] = {
                "status": "failed",
                "error": diagnostics["error"],
                "exception_type": diagnostics["exception_type"],
                "exception_repr": diagnostics["exception_repr"],
            }
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            log_event("runtime_failed", **diagnostics)
            raise
        finally:
            self._stop_runtime_lease_renewer(lease_renewer)
            self._release_runtime_lease(session_id)
            self._end_command_processing(session_id)

    async def _run_engine_async(
        self,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.to_thread(
                self._run_engine_sync,
                loop,
                session_id,
                seed,
                policy_mode,
            )
            if isinstance(result, dict) and result.get("status") == "waiting_input":
                self._status[session_id] = {
                    "status": "waiting_input",
                    "watchdog_state": "waiting_input",
                    "last_transition": result,
                }
                self._touch_activity(session_id)
                self._persist_runtime_state(session_id)
                self._release_runtime_lease(session_id)
                log_event("runtime_waiting_input", session_id=session_id)
                self._clear_runtime_task_if_current(session_id)
                return
            self._session_service.finish_session(session_id)
            await self._notify_session_completed(session_id)
            self._status[session_id] = {"status": "completed"}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            self._release_runtime_lease(session_id)
            log_event("runtime_completed", session_id=session_id)
            self._clear_runtime_task_if_current(session_id)
        except Exception as exc:
            diagnostics = _runtime_failure_diagnostics(
                session_id,
                exc,
                status=self._status.get(session_id),
            )
            self._status[session_id] = {
                "status": "failed",
                "error": diagnostics["error"],
                "exception_type": diagnostics["exception_type"],
                "exception_repr": diagnostics["exception_repr"],
            }
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            self._release_runtime_lease(session_id)
            log_event("runtime_failed", **diagnostics)
            await self._stream_service.publish(
                session_id,
                "error",
                build_error_payload(
                    code="RUNTIME_EXECUTION_FAILED",
                    message=str(diagnostics["error"]),
                    retryable=False,
                ),
            )
            self._clear_runtime_task_if_current(session_id)

    async def _notify_session_completed(self, session_id: str) -> None:
        for callback in list(self._session_completed_callbacks):
            try:
                result = callback(session_id)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                log_event("session_completed_callback_failed", session_id=session_id, error=str(exc))
                await self._stream_service.publish(
                    session_id,
                    "error",
                    build_error_payload(
                        code="SESSION_FINALIZE_CALLBACK_FAILED",
                        message=str(exc),
                        retryable=True,
                    ),
                )
    def _run_engine_sync(
        self,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> dict:
        if self._game_state_store is None:
            raise RuntimeError("module_runtime_requires_game_state_store")
        return self._run_engine_transition_loop_sync(loop, session_id, seed, policy_mode)

    def _run_engine_transition_loop_sync(
        self,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        *,
        max_transitions: int | None = None,
        first_command_consumer_name: str | None = None,
        first_command_seq: int | None = None,
    ) -> dict:
        transitions = 0
        last_step: dict = {"status": "unavailable", "reason": "not_started"}
        checkpoint_command_consumer_name = first_command_consumer_name if first_command_seq is not None else None
        checkpoint_command_seq = int(first_command_seq) if first_command_seq is not None else None
        while max_transitions is None or transitions < max(1, int(max_transitions)):
            command_consumer_name = first_command_consumer_name if transitions == 0 else None
            command_seq = first_command_seq if transitions == 0 else None
            last_step = self._run_engine_transition_once_sync(
                loop,
                session_id,
                seed,
                policy_mode,
                False,
                command_consumer_name,
                command_seq,
                checkpoint_command_consumer_name=checkpoint_command_consumer_name,
                checkpoint_command_seq=checkpoint_command_seq,
            )
            transitions += 1
            status = str(last_step.get("status", ""))
            if status in {"completed", "unavailable", "waiting_input", "rejected", "stale"}:
                return {**last_step, "transitions": transitions}
            if self._prompt_service is not None and self._prompt_service.has_pending_for_session(session_id):
                current = dict(self._status.get(session_id, {"status": "running"}))
                current["status"] = "waiting_input"
                current["watchdog_state"] = "waiting_input"
                self._status[session_id] = current
                self._persist_runtime_state(session_id)
                return {**last_step, "status": "waiting_input", "transitions": transitions}
        return {**last_step, "transitions": transitions}

    async def _watchdog_loop(self, session_id: str) -> None:
        warned = False
        while True:
            task = self._runtime_tasks.get(session_id)
            status = self._status.get(session_id, {}).get("status")
            if task is None:
                return
            if status in {"completed", "failed", "idle"}:
                return
            if task.done():
                self._refresh_status(session_id)
                return
            self._refresh_runtime_lease(session_id)
            last = self._last_activity_ms.get(session_id, self._now_ms())
            idle_ms = self._now_ms() - last
            waiting_human_input = False
            if self._prompt_service is not None:
                try:
                    waiting_human_input = bool(self._prompt_service.has_pending_for_session(session_id))
                except Exception:
                    waiting_human_input = False
            if waiting_human_input:
                warned = False
                current = dict(self._status.get(session_id, {"status": "running"}))
                if current.get("status") == "running":
                    current["watchdog_state"] = "waiting_input"
                    current["last_activity_ms"] = last
                    self._status[session_id] = current
                    self._persist_runtime_state(session_id)
                await asyncio.sleep(2.0)
                continue
            if idle_ms > self._watchdog_timeout_ms and not warned:
                warned = True
                current = dict(self._status.get(session_id, {"status": "running"}))
                current["watchdog_state"] = "stalled_warning"
                current["last_activity_ms"] = last
                self._status[session_id] = current
                self._persist_runtime_state(session_id)
                log_event("runtime_watchdog_warn", session_id=session_id, idle_ms=idle_ms)
                await self._stream_service.publish(
                    session_id,
                    "error",
                    build_error_payload(
                        code="RUNTIME_STALLED_WARN",
                        message=f"Runtime inactivity detected for {idle_ms}ms.",
                        retryable=True,
                    ),
                )
            if idle_ms <= self._watchdog_timeout_ms:
                warned = False
                current = dict(self._status.get(session_id, {"status": "running"}))
                if current.get("status") == "running":
                    current["watchdog_state"] = "ok"
                    current["last_activity_ms"] = last
                    self._status[session_id] = current
                    self._persist_runtime_state(session_id)
            await asyncio.sleep(2.0)

    def _touch_activity(self, session_id: str) -> None:
        self._last_activity_ms[session_id] = self._now_ms()
        self._persist_runtime_state(session_id)

    def _refresh_status(self, session_id: str) -> None:
        task = self._runtime_tasks.get(session_id)
        if not task:
            return
        if not task.done():
            return
        current = self._status.get(session_id, {})
        status = current.get("status")
        if self._game_state_store is not None:
            self._runtime_tasks.pop(session_id, None)
            return
        if status == "running":
            self._status[session_id] = {"status": "completed"}
            self._persist_runtime_state(session_id)
        self._runtime_tasks.pop(session_id, None)

    def _clear_runtime_task_if_current(self, session_id: str) -> None:
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if current_task is not None and self._runtime_tasks.get(session_id) is current_task:
            self._runtime_tasks.pop(session_id, None)

    @staticmethod
    def _now_ms() -> int:
        import time

        return int(time.time() * 1000)

    def _runner_kind_for_session(self, session_id: str) -> str:
        try:
            session = self._session_service.get_session(session_id)
        except Exception:
            return "module"
        resolved = dict(getattr(session, "resolved_parameters", {}) or {})
        return resolve_runtime_runner_kind(dict(resolved.get("runtime", {}) or {}))

    @staticmethod
    def _apply_runner_kind(state, runner_kind: str, checkpoint_schema_version: int) -> None:
        del runner_kind
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = max(
            3,
            int(getattr(state, "runtime_checkpoint_schema_version", 3) or 3),
            int(checkpoint_schema_version or 3),
        )

    @staticmethod
    def _ensure_engine_import_path() -> None:
        root = Path(__file__).resolve().parents[4]
        engine_dir = root / "engine"
        engine_text = str(engine_dir)
        if engine_text in sys.path:
            sys.path.remove(engine_text)
        sys.path.insert(0, engine_text)

    def _initialize_recovery_state(self) -> None:
        try:
            sessions = self._session_service.list_sessions()
        except Exception:
            return
        for session in sessions:
            if session.status != SessionStatus.IN_PROGRESS:
                continue
            payload = {
                "status": "recovery_required",
                "reason": "runtime_task_missing_after_restart",
            }
            self._status.setdefault(session.session_id, payload)
            self._persist_runtime_state(session.session_id)

    def delete_session_data(self, session_id: str) -> None:
        self._status.pop(session_id, None)
        self._last_activity_ms.pop(session_id, None)
        self._fallback_history.pop(session_id, None)
        if self._runtime_state_store is not None:
            self._runtime_state_store.delete_session_data(session_id)

    def _recent_fallbacks(self, session_id: str) -> list[dict]:
        if self._runtime_state_store is not None:
            return list(self._runtime_state_store.recent_fallbacks(session_id, limit=10))
        return list(self._fallback_history.get(session_id, []))[-10:]

    def _load_runtime_state(self, session_id: str) -> dict:
        if self._runtime_state_store is not None:
            payload = self._runtime_state_store.load_status(session_id)
            if payload is not None:
                return dict(payload)
            return {"status": "idle"}
        return dict(self._status.get(session_id, {"status": "idle"}))

    def _persist_runtime_state(self, session_id: str) -> None:
        if self._runtime_state_store is None:
            return
        base = dict(self._status.get(session_id, {}))
        if not base:
            return
        last_activity_ms = self._last_activity_ms.get(session_id)
        if last_activity_ms is not None:
            base["last_activity_ms"] = int(last_activity_ms)
            base["lease_expires_at_ms"] = int(last_activity_ms) + self._lease_ttl_ms
        base.setdefault("worker_id", self._worker_id)
        self._runtime_state_store.save_status(session_id, base)

    @staticmethod
    def _command_payload(command: dict) -> dict:
        payload = command.get("payload")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _command_payload_field(command: dict, name: str) -> str:
        payload = RuntimeService._command_payload(command)
        decision = payload.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        return str(payload.get(name) or decision.get(name) or "").strip()

    @staticmethod
    def _command_is_timeout_fallback(command: dict) -> bool:
        payload = RuntimeService._command_payload(command)
        decision = payload.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        source = str(payload.get("source") or "").strip()
        provider = str(payload.get("provider") or decision.get("provider") or "").strip()
        return source == "timeout_fallback" or provider == "timeout_fallback"

    @staticmethod
    def _command_module_identity_mismatch(checkpoint: dict, command: dict) -> bool:
        field_pairs = (
            ("frame_id", "active_frame_id"),
            ("module_id", "active_module_id"),
            ("module_type", "active_module_type"),
            ("module_cursor", "active_module_cursor"),
        )
        for command_field, checkpoint_field in field_pairs:
            command_value = RuntimeService._command_payload_field(command, command_field)
            checkpoint_value = str(checkpoint.get(checkpoint_field) or "").strip()
            if command_value and checkpoint_value and command_value != checkpoint_value:
                return True
        return False

    def _acquire_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        acquired = bool(self._runtime_state_store.acquire_lease(session_id, self._worker_id, self._lease_ttl_ms))
        if acquired:
            self._track_runtime_lease(session_id)
        return acquired

    def _refresh_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        return bool(self._runtime_state_store.refresh_lease(session_id, self._worker_id, self._lease_ttl_ms))

    def _release_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        try:
            return bool(self._runtime_state_store.release_lease(session_id, self._worker_id))
        finally:
            self._untrack_runtime_lease(session_id)

    def _track_runtime_lease(self, session_id: str) -> None:
        with self._runtime_lease_tracking_lock:
            self._held_runtime_leases.add(session_id)

    def _untrack_runtime_lease(self, session_id: str) -> None:
        with self._runtime_lease_tracking_lock:
            self._held_runtime_leases.discard(session_id)

    def _runtime_lease_held_by_this_process(self, session_id: str) -> bool:
        with self._runtime_lease_tracking_lock:
            return session_id in self._held_runtime_leases

    def _runtime_lease_owner(self, session_id: str) -> str | None:
        if self._runtime_state_store is None:
            return self._worker_id
        owner = getattr(self._runtime_state_store, "lease_owner", None)
        if not callable(owner):
            return None
        return owner(session_id)

    def _runtime_lease_refresh_interval_seconds(self) -> float:
        return min(2.0, max(0.5, self._lease_ttl_ms / 3000.0))

    def _start_runtime_lease_renewer(
        self,
        session_id: str,
        *,
        reason: str,
        command_seq: int | None = None,
        consumer_name: str | None = None,
    ) -> tuple[threading.Event, threading.Thread] | None:
        if self._runtime_state_store is None:
            return None
        stop_event = threading.Event()

        def _renew_loop() -> None:
            interval = self._runtime_lease_refresh_interval_seconds()
            while not stop_event.wait(interval):
                if self._refresh_runtime_lease(session_id):
                    continue
                lease_owner = self._runtime_lease_owner(session_id)
                log_event(
                    "runtime_lease_refresh_failed",
                    session_id=session_id,
                    worker_id=self._worker_id,
                    lease_owner=lease_owner,
                    reason=reason,
                    command_seq=command_seq,
                    consumer_name=consumer_name,
                )
                stop_event.set()
                return

        thread = threading.Thread(
            target=_renew_loop,
            name=f"runtime-lease-renew:{session_id}",
            daemon=True,
        )
        thread.start()
        return stop_event, thread

    @staticmethod
    def _stop_runtime_lease_renewer(handle: tuple[threading.Event, threading.Thread] | None) -> None:
        if handle is None:
            return
        stop_event, thread = handle
        stop_event.set()
        if thread.is_alive():
            thread.join(timeout=1.0)

    def _hydrate_engine_state(self, session_id: str, config, game_state_cls, runner_kind: str | None = None):
        del runner_kind
        if self._game_state_store is None:
            return None
        recovery = self.recovery_checkpoint(session_id)
        if not recovery.get("available"):
            return None
        current_state = recovery.get("current_state")
        if not isinstance(current_state, dict) or "tiles" not in current_state:
            return None
        return game_state_cls.from_checkpoint_payload(config, current_state)

    def _run_engine_transition_once_for_recovery(self, session_id: str, seed: int = 42, policy_mode: str | None = None) -> dict:
        if not self._acquire_runtime_lease(session_id):
            return {
                "status": "running_elsewhere",
                "reason": "runtime_lease_held",
                "lease_owner": self._runtime_lease_owner(session_id),
            }
        lease_renewer = self._start_runtime_lease_renewer(session_id, reason="recovery_transition")
        try:
            return self._run_engine_transition_once_sync(
                None,
                session_id,
                seed,
                policy_mode,
                True,
                None,
                None,
            )
        finally:
            self._stop_runtime_lease_renewer(lease_renewer)
            self._release_runtime_lease(session_id)

    def _decision_resume_from_command(self, session_id: str, command_seq: int | None) -> RuntimeDecisionResume | None:
        if command_seq is None or self._command_store is None:
            return None
        list_commands = getattr(self._command_store, "list_commands", None)
        if not callable(list_commands):
            return None
        target_seq = int(command_seq)
        for command in list_commands(session_id):
            if int(command.get("seq", 0) or 0) != target_seq:
                continue
            if str(command.get("type") or "").strip() != "decision_submitted":
                return None
            payload = command.get("payload")
            if not isinstance(payload, dict):
                return None
            decision = payload.get("decision")
            decision = decision if isinstance(decision, dict) else {}

            def _field(name: str) -> str:
                value = str(payload.get(name) or decision.get(name) or "").strip()
                if name == "batch_id" and not value:
                    value = _derive_batch_id_from_request_id(str(payload.get("request_id") or decision.get("request_id") or ""))
                return value

            choice_payload = payload.get("choice_payload")
            if not isinstance(choice_payload, dict):
                choice_payload = decision.get("choice_payload")
            return RuntimeDecisionResume(
                request_id=_field("request_id"),
                player_id=int(payload.get("player_id") or decision.get("player_id") or 0),
                request_type=_field("request_type"),
                choice_id=_field("choice_id"),
                choice_payload=_normalize_decision_choice_payload(choice_payload),
                resume_token=_field("resume_token"),
                frame_id=_field("frame_id"),
                module_id=_field("module_id"),
                module_type=_field("module_type"),
                module_cursor=_field("module_cursor"),
                batch_id=_field("batch_id"),
            )
        return None

    def _validate_decision_resume_against_checkpoint(self, state, resume: RuntimeDecisionResume) -> None:  # noqa: ANN001
        from runtime_modules.prompts import validate_resume

        internal_player_id = max(0, int(resume.player_id) - 1)
        continuation = getattr(state, "runtime_active_prompt", None)
        batch = getattr(state, "runtime_active_prompt_batch", None)
        if continuation is None and batch is not None:
            if resume.batch_id and str(getattr(batch, "batch_id", "") or "") != resume.batch_id:
                raise ValueError("batch id mismatch")
            prompts = getattr(batch, "prompts_by_player_id", {}) or {}
            continuation = prompts.get(internal_player_id)
        validate_resume(
            continuation,
            request_id=resume.request_id,
            resume_token=resume.resume_token,
            frame_id=resume.frame_id,
            module_id=resume.module_id,
            module_cursor=resume.module_cursor,
            player_id=internal_player_id,
            choice_id=resume.choice_id,
        )
        expected_request_type = str(getattr(continuation, "request_type", "") or "").strip()
        if expected_request_type and resume.request_type and expected_request_type != resume.request_type:
            raise ValueError("request type mismatch")
        expected_module_type = str(getattr(continuation, "module_type", "") or "").strip()
        if expected_module_type and resume.module_type and expected_module_type != resume.module_type:
            raise ValueError("module type mismatch")

    def _save_rejected_command_offset(self, command_consumer_name: str | None, session_id: str, command_seq: int | None) -> None:
        if not command_consumer_name or command_seq is None or self._command_store is None:
            return
        save_offset = getattr(self._command_store, "save_consumer_offset", None)
        if callable(save_offset):
            save_offset(command_consumer_name, session_id, int(command_seq))

    def _run_engine_transition_once_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        require_checkpoint: bool,
        command_consumer_name: str | None,
        command_seq: int | None,
        *,
        checkpoint_command_consumer_name: str | None = None,
        checkpoint_command_seq: int | None = None,
    ) -> dict:
        self._ensure_engine_import_path()
        from engine import GameEngine
        from policy.factory import PolicyFactory
        from state import GameState

        session = self._session_service.get_session(session_id)
        resolved = dict(session.resolved_parameters or {})
        runtime = dict(resolved.get("runtime", {}))
        runner_kind = resolve_runtime_runner_kind(runtime)
        checkpoint_schema_version = runtime_checkpoint_schema_version_for_runner(runner_kind)
        selected_policy_mode = policy_mode or runtime.get("policy_mode") or "heuristic_v3_engine"
        ai_policy = PolicyFactory.create_runtime_policy(policy_mode=selected_policy_mode, lap_policy_mode=selected_policy_mode)
        policy = ai_policy
        base_commit_seq = self._latest_view_commit_seq(session_id)
        human_seats = [
            max(0, int(seat.seat) - 1)
            for seat in session.seats
            if seat.seat_type == SeatType.HUMAN
        ]
        if loop is not None and self._stream_service is not None:
            ai_decision_delay_ms = int(
                runtime.get(
                    "ai_decision_delay_ms",
                    0 if os.environ.get("PYTEST_CURRENT_TEST") else 1000,
                )
                or 0
            )
            policy = _ServerDecisionPolicyBridge(
                session_id=session_id,
                session_seats=session.seats,
                human_seats=human_seats,
                ai_fallback=ai_policy,
                prompt_service=self._prompt_service,
                stream_service=self._stream_service,
                loop=loop,
                touch_activity=self._touch_activity,
                fallback_executor=self.execute_prompt_fallback,
                client_factory=self._decision_client_factory,
                ai_decision_delay_ms=ai_decision_delay_ms,
                blocking_human_prompts=False,
            )
        config = self._config_factory.create(resolved)
        state = self._hydrate_engine_state(session_id, config, GameState, runner_kind)
        decision_resume = None
        runtime_recovery_checkpoint: dict | None = None
        if self._game_state_store is not None and callable(getattr(self._game_state_store, "load_checkpoint", None)):
            loaded_checkpoint = self._game_state_store.load_checkpoint(session_id)
            if isinstance(loaded_checkpoint, dict):
                runtime_recovery_checkpoint = loaded_checkpoint
        if state is None:
            if require_checkpoint:
                return {"status": "unavailable", "reason": "checkpoint_missing"}
        if state is not None:
            self._apply_runner_kind(state, runner_kind, checkpoint_schema_version)
            decision_resume = self._decision_resume_from_command(session_id, command_seq)
            if callable(getattr(policy, "set_prompt_sequence", None)):
                prompt_sequence = int(getattr(state, "prompt_sequence", 0) or 0)
                pending_prompt_instance_id = int(getattr(state, "pending_prompt_instance_id", 0) or 0)
                prior_prompt_seed = _prior_same_module_resume_prompt_seed(runtime_recovery_checkpoint, decision_resume)
                if prior_prompt_seed is not None:
                    prompt_sequence = prior_prompt_seed
                elif pending_prompt_instance_id > 0 and (
                    decision_resume is None
                    or str(getattr(state, "pending_prompt_request_id", "") or "").strip()
                    == str(decision_resume.request_id or "").strip()
                ):
                    prompt_sequence = max(0, pending_prompt_instance_id - 1)
                policy.set_prompt_sequence(prompt_sequence)
            if decision_resume is not None:
                try:
                    self._validate_decision_resume_against_checkpoint(state, decision_resume)
                except ValueError as exc:
                    self._save_rejected_command_offset(command_consumer_name, session_id, command_seq)
                    return {
                        "status": "rejected",
                        "reason": str(exc),
                        "request_id": decision_resume.request_id,
                        "player_id": decision_resume.player_id,
                        "choice_id": decision_resume.choice_id,
                        "processed_command_seq": command_seq,
                        "processed_command_consumer": command_consumer_name,
                        "runner_kind": "module",
                        "module_type": decision_resume.module_type,
                        "module_id": decision_resume.module_id,
                        "frame_id": decision_resume.frame_id,
                        "module_cursor": decision_resume.module_cursor,
                    }
                if callable(getattr(policy, "set_decision_resume", None)):
                    policy.set_decision_resume(decision_resume)
        human_player_ids = [
            int(seat.seat)
            for seat in session.seats
            if seat.seat_type == SeatType.HUMAN
        ]
        event_stream = (
            _FanoutVisEventStream(
                loop,
                self._stream_service,
                session_id,
                self._touch_activity,
                human_player_ids=human_player_ids,
                spectator_event_delay_ms=0,
            )
            if loop is not None and self._stream_service is not None
            else None
        )
        engine = GameEngine(
            config=config,
            policy=policy,
            decision_port=policy if hasattr(policy, "request") else None,
            rng=random.Random(seed),
            event_stream=event_stream,
        )
        engine._vis_session_id_override = session_id
        try:
            prompt_boundary_payload: dict | None = None
            if state is None:
                state = engine.create_initial_state()
                self._apply_runner_kind(state, runner_kind, checkpoint_schema_version)
                state = engine.prepare_run(initial_state=state)
            else:
                state = engine.prepare_run(initial_state=state)
            if decision_resume is None:
                step = engine.run_next_transition(state)
            else:
                step = engine.run_next_transition(state, decision_resume=decision_resume)
        except (RuntimeDecisionResumeMismatch, PromptFingerprintMismatch) as exc:
            self._save_rejected_command_offset(command_consumer_name, session_id, command_seq)
            return {
                "status": "rejected",
                "reason": str(exc),
                "processed_command_seq": command_seq,
                "processed_command_consumer": command_consumer_name,
                "runner_kind": "module",
            }
        except PromptRequired as exc:
            state = state or getattr(engine, "_last_prepared_state", None)
            if state is None:
                raise
            prompt_boundary_payload = dict(exc.prompt)
            prompt_instance_id = int(exc.prompt.get("prompt_instance_id", 0) or 0)
            state.prompt_sequence = max(int(getattr(state, "prompt_sequence", 0) or 0), prompt_instance_id)
            state.pending_prompt_request_id = str(exc.prompt.get("request_id") or "")
            state.pending_prompt_type = str(exc.prompt.get("request_type") or "")
            state.pending_prompt_player_id = int(exc.prompt.get("player_id", 0) or 0)
            state.pending_prompt_instance_id = prompt_instance_id
            step = {
                "status": "waiting_input",
                "reason": "prompt_required",
                "request_id": exc.prompt.get("request_id"),
                "request_type": exc.prompt.get("request_type"),
                "player_id": exc.prompt.get("player_id"),
            }
        else:
            prompt_boundary_payload = None
            state.pending_prompt_request_id = ""
            state.pending_prompt_type = ""
            state.pending_prompt_player_id = 0
            state.pending_prompt_instance_id = 0
            _clear_resolved_runtime_prompt_continuation(state, step)
        current_prompt_sequence = getattr(policy, "current_prompt_sequence", None)
        if state is not None and callable(current_prompt_sequence):
            state.prompt_sequence = max(
                int(getattr(state, "prompt_sequence", 0) or 0),
                int(current_prompt_sequence() or 0),
            )
        effective_runner_kind = str(getattr(state, "runtime_runner_kind", runner_kind) or runner_kind)
        effective_checkpoint_schema_version = int(
            getattr(state, "runtime_checkpoint_schema_version", checkpoint_schema_version) or checkpoint_schema_version
        )
        current_status = dict(self._status.get(session_id, {"status": "running"}))
        current_status["runner_kind"] = effective_runner_kind
        current_status["checkpoint_schema_version"] = effective_checkpoint_schema_version
        self._status[session_id] = current_status
        self._persist_runtime_state(session_id)
        if self._game_state_store is not None:
            payload = state.to_checkpoint_payload()
            validate_checkpoint_payload(payload)
            pending_action_types = [
                str(action.get("type") or "")
                for action in payload.get("pending_actions") or []
                if isinstance(action, dict)
            ]
            scheduled_action_types = [
                str(action.get("type") or "")
                for action in payload.get("scheduled_actions") or []
                if isinstance(action, dict)
            ]
            latest_event_type = "prompt_required" if step.get("status") == "waiting_input" else "engine_transition"
            updated_at_ms = self._now_ms()
            runtime_active_prompt = payload.get("runtime_active_prompt")
            runtime_active_prompt = runtime_active_prompt if isinstance(runtime_active_prompt, dict) else {}
            runtime_active_prompt_batch = payload.get("runtime_active_prompt_batch")
            runtime_active_prompt_batch = runtime_active_prompt_batch if isinstance(runtime_active_prompt_batch, dict) else {}
            prompt_publish_payload: dict | None = None
            if latest_event_type == "prompt_required" and prompt_boundary_payload:
                prompt_publish_payload = self._materialize_prompt_boundary_sync(
                    loop,
                    session_id,
                    prompt_boundary_payload,
                    state=state,
                    publish=False,
                )
            previous_source_event_seq = self._latest_committed_source_event_seq(session_id)
            latest_stream_seq = self._latest_stream_seq_sync(loop, session_id)
            source_messages = self._source_history_sync(loop, session_id, latest_stream_seq)
            snapshot_pulse_specs = _snapshot_pulse_specs_from_source_messages(
                source_messages,
                after_seq=previous_source_event_seq,
            )
            commit_seq = base_commit_seq + 1
            source_event_seq = latest_stream_seq
            module_debug_fields = _runtime_module_debug_fields(
                {
                    **step,
                    "runner_kind": step.get("runner_kind") or effective_runner_kind,
                },
                state,
            )
            continuation_debug_fields = _runtime_continuation_debug_fields(payload, decision_resume)
            processed_command_consumer = command_consumer_name or checkpoint_command_consumer_name
            processed_command_seq = command_seq if command_seq is not None else checkpoint_command_seq
            runtime_checkpoint = {
                "schema_version": effective_checkpoint_schema_version,
                "session_id": session_id,
                "runner_kind": effective_runner_kind,
                "latest_seq": latest_stream_seq,
                "latest_event_type": latest_event_type,
                "base_commit_seq": base_commit_seq,
                "latest_commit_seq": commit_seq,
                "latest_source_event_seq": source_event_seq,
                "has_snapshot": True,
                "has_view_commit": True,
                "round_index": int(payload.get("rounds_completed", 0)) + 1,
                "turn_index": int(payload.get("turn_index", 0)),
                "waiting_prompt_request_id": payload.get("pending_prompt_request_id"),
                "waiting_prompt_type": payload.get("pending_prompt_type"),
                "waiting_prompt_player_id": payload.get("pending_prompt_player_id"),
                "waiting_prompt_instance_id": payload.get("pending_prompt_instance_id"),
                "prompt_sequence": payload.get("prompt_sequence"),
                "runtime_active_prompt": runtime_active_prompt,
                "runtime_active_prompt_batch": runtime_active_prompt_batch,
                "active_frame_id": module_debug_fields.get("frame_id", ""),
                "active_module_id": module_debug_fields.get("module_id", ""),
                "active_module_type": module_debug_fields.get("module_type", ""),
                "active_module_cursor": module_debug_fields.get("module_cursor", ""),
                "pending_action_count": len(payload.get("pending_actions") or []),
                "scheduled_action_count": len(payload.get("scheduled_actions") or []),
                "pending_action_types": pending_action_types,
                "scheduled_action_types": scheduled_action_types,
                "next_action_type": pending_action_types[0] if pending_action_types else "",
                "next_scheduled_action_type": scheduled_action_types[0] if scheduled_action_types else "",
                "has_pending_actions": bool(payload.get("pending_actions")),
                "has_scheduled_actions": bool(payload.get("scheduled_actions")),
                "has_pending_turn_completion": bool(payload.get("pending_turn_completion")),
                "processed_command_seq": processed_command_seq,
                "processed_command_consumer": processed_command_consumer,
                **continuation_debug_fields,
                "updated_at_ms": updated_at_ms,
            }
            offset_consumer_name, offset_command_seq = self._command_offset_args_for_commit(
                session_id=session_id,
                checkpoint=runtime_checkpoint,
                command_consumer_name=command_consumer_name,
                command_seq=command_seq,
                decision_resume=decision_resume,
            )
            command_commit_envelope = {
                "version": 1,
                "atomic_commit": "redis_transition_state_checkpoint_event_offset",
                "consumer": str(processed_command_consumer or ""),
                "seq": processed_command_seq,
                "state": True,
                "checkpoint": True,
                "view_state": True,
                "view_commit": True,
                "runtime_event": True,
                "consumer_offset": bool(offset_consumer_name and offset_command_seq is not None),
                "offset_consumer": str(offset_consumer_name or ""),
                "offset_seq": offset_command_seq,
            }
            runtime_checkpoint["command_commit_envelope"] = command_commit_envelope
            view_commits = self._build_authoritative_view_commits(
                session_id=session_id,
                state=state,
                checkpoint_payload=payload,
                runtime_checkpoint=runtime_checkpoint,
                module_debug_fields=module_debug_fields,
                step=step,
                commit_seq=commit_seq,
                source_event_seq=source_event_seq,
                source_messages=source_messages,
                server_time_ms=updated_at_ms,
            )
            public_view_state = {}
            spectator_commit = view_commits.get("spectator") or view_commits.get("public") or {}
            if isinstance(spectator_commit, dict) and isinstance(spectator_commit.get("view_state"), dict):
                public_view_state = dict(spectator_commit["view_state"])
            latest_commit_seq_before_write = self._latest_view_commit_seq(session_id)
            if latest_commit_seq_before_write != base_commit_seq:
                log_event(
                    "runtime_transition_stale_before_commit",
                    session_id=session_id,
                    base_commit_seq=base_commit_seq,
                    latest_commit_seq=latest_commit_seq_before_write,
                    attempted_commit_seq=commit_seq,
                    processed_command_seq=processed_command_seq,
                    processed_command_consumer=processed_command_consumer,
                    **module_debug_fields,
                    **continuation_debug_fields,
                )
                return {
                    "status": "stale",
                    "reason": "view_commit_seq_changed_before_commit",
                    "base_commit_seq": base_commit_seq,
                    "latest_commit_seq": latest_commit_seq_before_write,
                    "attempted_commit_seq": commit_seq,
                    "processed_command_seq": processed_command_seq,
                    "processed_command_consumer": processed_command_consumer,
                    "runner_kind": effective_runner_kind,
                    **module_debug_fields,
                    **continuation_debug_fields,
                }
            lease_owner_before_write = self._runtime_lease_owner(session_id)
            lease_check_required = self._runtime_state_store is not None and (
                self._runtime_lease_held_by_this_process(session_id)
                or lease_owner_before_write is not None
            )
            if lease_check_required and lease_owner_before_write != self._worker_id:
                log_event(
                    "runtime_transition_lease_lost_before_commit",
                    session_id=session_id,
                    worker_id=self._worker_id,
                    lease_owner=lease_owner_before_write,
                    base_commit_seq=base_commit_seq,
                    attempted_commit_seq=commit_seq,
                    processed_command_seq=processed_command_seq,
                    processed_command_consumer=processed_command_consumer,
                    **module_debug_fields,
                    **continuation_debug_fields,
                )
                return {
                    "status": "stale",
                    "reason": "runtime_lease_lost_before_commit",
                    "lease_owner": lease_owner_before_write,
                    "base_commit_seq": base_commit_seq,
                    "attempted_commit_seq": commit_seq,
                    "processed_command_seq": processed_command_seq,
                    "processed_command_consumer": processed_command_consumer,
                    "runner_kind": effective_runner_kind,
                    **module_debug_fields,
                    **continuation_debug_fields,
                }
            self._game_state_store.commit_transition(
                session_id,
                current_state=payload,
                checkpoint=runtime_checkpoint,
                view_state=public_view_state,
                view_commits=view_commits,
                command_consumer_name=offset_consumer_name,
                command_seq=offset_command_seq,
                runtime_event_payload={
                    "event_type": latest_event_type,
                    "status": step.get("status"),
                    "reason": step.get("reason"),
                    "request_id": step.get("request_id"),
                    "request_type": step.get("request_type"),
                    "player_id": step.get("player_id"),
                    "processed_command_seq": processed_command_seq,
                    "processed_command_consumer": processed_command_consumer,
                    "base_commit_seq": base_commit_seq,
                    "command_commit_envelope": command_commit_envelope,
                    "pending_action_count": len(payload.get("pending_actions") or []),
                    "scheduled_action_count": len(payload.get("scheduled_actions") or []),
                    **module_debug_fields,
                    **continuation_debug_fields,
                },
                runtime_event_server_time_ms=updated_at_ms,
                expected_previous_commit_seq=base_commit_seq,
            )
            self._emit_latest_view_commit_sync(loop, session_id)
            if prompt_publish_payload:
                self._publish_prompt_boundary_sync(loop, session_id, prompt_publish_payload)
            self._emit_snapshot_pulses_sync(loop, session_id, snapshot_pulse_specs)
            write_game_debug_log(
                "engine",
                latest_event_type,
                session_id=session_id,
                round_index=int(payload.get("rounds_completed", 0)) + 1,
                turn_index=int(payload.get("turn_index", 0)),
                status=step.get("status"),
                reason=step.get("reason"),
                request_id=step.get("request_id"),
                request_type=step.get("request_type"),
                player_id=step.get("player_id"),
                base_commit_seq=base_commit_seq,
                commit_seq=commit_seq,
                processed_command_seq=processed_command_seq,
                processed_command_consumer=processed_command_consumer,
                pending_action_count=len(payload.get("pending_actions") or []),
                scheduled_action_count=len(payload.get("scheduled_actions") or []),
                **module_debug_fields,
                **continuation_debug_fields,
            )
        if step.get("status") == "waiting_input":
            self._publish_active_module_prompt_batch_sync(loop, session_id, state)
        return step

    def _emit_latest_view_commit_sync(self, loop: asyncio.AbstractEventLoop | None, session_id: str) -> None:
        if loop is None or self._stream_service is None:
            return
        emit = getattr(self._stream_service, "emit_latest_view_commit", None)
        if not callable(emit):
            return
        if _stream_backend_of(self._stream_service) is not None:
            _schedule_runtime_stream_task(
                loop,
                session_id,
                "runtime_view_commit_emit_failed",
                lambda: emit(session_id),
            )
            return
        _run_runtime_stream_task_sync(
            loop,
            session_id,
            "runtime_view_commit_emit_failed",
            lambda: emit(session_id),
            timeout=1.0,
        )

    def _emit_snapshot_pulses_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        specs: list[dict[str, int | str | None]],
    ) -> None:
        if loop is None or self._stream_service is None or not specs:
            return
        emit = getattr(self._stream_service, "emit_snapshot_pulse", None)
        if not callable(emit):
            return
        fire_and_forget = _stream_backend_of(self._stream_service) is not None
        for spec in specs:
            reason = str(spec.get("reason") or "snapshot_guardrail")
            target_player_id = self._int_or_none(spec.get("target_player_id"))
            if fire_and_forget:
                _schedule_runtime_stream_task(
                    loop,
                    session_id,
                    "runtime_snapshot_pulse_emit_failed",
                    lambda reason=reason, target_player_id=target_player_id: emit(
                        session_id,
                        reason=reason,
                        target_player_id=target_player_id,
                    ),
                    reason=reason,
                    target_player_id=target_player_id,
                )
                continue
            future = asyncio.run_coroutine_threadsafe(
                emit(session_id, reason=reason, target_player_id=target_player_id),
                loop,
            )
            try:
                future.result(timeout=5)
            except Exception as exc:
                log_event(
                    "runtime_snapshot_pulse_emit_failed",
                    session_id=session_id,
                    reason=reason,
                    target_player_id=target_player_id,
                    error=str(exc).strip() or exc.__class__.__name__,
                    exception_type=exc.__class__.__name__,
                    exception_repr=repr(exc),
                )

    def _latest_committed_source_event_seq(self, session_id: str) -> int:
        if self._game_state_store is None:
            return 0
        if callable(getattr(self._game_state_store, "load_view_commit_index", None)):
            index = self._game_state_store.load_view_commit_index(session_id)
            if isinstance(index, dict):
                value = self._int_or_none(index.get("latest_source_event_seq"))
                if value is not None:
                    return value
        if callable(getattr(self._game_state_store, "load_checkpoint", None)):
            checkpoint = self._game_state_store.load_checkpoint(session_id)
            if isinstance(checkpoint, dict):
                value = self._int_or_none(checkpoint.get("latest_source_event_seq") or checkpoint.get("latest_seq"))
                if value is not None:
                    return value
        return 0

    def _latest_stream_seq_sync(self, loop: asyncio.AbstractEventLoop | None, session_id: str) -> int:
        if self._stream_service is None:
            return 0
        backend = _stream_backend_of(self._stream_service)
        latest_seq = getattr(backend, "latest_seq", None)
        if callable(latest_seq):
            try:
                return int(latest_seq(session_id))
            except Exception as exc:
                log_event(
                    "runtime_latest_stream_seq_failed",
                    session_id=session_id,
                    error=str(exc).strip() or exc.__class__.__name__,
                    exception_type=exc.__class__.__name__,
                    exception_repr=repr(exc),
                    source="stream_backend",
                )
                return 0
        if loop is None:
            return 0
        future = asyncio.run_coroutine_threadsafe(self._stream_service.latest_seq(session_id), loop)
        try:
            return int(future.result(timeout=5))
        except Exception as exc:
            log_event(
                "runtime_latest_stream_seq_failed",
                session_id=session_id,
                error=str(exc).strip() or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return 0

    def _source_history_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        through_seq: int | None = None,
    ) -> list[dict]:
        if self._stream_service is None:
            return []
        backend = _stream_backend_of(self._stream_service)
        backend_source_snapshot = getattr(backend, "source_snapshot", None)
        if callable(backend_source_snapshot):
            try:
                result = backend_source_snapshot(session_id, through_seq=through_seq)
            except Exception as exc:
                log_event(
                    "runtime_source_history_failed",
                    session_id=session_id,
                    through_seq=through_seq,
                    error=str(exc).strip() or exc.__class__.__name__,
                    exception_type=exc.__class__.__name__,
                    exception_repr=repr(exc),
                    source="stream_backend",
                )
                return []
            return list(result) if isinstance(result, list) else []
        if loop is None:
            return []
        source_snapshot = getattr(self._stream_service, "source_snapshot", None)
        if not callable(source_snapshot):
            return []
        future = asyncio.run_coroutine_threadsafe(source_snapshot(session_id, through_seq), loop)
        try:
            result = future.result(timeout=5)
        except Exception as exc:
            log_event(
                "runtime_source_history_failed",
                session_id=session_id,
                through_seq=through_seq,
                error=str(exc).strip() or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return []
        return list(result) if isinstance(result, list) else []

    def _latest_view_commit_seq(self, session_id: str) -> int:
        if self._game_state_store is None:
            return 0
        candidates: list[int] = []

        if callable(getattr(self._game_state_store, "load_checkpoint", None)):
            checkpoint = self._game_state_store.load_checkpoint(session_id)
            if isinstance(checkpoint, dict):
                commit_seq = self._int_or_none(checkpoint.get("latest_commit_seq"))
                if commit_seq is not None:
                    candidates.append(commit_seq)

        index: dict | None = None
        if callable(getattr(self._game_state_store, "load_view_commit_index", None)):
            loaded_index = self._game_state_store.load_view_commit_index(session_id)
            if isinstance(loaded_index, dict):
                index = loaded_index
                commit_seq = self._int_or_none(index.get("latest_commit_seq"))
                if commit_seq is not None:
                    candidates.append(commit_seq)

        if callable(getattr(self._game_state_store, "load_view_commit", None)):
            labels = {"spectator", "public", "admin"}
            if isinstance(index, dict):
                raw_labels = index.get("view_commit_viewers")
                if isinstance(raw_labels, list):
                    labels.update(str(label) for label in raw_labels)
            for label in sorted(labels):
                payload = None
                if label.startswith("player:"):
                    player_id = self._int_or_none(label.split(":", 1)[1])
                    if player_id is not None:
                        payload = self._game_state_store.load_view_commit(session_id, "player", player_id=player_id)
                else:
                    payload = self._game_state_store.load_view_commit(session_id, label)
                if isinstance(payload, dict):
                    commit_seq = self._int_or_none(payload.get("commit_seq"))
                    if commit_seq is not None:
                        candidates.append(commit_seq)

        return max([0, *candidates])

    def _next_view_commit_seq(self, session_id: str) -> int:
        return self._latest_view_commit_seq(session_id) + 1

    def _build_authoritative_view_commits(
        self,
        *,
        session_id: str,
        state: object,
        checkpoint_payload: dict,
        runtime_checkpoint: dict,
        module_debug_fields: dict[str, str],
        step: dict,
        commit_seq: int,
        source_event_seq: int,
        source_messages: list[dict],
        server_time_ms: int,
    ) -> dict[str, dict]:
        commits: dict[str, dict] = {}
        public_snapshot = self._public_snapshot_from_state(state)
        parameter_manifest = self._parameter_manifest_for_session(session_id)
        active_module = self._active_runtime_module_from_checkpoint(checkpoint_payload, module_debug_fields)
        round_index = int_or_default(runtime_checkpoint.get("round_index"), 0)
        turn_index = int_or_default(runtime_checkpoint.get("turn_index"), 0)
        commit_turn_label = protocol_turn_label(round_index, turn_index)
        viewer_specs: list[tuple[str, dict]] = [
            ("spectator", {"role": "spectator"}),
            ("public", {"role": "spectator"}),
            ("admin", {"role": "admin"}),
        ]
        for raw_player in checkpoint_payload.get("players") or []:
            if not isinstance(raw_player, dict):
                continue
            internal_player_id = self._int_or_none(raw_player.get("player_id"))
            if internal_player_id is None:
                continue
            external_player_id = internal_player_id + 1
            viewer_specs.append(
                (
                    f"player:{external_player_id}",
                    {
                        "role": "seat",
                        "player_id": external_player_id,
                        "seat": external_player_id,
                        **display_identity_fields(external_player_id, legacy_player_id=external_player_id),
                    },
                )
            )

        for label, viewer in viewer_specs:
            view_state = self._build_authoritative_view_state(
                session_id=session_id,
                state=state,
                checkpoint_payload=checkpoint_payload,
                runtime_checkpoint=runtime_checkpoint,
                public_snapshot=public_snapshot,
                parameter_manifest=parameter_manifest,
                active_module=active_module,
                step=step,
                commit_seq=commit_seq,
                viewer=viewer,
                source_messages=source_messages,
            )
            commits[label] = {
                "schema_version": _VIEW_COMMIT_SCHEMA_VERSION,
                "commit_seq": commit_seq,
                "source_event_seq": source_event_seq,
                "round_index": round_index,
                "turn_index": turn_index,
                "turn_label": commit_turn_label,
                "viewer": dict(viewer),
                "runtime": {
                    "status": self._runtime_status_from_step(step, checkpoint_payload),
                    "round_index": round_index,
                    "turn_index": turn_index,
                    "turn_label": commit_turn_label,
                    "active_frame_id": str(active_module.get("frame_id") or runtime_checkpoint.get("active_frame_id") or ""),
                    "active_module_id": str(active_module.get("module_id") or runtime_checkpoint.get("active_module_id") or ""),
                    "active_module_type": str(
                        active_module.get("module_type") or runtime_checkpoint.get("active_module_type") or ""
                    ),
                    "module_path": list(active_module.get("module_path") or []),
                },
                "view_state": view_state,
                "server_time_ms": server_time_ms,
            }
        return commits

    def _build_authoritative_view_state(
        self,
        *,
        session_id: str,
        state: object,
        checkpoint_payload: dict,
        runtime_checkpoint: dict,
        public_snapshot: dict,
        parameter_manifest: dict,
        active_module: dict,
        step: dict,
        commit_seq: int,
        viewer: dict,
        source_messages: list[dict] | None = None,
    ) -> dict:
        players_view = self._build_players_view_state(public_snapshot, checkpoint_payload)
        board_view = self._build_board_view_state(public_snapshot, checkpoint_payload)
        runtime_view = self._runtime_projection_view_state(runtime_checkpoint, active_module, step, checkpoint_payload)
        weather_view = self._current_weather_view_state(state, public_snapshot, checkpoint_payload)
        game_ended = self._runtime_status_from_step(step, checkpoint_payload) == "completed"
        actor_id = None if game_ended else self._current_actor_player_id(checkpoint_payload)
        turn_stage = {
            "round_index": int(runtime_checkpoint.get("round_index", 0) or 0),
            "turn_index": int(runtime_checkpoint.get("turn_index", 0) or 0),
            "current_actor_player_id": actor_id,
            "ordered_player_ids": list(players_view.get("ordered_player_ids") or []),
            **weather_view,
        }
        if game_ended:
            turn_stage.update(self._game_end_turn_stage_fields(checkpoint_payload))
        situation = {
            "round_index": turn_stage["round_index"],
            "turn_index": turn_stage["turn_index"],
            "roundIndex": turn_stage["round_index"],
            "turnIndex": turn_stage["turn_index"],
            "actor_player_id": actor_id,
            "actorPlayerId": actor_id,
            "active_module_type": runtime_view.get("active_module_type", ""),
            "activeModuleType": runtime_view.get("active_module_type", ""),
            **weather_view,
        }
        if game_ended:
            situation.update(
                {
                    "headline_event_code": "game_end",
                    "headlineEventCode": "game_end",
                    "headline_message_type": "event",
                    "headlineMessageType": "event",
                }
            )
        view_state: dict[str, object] = {
            "schema_version": _VIEW_COMMIT_SCHEMA_VERSION,
            "commit_seq": commit_seq,
            "board": board_view,
            "players": players_view,
            "player_cards": self._build_player_cards_view_state(public_snapshot, checkpoint_payload),
            "active_slots": self._build_active_slots_view_state(public_snapshot, checkpoint_payload),
            "active_by_card": dict(public_snapshot.get("active_by_card") or checkpoint_payload.get("active_by_card") or {}),
            "turn_stage": turn_stage,
            "scene": {"situation": situation},
            "runtime": runtime_view,
            "parameter_manifest": parameter_manifest,
        }
        prompt_view = self._build_prompt_view_state_for_viewer(
            checkpoint_payload=checkpoint_payload,
            viewer=viewer,
            active_module=active_module,
            commit_seq=commit_seq,
        )
        if prompt_view:
            view_state["prompt"] = prompt_view
        hand_tray = self._build_hand_tray_view_state(state, viewer)
        if hand_tray:
            view_state["hand_tray"] = {"items": hand_tray}
        replay_view_state = self._source_projection_view_state(session_id, list(source_messages or []), viewer)
        replay_scene = replay_view_state.get("scene")
        if isinstance(replay_scene, dict):
            merged_scene = dict(replay_scene)
            replay_situation = merged_scene.get("situation")
            merged_scene["situation"] = {
                **situation,
                **(replay_situation if isinstance(replay_situation, dict) else {}),
            }
            view_state["scene"] = merged_scene
        turn_history = replay_view_state.get("turn_history")
        if isinstance(turn_history, dict):
            view_state["turn_history"] = turn_history
        return view_state

    def _source_projection_view_state(self, session_id: str, source_messages: list[dict], viewer: dict) -> dict:
        if not source_messages:
            return {}
        role = str(viewer.get("role") or "spectator")
        return dict(
            project_replay_view_state(
                source_messages,
                ViewerContext(
                    role=role,
                    session_id=session_id,
                    player_id=self._int_or_none(viewer.get("player_id")),
                    seat=self._int_or_none(viewer.get("seat")),
                ),
            )
        )

    @staticmethod
    def _game_end_turn_stage_fields(checkpoint_payload: dict) -> dict[str, object]:
        winner_ids = []
        for raw_winner_id in checkpoint_payload.get("winner_ids") or []:
            try:
                winner_ids.append(int(raw_winner_id) + 1)
            except (TypeError, ValueError):
                continue
        reason = str(checkpoint_payload.get("end_reason") or "").strip()
        winners = ", ".join(f"P{player_id}" for player_id in winner_ids)
        detail = " / ".join(item for item in [f"Winner {winners}" if winners else "", reason] if item)
        return {
            "current_beat_kind": "system",
            "current_beat_event_code": "game_end",
            "current_beat_request_type": "-",
            "current_beat_label": "",
            "current_beat_detail": detail,
            "current_beat_seq": None,
            "prompt_request_type": "-",
            "prompt_summary": "-",
            "progress_codes": ["game_end"],
        }

    @staticmethod
    def _current_weather_view_state(state: object, public_snapshot: dict, checkpoint_payload: dict) -> dict[str, str]:
        weather = getattr(state, "current_weather", None)
        name = str(getattr(weather, "name", "") or "")
        effect = str(getattr(weather, "effect", "") or "")

        snapshot_weather = public_snapshot.get("current_weather") or public_snapshot.get("weather")
        if isinstance(snapshot_weather, dict):
            name = name or str(snapshot_weather.get("name") or snapshot_weather.get("weather_name") or "")
            effect = effect or str(snapshot_weather.get("effect") or snapshot_weather.get("weather_effect") or "")

        checkpoint_weather = checkpoint_payload.get("current_weather") or checkpoint_payload.get("weather")
        if isinstance(checkpoint_weather, dict):
            name = name or str(checkpoint_weather.get("name") or checkpoint_weather.get("weather_name") or "")
            effect = effect or str(checkpoint_weather.get("effect") or checkpoint_weather.get("weather_effect") or "")

        if not effect:
            effects = checkpoint_payload.get("current_weather_effects")
            if isinstance(effects, list):
                effect = " / ".join(str(item) for item in effects if str(item).strip())

        if not name.strip():
            return {}
        return {
            "weather_name": name,
            "weather_effect": effect if effect.strip() else "-",
        }

    @staticmethod
    def _public_snapshot_from_state(state: object) -> dict:
        try:
            from viewer.public_state import build_turn_end_snapshot

            snapshot = build_turn_end_snapshot(state)
            return dict(snapshot) if isinstance(snapshot, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _build_board_view_state(public_snapshot: dict, checkpoint_payload: dict) -> dict:
        board = dict(public_snapshot.get("board") or {})
        board.setdefault("tiles", [])
        board.setdefault("f_value", checkpoint_payload.get("f_value", 0))
        board.setdefault("marker_owner_player_id", int(checkpoint_payload.get("marker_owner_id", 0) or 0) + 1)
        board.setdefault("round_index", int(checkpoint_payload.get("rounds_completed", 0) or 0) + 1)
        board.setdefault("turn_index", int(checkpoint_payload.get("turn_index", 0) or 0) + 1)
        board["marker_draft_direction"] = (
            "clockwise" if bool(checkpoint_payload.get("marker_draft_clockwise", True)) else "counterclockwise"
        )
        board["weather_effects"] = list(checkpoint_payload.get("current_weather_effects") or [])
        board["next_supply_f_threshold"] = int(checkpoint_payload.get("next_supply_f_threshold", 0) or 0)
        board["winner_ids"] = [int(item) + 1 for item in checkpoint_payload.get("winner_ids") or []]
        board["end_reason"] = str(checkpoint_payload.get("end_reason") or "")
        return board

    def _build_players_view_state(self, public_snapshot: dict, checkpoint_payload: dict) -> dict:
        snapshot_players = public_snapshot.get("players")
        public_players = list(snapshot_players) if isinstance(snapshot_players, list) else []
        payload_players = [item for item in checkpoint_payload.get("players") or [] if isinstance(item, dict)]
        payload_by_external = {
            int(player.get("player_id", -1)) + 1: player
            for player in payload_players
            if self._int_or_none(player.get("player_id")) is not None
        }
        ordered = [int(item) + 1 for item in checkpoint_payload.get("current_round_order") or []]
        current_actor = self._current_actor_player_id(checkpoint_payload)
        active_by_card = dict(public_snapshot.get("active_by_card") or checkpoint_payload.get("active_by_card") or {})
        character_to_slot = {str(character): self._int_or_none(slot) for slot, character in active_by_card.items()}
        items: list[dict] = []
        for public_player in public_players:
            if not isinstance(public_player, dict):
                continue
            player_id = self._int_or_none(public_player.get("player_id"))
            if player_id is None:
                continue
            payload_player = payload_by_external.get(player_id, {})
            current_character = str(public_player.get("character") or payload_player.get("current_character") or "")
            hand_coins = int(public_player.get("hand_score_coins", payload_player.get("hand_coins", 0)) or 0)
            placed_coins = int(public_player.get("placed_score_coins", payload_player.get("score_coins_placed", 0)) or 0)
            score = int(public_player.get("score", 0) or 0)
            if score <= 0:
                score = int(public_player.get("owned_tile_count", payload_player.get("tiles_owned", 0)) or 0) + placed_coins
            item = {
                **public_player,
                "player_id": player_id,
                "seat": self._int_or_none(public_player.get("seat")) or player_id,
                "current_character_face": current_character,
                "character": current_character,
                "hand_coins": hand_coins,
                "placed_coins": placed_coins,
                "placed_score_coins": placed_coins,
                "score": score,
                "total_score": score,
                "is_marker_owner": player_id == int(checkpoint_payload.get("marker_owner_id", 0) or 0) + 1,
                "is_current_actor": player_id == current_actor,
                "turn_order_rank": ordered.index(player_id) if player_id in ordered else None,
                "priority_slot": character_to_slot.get(current_character),
            }
            items.append(item)
        if not ordered:
            ordered = [int(item.get("player_id", 0)) for item in items if self._int_or_none(item.get("player_id"))]
        return {
            "items": items,
            "ordered_player_ids": ordered,
            "turn_order_source": "round_order" if ordered else "player_id",
            "marker_owner_player_id": int(checkpoint_payload.get("marker_owner_id", 0) or 0) + 1,
            "marker_draft_direction": (
                "clockwise" if bool(checkpoint_payload.get("marker_draft_clockwise", True)) else "counterclockwise"
            ),
        }

    def _build_player_cards_view_state(self, public_snapshot: dict, checkpoint_payload: dict) -> dict:
        del checkpoint_payload
        players = public_snapshot.get("players")
        if not isinstance(players, list):
            return {"items": []}
        active_by_card = dict(public_snapshot.get("active_by_card") or {})
        character_to_slot = {str(character): self._int_or_none(slot) for slot, character in active_by_card.items()}
        items: list[dict] = []
        for raw_player in players:
            if not isinstance(raw_player, dict):
                continue
            player_id = self._int_or_none(raw_player.get("player_id"))
            character = str(raw_player.get("character") or "")
            if player_id is None or not character:
                continue
            items.append(
                {
                    "player_id": player_id,
                    "seat": self._int_or_none(raw_player.get("seat")) or player_id,
                    "character": character,
                    "current_character_face": character,
                    "priority_slot": character_to_slot.get(character),
                    "reveal_state": "revealed",
                }
            )
        return {"items": items}

    def _build_active_slots_view_state(self, public_snapshot: dict, checkpoint_payload: dict) -> dict:
        del checkpoint_payload
        active_by_card = dict(public_snapshot.get("active_by_card") or {})
        items = []
        for slot, character in sorted(active_by_card.items(), key=lambda item: str(item[0])):
            items.append(
                {
                    "priority_slot": self._int_or_none(slot),
                    "character": str(character),
                    "card_name": str(character),
                    "occupied": bool(str(character)),
                }
            )
        return {"items": items}

    def _build_hand_tray_view_state(self, state: object, viewer: dict) -> list[dict]:
        player_id = self._int_or_none(viewer.get("player_id"))
        if player_id is None:
            return []
        players = getattr(state, "players", None)
        if not isinstance(players, list):
            return []
        internal_id = player_id - 1
        if internal_id < 0 or internal_id >= len(players):
            return []
        hand = getattr(players[internal_id], "trick_hand", None)
        if not isinstance(hand, list):
            return []
        items = []
        for index, card in enumerate(hand):
            deck_index = self._int_or_none(getattr(card, "deck_index", None))
            name = str(getattr(card, "name", "") or "")
            effect = str(
                getattr(card, "description", "")
                or getattr(card, "effect", "")
                or getattr(card, "text", "")
                or ""
            )
            items.append(
                {
                    "key": f"{deck_index if deck_index is not None else index}:{name}:{index}",
                    "deck_index": deck_index,
                    "title": name,
                    "name": name,
                    "effect": effect,
                    "description": effect,
                    "serial": str(deck_index) if deck_index is not None else "",
                    "hidden": False,
                    "is_hidden": False,
                    "currentTarget": False,
                    "is_current_target": False,
                }
            )
        return items

    def _build_prompt_view_state_for_viewer(
        self,
        *,
        checkpoint_payload: dict,
        viewer: dict,
        active_module: dict,
        commit_seq: int,
    ) -> dict | None:
        player_id = self._int_or_none(viewer.get("player_id"))
        if str(viewer.get("role") or "") not in {"seat", "player"} or player_id is None:
            return None
        prompt_payload = self._active_prompt_payload_for_player(checkpoint_payload, player_id, active_module)
        if not prompt_payload:
            return None
        prompt_view = build_prompt_view_state([{"type": "prompt", "payload": prompt_payload}])
        if not isinstance(prompt_view, dict):
            return None
        active = prompt_view.get("active")
        if isinstance(active, dict):
            active["commit_seq"] = commit_seq
            active["view_commit_seq"] = commit_seq
            active["prompt_commit_seq"] = commit_seq
            active["prompt_instance_id"] = prompt_payload.get("prompt_instance_id")
            active["legal_choices"] = list(prompt_payload.get("legal_choices") or [])
        return prompt_view

    def _active_prompt_payload_for_player(self, checkpoint_payload: dict, player_id: int, active_module: dict) -> dict | None:
        active_prompt = checkpoint_payload.get("runtime_active_prompt")
        if isinstance(active_prompt, dict):
            prompt_player_id = self._external_prompt_player_id(active_prompt, checkpoint_payload)
            if prompt_player_id == player_id:
                return self._single_prompt_payload(active_prompt, checkpoint_payload, active_module, player_id=player_id)
        active_batch = checkpoint_payload.get("runtime_active_prompt_batch")
        if isinstance(active_batch, dict):
            return self._batch_prompt_payload_for_player(active_batch, checkpoint_payload, active_module, player_id)
        return None

    def _single_prompt_payload(
        self,
        prompt: dict,
        checkpoint_payload: dict,
        active_module: dict,
        *,
        player_id: int,
    ) -> dict:
        payload = dict(prompt)
        payload["player_id"] = player_id
        payload.setdefault("request_id", checkpoint_payload.get("pending_prompt_request_id"))
        payload.setdefault("request_type", checkpoint_payload.get("pending_prompt_type"))
        payload.setdefault("prompt_instance_id", checkpoint_payload.get("pending_prompt_instance_id"))
        payload.setdefault("timeout_ms", DEFAULT_HUMAN_PROMPT_TIMEOUT_MS)
        payload.setdefault("provider", "human")
        payload.setdefault("legal_choices", [])
        payload.setdefault("public_context", {})
        payload["runtime_module"] = self._runtime_module_prompt_payload(active_module)
        return payload

    def _batch_prompt_payload_for_player(
        self,
        batch: dict,
        checkpoint_payload: dict,
        active_module: dict,
        player_id: int,
    ) -> dict | None:
        prompts = batch.get("prompts_by_player_id")
        if not isinstance(prompts, dict):
            return None
        internal_player_id = player_id - 1
        raw_prompt = prompts.get(str(internal_player_id)) or prompts.get(internal_player_id)
        if not isinstance(raw_prompt, dict):
            return None
        prompt = dict(raw_prompt)
        prompt["player_id"] = player_id
        prompt.setdefault("request_id", checkpoint_payload.get("pending_prompt_request_id") or prompt.get("request_id"))
        prompt.setdefault("request_type", batch.get("request_type"))
        prompt.setdefault("timeout_ms", DEFAULT_HUMAN_PROMPT_TIMEOUT_MS)
        prompt.setdefault("provider", "human")
        prompt.setdefault("legal_choices", [])
        prompt.setdefault("public_context", {})
        prompt.setdefault("runner_kind", active_module.get("runner_kind") or "module")
        prompt.setdefault("frame_id", active_module.get("frame_id"))
        prompt.setdefault("module_id", active_module.get("module_id"))
        prompt.setdefault("module_type", active_module.get("module_type"))
        prompt.setdefault("module_cursor", active_module.get("module_cursor"))
        prompt["batch_id"] = str(batch.get("batch_id") or "")
        prompt["missing_player_ids"] = [
            int(raw) + 1
            for raw in batch.get("missing_player_ids") or []
            if self._int_or_none(raw) is not None
        ]
        resume_tokens = batch.get("resume_tokens_by_player_id")
        if isinstance(resume_tokens, dict):
            prompt["resume_tokens_by_player_id"] = {
                str(int(raw_id) + 1): str(token)
                for raw_id, token in resume_tokens.items()
                if self._int_or_none(raw_id) is not None
            }
        prompt["runtime_module"] = self._runtime_module_prompt_payload(active_module)
        return prompt

    def _external_prompt_player_id(self, prompt: dict, checkpoint_payload: dict) -> int | None:
        raw_player_id = self._int_or_none(prompt.get("player_id"))
        pending_player_id = self._int_or_none(checkpoint_payload.get("pending_prompt_player_id"))
        player_count = len([item for item in checkpoint_payload.get("players") or [] if isinstance(item, dict)])
        if raw_player_id is None:
            return pending_player_id
        if pending_player_id is not None and raw_player_id == pending_player_id:
            return raw_player_id
        if pending_player_id is not None and raw_player_id + 1 == pending_player_id:
            return pending_player_id
        if 0 <= raw_player_id < player_count:
            return raw_player_id + 1
        return raw_player_id

    @staticmethod
    def _runtime_module_prompt_payload(active_module: dict) -> dict:
        return {
            "runner_kind": str(active_module.get("runner_kind") or ""),
            "frame_id": str(active_module.get("frame_id") or ""),
            "frame_type": str(active_module.get("frame_type") or ""),
            "module_id": str(active_module.get("module_id") or ""),
            "module_type": str(active_module.get("module_type") or ""),
            "module_cursor": str(active_module.get("module_cursor") or ""),
            "module_path": list(active_module.get("module_path") or []),
            "idempotency_key": str(active_module.get("idempotency_key") or ""),
        }

    def _active_runtime_module_from_checkpoint(self, checkpoint_payload: dict, module_debug_fields: dict[str, str]) -> dict:
        frame_stack = checkpoint_payload.get("runtime_frame_stack")
        if isinstance(frame_stack, list):
            for frame_index in range(len(frame_stack) - 1, -1, -1):
                frame = frame_stack[frame_index]
                if not isinstance(frame, dict) or str(frame.get("status") or "") == "completed":
                    continue
                module = self._active_module_from_frame_payload(frame)
                if module is None:
                    continue
                frame_id = str(frame.get("frame_id") or "")
                module_id = str(module.get("module_id") or "")
                path = [
                    str(raw_frame.get("frame_id") or raw_frame.get("frame_type") or "")
                    for raw_frame in frame_stack[: frame_index + 1]
                    if isinstance(raw_frame, dict)
                ]
                if module_id:
                    path.append(module_id)
                return {
                    "runner_kind": str(checkpoint_payload.get("runtime_runner_kind") or "module"),
                    "frame_id": frame_id,
                    "frame_type": str(frame.get("frame_type") or ""),
                    "module_id": module_id,
                    "module_type": str(module.get("module_type") or ""),
                    "module_status": str(module.get("status") or ""),
                    "module_cursor": str(module.get("module_cursor") or ""),
                    "idempotency_key": str(module.get("idempotency_key") or ""),
                    "module_path": [item for item in path if item],
                }
        return {
            "runner_kind": str(module_debug_fields.get("runner_kind") or checkpoint_payload.get("runtime_runner_kind") or "module"),
            "frame_id": str(module_debug_fields.get("frame_id") or ""),
            "frame_type": "",
            "module_id": str(module_debug_fields.get("module_id") or ""),
            "module_type": str(module_debug_fields.get("module_type") or ""),
            "module_status": "",
            "module_cursor": str(module_debug_fields.get("module_cursor") or ""),
            "idempotency_key": str(module_debug_fields.get("idempotency_key") or ""),
            "module_path": [
                item
                for item in [
                    str(module_debug_fields.get("frame_id") or ""),
                    str(module_debug_fields.get("module_id") or ""),
                ]
                if item
            ],
        }

    @staticmethod
    def _active_module_from_frame_payload(frame: dict) -> dict | None:
        queue = frame.get("module_queue")
        if not isinstance(queue, list):
            return None
        active_module_id = str(frame.get("active_module_id") or "")
        if active_module_id:
            for module in queue:
                if (
                    isinstance(module, dict)
                    and str(module.get("module_id") or "") == active_module_id
                    and str(module.get("status") or "") in {"running", "suspended"}
                ):
                    return module
        for module in queue:
            if not isinstance(module, dict):
                continue
            if str(module.get("status") or "") in {"running", "suspended"}:
                return module
        return None

    def _runtime_projection_view_state(
        self,
        runtime_checkpoint: dict,
        active_module: dict,
        step: dict,
        checkpoint_payload: dict,
    ) -> dict:
        module_type = str(active_module.get("module_type") or runtime_checkpoint.get("active_module_type") or "")
        module_path = [str(item) for item in active_module.get("module_path") or [] if str(item)]
        active_sequence = self._active_sequence_from_path(module_path, module_type)
        round_stage = ROUND_STAGE_BY_MODULE.get(module_type, "in_round" if module_type else "")
        turn_stage = TURN_STAGE_BY_MODULE.get(module_type, "" if round_stage in {"round_setup", "draft", "turn_scheduler"} else "in_turn")
        return {
            "runner_kind": str(active_module.get("runner_kind") or runtime_checkpoint.get("runner_kind") or "module"),
            "latest_module_path": module_path,
            "module_path": module_path,
            "round_stage": round_stage,
            "turn_stage": turn_stage,
            "active_sequence": active_sequence,
            "active_prompt_request_id": str(
                runtime_checkpoint.get("waiting_prompt_request_id") or step.get("request_id") or ""
            ),
            "active_frame_id": str(active_module.get("frame_id") or runtime_checkpoint.get("active_frame_id") or ""),
            "active_frame_type": str(active_module.get("frame_type") or ""),
            "active_module_id": str(active_module.get("module_id") or runtime_checkpoint.get("active_module_id") or ""),
            "active_module_type": module_type,
            "active_module_status": str(active_module.get("module_status") or ""),
            "active_module_cursor": str(active_module.get("module_cursor") or runtime_checkpoint.get("active_module_cursor") or ""),
            "active_module_idempotency_key": str(active_module.get("idempotency_key") or ""),
            "draft_active": module_type == "DraftModule"
            or str(runtime_checkpoint.get("waiting_prompt_type") or "") in {"draft_card", "final_character", "final_character_choice"},
            "trick_sequence_active": active_sequence == "trick" or module_type.startswith("Trick"),
            "card_flip_legal": module_type == "RoundEndCardFlipModule",
            "status": self._runtime_status_from_step(step, checkpoint_payload),
        }

    @staticmethod
    def _runtime_status_from_step(step: dict, checkpoint_payload: dict) -> str:
        status = str(step.get("status") or "")
        if status == "waiting_input":
            return "waiting_input"
        if status in {"completed", "game_over"} or checkpoint_payload.get("winner_ids") or checkpoint_payload.get("end_reason"):
            return "completed"
        return "running"

    @staticmethod
    def _active_sequence_from_path(module_path: list[str], module_type: str) -> str:
        if any(item.startswith("seq:trick") for item in module_path) or module_type.startswith("Trick"):
            return "trick"
        if any(item.startswith("seq:fortune") for item in module_path) or module_type.startswith("Fortune"):
            return "fortune"
        return ""

    @staticmethod
    def _current_actor_player_id(checkpoint_payload: dict) -> int | None:
        frame_actor = RuntimeService._active_turn_frame_actor_player_id(checkpoint_payload)
        if frame_actor is not None:
            return frame_actor
        ordered = checkpoint_payload.get("current_round_order")
        turn_index = int(checkpoint_payload.get("turn_index", 0) or 0)
        if isinstance(ordered, list) and ordered:
            raw_actor = ordered[min(turn_index, len(ordered) - 1)]
            try:
                return int(raw_actor) + 1
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _active_turn_frame_actor_player_id(checkpoint_payload: dict) -> int | None:
        frames = checkpoint_payload.get("runtime_frame_stack")
        if not isinstance(frames, list):
            runtime_state = checkpoint_payload.get("runtime_state")
            if isinstance(runtime_state, dict):
                frames = runtime_state.get("frame_stack")
        if not isinstance(frames, list):
            return None
        for frame in reversed(frames):
            if not isinstance(frame, dict):
                continue
            if str(frame.get("frame_type") or "") != "turn":
                continue
            if str(frame.get("status") or "") in {"completed", "skipped", "failed"}:
                continue
            owner = RuntimeService._int_or_none(frame.get("owner_player_id"))
            if owner is not None:
                return owner + 1
            frame_id = str(frame.get("frame_id") or "")
            if ":p" in frame_id:
                suffix = frame_id.rsplit(":p", 1)[1]
                if suffix.isdigit():
                    return int(suffix) + 1
        return None

    def _parameter_manifest_for_session(self, session_id: str) -> dict:
        get_session = getattr(self._session_service, "get_session", None)
        if not callable(get_session):
            return {}
        try:
            session = get_session(session_id)
        except Exception:
            return {}
        for attr in ("parameter_manifest", "resolved_parameter_manifest", "manifest"):
            value = getattr(session, attr, None)
            if isinstance(value, dict):
                return dict(value)
        resolved_parameters = getattr(session, "resolved_parameters", None)
        if isinstance(resolved_parameters, dict):
            for key in ("parameter_manifest", "manifest"):
                value = resolved_parameters.get(key)
                if isinstance(value, dict):
                    return dict(value)
        return {}

    @staticmethod
    def _int_or_none(value: object) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _materialize_prompt_boundary_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        prompt_payload: dict,
        *,
        state: object | None = None,
        publish: bool = True,
    ) -> dict | None:
        if loop is None or self._stream_service is None or self._prompt_service is None:
            return None
        payload = dict(prompt_payload)
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return None
        payload.setdefault("provider", "human")
        self._enrich_prompt_boundary_from_active_batch(payload, state)
        try:
            self._prompt_service.create_prompt(session_id=session_id, prompt=payload)
        except ValueError as exc:
            if str(exc) not in {"duplicate_pending_request_id", "duplicate_recent_request_id"}:
                raise
            if str(exc) == "duplicate_recent_request_id":
                return None

        if not publish:
            return payload

        self._publish_prompt_boundary_sync(loop, session_id, payload)
        return payload

    def _publish_prompt_boundary_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        prompt_payload: dict,
    ) -> None:
        if loop is None or self._stream_service is None:
            return
        payload = dict(prompt_payload)
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return
        request_type = str(payload.get("request_type") or "")
        player_id = int(payload.get("player_id") or 0)
        stream_backend = _stream_backend_of(self._stream_service)
        publish_prompt = lambda: self._stream_service.publish(session_id, "prompt", payload)
        if stream_backend is None:
            _run_runtime_stream_task_sync(
                loop,
                session_id,
                "runtime_prompt_publish_failed",
                publish_prompt,
                timeout=_PROMPT_BOUNDARY_PUBLISH_TIMEOUT_SECONDS,
                attempts=_PROMPT_BOUNDARY_PUBLISH_ATTEMPTS,
                retry_delay=0.05,
                request_id=request_id,
                request_type=request_type,
                player_id=player_id,
            )
        else:
            _schedule_runtime_stream_task(
                loop,
                session_id,
                "runtime_prompt_publish_failed",
                publish_prompt,
                request_id=request_id,
                request_type=request_type,
                player_id=player_id,
            )
        if self._prompt_service is not None:
            self._prompt_service.mark_prompt_delivered(request_id, session_id=session_id)

        public_context = dict(payload.get("public_context") or {})
        requested = build_decision_requested_payload(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            fallback_policy=str(payload.get("fallback_policy") or "required"),
            provider=str(payload.get("provider") or "human"),
            round_index=public_context.get("round_index"),
            turn_index=public_context.get("turn_index"),
            public_context=public_context,
        )
        publish_event = lambda: self._stream_service.publish(session_id, "event", requested)
        if stream_backend is None:
            _run_runtime_stream_task_sync(
                loop,
                session_id,
                "runtime_prompt_event_publish_failed",
                publish_event,
                timeout=_PROMPT_BOUNDARY_PUBLISH_TIMEOUT_SECONDS,
                attempts=_PROMPT_BOUNDARY_PUBLISH_ATTEMPTS,
                retry_delay=0.05,
                request_id=request_id,
                request_type=request_type,
                player_id=player_id,
            )
        else:
            _schedule_runtime_stream_task(
                loop,
                session_id,
                "runtime_prompt_event_publish_failed",
                publish_event,
                request_id=request_id,
                request_type=request_type,
                player_id=player_id,
            )
        self._touch_activity(session_id)

    def _publish_active_module_prompt_batch_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        state: object | None,
    ) -> None:
        if loop is None or self._stream_service is None or self._prompt_service is None or state is None:
            return
        batch = getattr(state, "runtime_active_prompt_batch", None)
        if batch is None:
            return
        prompts = getattr(batch, "prompts_by_player_id", {}) or {}
        for internal_player_id in list(getattr(batch, "missing_player_ids", []) or []):
            continuation = prompts.get(int(internal_player_id))
            if continuation is None:
                continue
            player_id = int(internal_player_id) + 1
            public_context = dict(getattr(continuation, "public_context", {}) or {})
            payload = {
                "request_id": str(getattr(continuation, "request_id", "") or ""),
                "request_type": str(getattr(continuation, "request_type", "") or ""),
                "player_id": player_id,
                "prompt_instance_id": int(getattr(continuation, "prompt_instance_id", 0) or 0),
                "legal_choices": list(getattr(continuation, "legal_choices", []) or []),
                "public_context": public_context,
                "timeout_ms": DEFAULT_HUMAN_PROMPT_TIMEOUT_MS,
                "fallback_policy": "required",
                "runner_kind": "module",
                "resume_token": str(getattr(continuation, "resume_token", "") or ""),
                "frame_id": str(getattr(continuation, "frame_id", "") or ""),
                "module_id": str(getattr(continuation, "module_id", "") or ""),
                "module_type": str(getattr(continuation, "module_type", "") or ""),
                "module_cursor": str(getattr(continuation, "module_cursor", "") or ""),
                "batch_id": str(getattr(batch, "batch_id", "") or ""),
                "missing_player_ids": [
                    int(missing_player_id) + 1
                    for missing_player_id in list(getattr(batch, "missing_player_ids", []) or [])
                ],
                "resume_tokens_by_player_id": {
                    str(player_id): str(getattr(continuation, "resume_token", "") or ""),
                },
                "runtime_module": {
                    "runner_kind": "module",
                    "frame_type": "simultaneous",
                    "frame_id": str(getattr(continuation, "frame_id", "") or ""),
                    "module_id": str(getattr(continuation, "module_id", "") or ""),
                    "module_type": str(getattr(continuation, "module_type", "") or ""),
                    "module_cursor": str(getattr(continuation, "module_cursor", "") or ""),
                },
            }
            self._materialize_prompt_boundary_sync(loop, session_id, {**payload, "provider": "human"})

    @staticmethod
    def _enrich_prompt_boundary_from_active_batch(payload: dict, state: object | None) -> None:
        def _field(source: object | None, key: str, default: object | None = None) -> object | None:
            if isinstance(source, dict):
                return source.get(key, default)
            return getattr(source, key, default)

        def _text_field(source: object | None, key: str) -> str:
            return str(_field(source, key, "") or "").strip()

        request_id = str(payload.get("request_id") or "").strip()
        derived_batch_id = _derive_batch_id_from_request_id(request_id)
        if derived_batch_id and not str(payload.get("batch_id") or "").strip():
            payload["batch_id"] = derived_batch_id

        batch = getattr(state, "runtime_active_prompt_batch", None) if state is not None else None
        if batch is None:
            return

        active_batch_id = _text_field(batch, "batch_id")
        prompts = _field(batch, "prompts_by_player_id", {}) or {}
        if not isinstance(prompts, dict):
            prompts = {}
        matching_prompt = None
        for internal_player_id, continuation in prompts.items():
            if _text_field(continuation, "request_id") == request_id:
                matching_prompt = continuation
                break
            try:
                continuation_internal_player_id = int(internal_player_id)
            except (TypeError, ValueError):
                continue
            if (
                active_batch_id
                and derived_batch_id == active_batch_id
                and _derive_internal_player_id_from_batch_request_id(request_id) == continuation_internal_player_id
            ):
                matching_prompt = continuation
                break
        if matching_prompt is None and (not active_batch_id or derived_batch_id != active_batch_id):
            return

        payload.setdefault("runner_kind", "module")
        payload["batch_id"] = str(active_batch_id or payload.get("batch_id") or "")
        if matching_prompt is not None:
            payload["frame_id"] = str(_text_field(matching_prompt, "frame_id") or payload.get("frame_id") or "")
            payload["module_id"] = str(_text_field(matching_prompt, "module_id") or payload.get("module_id") or "")
            payload["module_type"] = str(_text_field(matching_prompt, "module_type") or payload.get("module_type") or "")
            payload["module_cursor"] = str(_text_field(matching_prompt, "module_cursor") or payload.get("module_cursor") or "")
            payload["resume_token"] = str(_text_field(matching_prompt, "resume_token") or payload.get("resume_token") or "")
        missing_player_ids = [
            int(missing_player_id) + 1
            for missing_player_id in list(_field(batch, "missing_player_ids", []) or [])
        ]
        payload["missing_player_ids"] = missing_player_ids
        payload["resume_tokens_by_player_id"] = {
            str(int(internal_player_id) + 1): _text_field(continuation, "resume_token")
            for internal_player_id, continuation in prompts.items()
            if int(internal_player_id) in list(_field(batch, "missing_player_ids", []) or [])
        }
        runtime_module = dict(payload.get("runtime_module") or {})
        runtime_module.update(
            {
                "runner_kind": "module",
                "frame_type": "simultaneous",
                "frame_id": payload["frame_id"],
                "module_id": payload["module_id"],
                "module_type": payload["module_type"],
                "module_cursor": payload["module_cursor"],
            }
        )
        payload["runtime_module"] = runtime_module


class _ServerDecisionPolicyBridge:
    """Server runtime adapter: normalizes human and AI seats through one decision contract."""

    def __init__(
        self,
        *,
        session_id: str,
        session_seats: list[SeatConfig] | None = None,
        human_seats: list[int],
        ai_fallback,
        prompt_service,
        stream_service,
        loop: asyncio.AbstractEventLoop,
        touch_activity,
        fallback_executor,
        client_factory=None,
        ai_decision_delay_ms: int = 0,
        blocking_human_prompts: bool = True,
    ) -> None:
        self._human_seats = frozenset(int(seat) for seat in human_seats)
        self._session_id = session_id
        self._gateway = DecisionGateway(
            session_id=session_id,
            prompt_service=prompt_service,
            stream_service=stream_service,
            loop=loop,
            touch_activity=touch_activity,
            fallback_executor=fallback_executor,
            ai_decision_delay_ms=ai_decision_delay_ms,
            blocking_human_prompts=blocking_human_prompts,
        )
        factory = client_factory or _ServerDecisionClientFactory()
        self._human_client = factory.create_human_client(
            human_seats=human_seats,
            ai_fallback=ai_fallback,
            gateway=self._gateway,
        )
        default_ai_client = factory.create_ai_client(ai_fallback=ai_fallback, gateway=self._gateway)
        if hasattr(factory, "create_participant_clients"):
            self._participant_clients = factory.create_participant_clients(
                session_seats=session_seats or [],
                human_client=self._human_client,
                ai_fallback=ai_fallback,
                gateway=self._gateway,
            )
        else:
            self._participant_clients = {}
        self._ai_client = self._participant_clients.get("__default_ai__") or default_ai_client
        self._router = _ServerDecisionClientRouter(
            session_seats=session_seats,
            human_seats=human_seats,
            human_client=self._human_client,
            ai_client=self._ai_client,
            participant_clients=self._participant_clients,
        )
        self._inner = self._human_client.policy if self._human_client is not None else None
        self._decision_resume: RuntimeDecisionResume | None = None

    def set_decision_resume(self, resume: RuntimeDecisionResume | None) -> None:
        self._decision_resume = resume

    def set_prompt_sequence(self, value: int) -> None:
        if self._human_client is not None:
            self._human_client.set_prompt_seq(value)

    def current_prompt_sequence(self) -> int:
        if self._human_client is None:
            return 0
        return int(self._human_client.prompt_seq)

    def _ask(self, prompt: dict, parser, fallback_fn):
        if self._human_client is not None:
            self._human_client.bump_prompt_seq()
            prompt = dict(prompt)
            prompt["prompt_instance_id"] = self._human_client.prompt_seq
        return self._gateway.resolve_human_prompt(prompt, parser, fallback_fn)

    def request(self, request):
        invocation = build_decision_invocation_from_request(request)
        fallback_policy = str(getattr(request, "fallback_policy", "required") or "required")
        call = build_routed_decision_call(invocation, fallback_policy=fallback_policy)
        if self._decision_resume is not None and self._decision_resume_matches_call(call, self._decision_resume):
            return self._consume_decision_resume(call)
        client = self._router.client_for_call(call)
        client_policy = getattr(client, "policy", None)
        if callable(getattr(request, "fallback", None)) and (client_policy is None or not hasattr(client_policy, invocation.method_name)):
            return request.fallback()
        return client.resolve(call)

    def _decision_resume_matches_call(self, call, resume: RuntimeDecisionResume) -> bool:
        request = call.request
        expected_player_id = int(request.player_id if request.player_id is not None else -1) + 1
        if expected_player_id != int(resume.player_id):
            return False
        if str(request.request_type or "") != str(resume.request_type or ""):
            return False
        if not self._decision_resume_matches_next_prompt_instance(resume):
            return False
        return True

    def _decision_resume_matches_next_prompt_instance(self, resume: RuntimeDecisionResume) -> bool:
        parsed_instance_id = self._prompt_instance_id_from_resume_request_id(resume)
        if parsed_instance_id <= 0 or self._human_client is None:
            return True
        current_prompt_seq = int(self._human_client.prompt_seq)
        if current_prompt_seq <= 0:
            return True
        return current_prompt_seq + 1 == parsed_instance_id

    def _consume_decision_resume(self, call):
        resume = self._decision_resume
        if resume is None:
            raise RuntimeDecisionResumeMismatch("missing decision resume")
        request = call.request
        expected_player_id = int(request.player_id if request.player_id is not None else -1) + 1
        if expected_player_id != int(resume.player_id):
            raise RuntimeDecisionResumeMismatch("decision resume player mismatch")
        if str(request.request_type or "") != str(resume.request_type or ""):
            raise RuntimeDecisionResumeMismatch("decision resume request type mismatch")
        legal = {str(choice.get("choice_id") or "") for choice in call.legal_choices if isinstance(choice, dict)}
        if legal and str(resume.choice_id) not in legal:
            raise RuntimeDecisionResumeMismatch("decision resume choice is not legal")
        batch_parsed = self._parse_active_flip_batch_resume(call, resume)
        if batch_parsed is not _ACTIVE_FLIP_BATCH_NOT_APPLICABLE:
            parsed = batch_parsed
        else:
            parsed = self._parse_standard_decision_resume_choice(call, resume)
        self._advance_prompt_sequence_after_decision_resume(resume)
        self._decision_resume = None
        self._gateway._publish_decision_resolved(
            request_id=resume.request_id,
            player_id=int(resume.player_id),
            request_type=str(resume.request_type),
            resolution="accepted",
            choice_id=str(resume.choice_id),
            provider="human",
            public_context=dict(request.public_context),
        )
        return parsed

    @staticmethod
    def _parse_standard_decision_resume_choice(call, resume: RuntimeDecisionResume):  # noqa: ANN001
        parser = call.choice_parser
        if parser is None:
            return resume.choice_id
        try:
            return parser(
                str(resume.choice_id),
                call.invocation.args,
                call.invocation.kwargs,
                call.invocation.state,
                call.invocation.player,
            )
        except Exception as exc:
            raise RuntimeDecisionResumeMismatch("decision resume parse failed") from exc

    @staticmethod
    def _parse_active_flip_batch_resume(call, resume: RuntimeDecisionResume):  # noqa: ANN001
        if str(call.request.request_type or "") != "active_flip":
            return _ACTIVE_FLIP_BATCH_NOT_APPLICABLE
        if str(resume.choice_id) != "none":
            return _ACTIVE_FLIP_BATCH_NOT_APPLICABLE
        selected_ids = resume.choice_payload.get("selected_choice_ids")
        if not isinstance(selected_ids, list):
            return _ACTIVE_FLIP_BATCH_NOT_APPLICABLE
        legal_by_id = {
            str(choice.get("choice_id") or ""): choice
            for choice in call.legal_choices
            if isinstance(choice, dict) and str(choice.get("choice_id") or "")
        }
        selected_cards: list[int] = []
        seen_cards: set[int] = set()
        for raw_selected_id in selected_ids:
            selected_id = str(raw_selected_id or "").strip()
            if not selected_id or selected_id == "none":
                continue
            if legal_by_id and selected_id not in legal_by_id:
                raise RuntimeDecisionResumeMismatch("decision resume active flip batch choice is not legal")
            choice = legal_by_id.get(selected_id, {})
            value = choice.get("value") if isinstance(choice, dict) else None
            card_index_source = value.get("card_index") if isinstance(value, dict) else selected_id
            try:
                card_index = int(card_index_source)
            except (TypeError, ValueError) as exc:
                raise RuntimeDecisionResumeMismatch("decision resume active flip batch parse failed") from exc
            if card_index in seen_cards:
                continue
            seen_cards.add(card_index)
            selected_cards.append(card_index)
        return selected_cards if selected_cards else None

    def _advance_prompt_sequence_after_decision_resume(self, resume: RuntimeDecisionResume) -> None:
        if self._human_client is None:
            return
        parsed_instance_id = self._prompt_instance_id_from_resume_request_id(resume)
        next_instance_id = max(self._human_client.prompt_seq + 1, parsed_instance_id)
        self._human_client.set_prompt_seq(next_instance_id)

    @staticmethod
    def _prompt_instance_id_from_resume_request_id(resume: RuntimeDecisionResume) -> int:
        request_type = str(resume.request_type or "").strip()
        request_id = str(resume.request_id or "").strip()
        if not request_type or not request_id:
            return 0
        marker = f":{request_type}:"
        if marker not in request_id:
            return 0
        raw_instance_id = request_id.rsplit(marker, 1)[-1]
        try:
            return max(0, int(raw_instance_id))
        except ValueError:
            return 0

    def __getattr__(self, name: str):
        target = self._router.attribute_target(name)
        if hasattr(target, name):
            attr = getattr(target, name)
            if not name.startswith("choose_") or not callable(attr):
                return attr
        elif not name.startswith("choose_"):
            raise AttributeError(name)

        def _wrapped(*args, **kwargs):
            invocation = build_decision_invocation(name, args, kwargs)
            call = build_routed_decision_call(invocation, fallback_policy="ai")
            if self._decision_resume is not None and self._decision_resume_matches_call(call, self._decision_resume):
                return self._consume_decision_resume(call)
            client = self._router.client_for_call(call)
            return client.resolve(call)

        return _wrapped


_ServerHumanPolicyBridge = _ServerDecisionPolicyBridge


class _LocalAiDecisionClient:
    def __init__(self, *, ai_fallback, gateway: DecisionGateway) -> None:
        self.policy = ai_fallback
        self._gateway = gateway

    def resolve(self, call):
        ai_callable = getattr(self.policy, call.invocation.method_name)
        request = call.request
        player_id = int(request.player_id if request.player_id is not None else -1) + 1
        return self._gateway.resolve_ai_decision(
            request_type=request.request_type,
            player_id=player_id,
            public_context=request.public_context,
            resolver=lambda: ai_callable(*call.invocation.args, **call.invocation.kwargs),
            choice_serializer=call.choice_serializer,
        )


@dataclass(frozen=True)
class _ExternalAiDecisionEnvelope:
    request_id: str
    session_id: str
    seat: int
    player_id: int
    method_name: str
    request_type: str
    fallback_policy: str
    public_context: dict[str, object]
    legal_choices: list[dict[str, object]]
    transport: str
    worker_contract_version: str
    required_capabilities: list[str]
    participant_config: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "seat": self.seat,
            "player_id": self.player_id,
            "decision_name": self.method_name,
            "request_type": self.request_type,
            "fallback_policy": self.fallback_policy,
            "public_context": dict(self.public_context),
            "legal_choices": list(self.legal_choices),
            "transport": self.transport,
            "worker_contract_version": self.worker_contract_version,
            "required_capabilities": list(self.required_capabilities),
        }


class _ExternalAiTransportBase:
    def __init__(
        self,
        *,
        session_id: str,
        ai_fallback,
        gateway: DecisionGateway,
        seat: int,
        config: dict[str, object] | None = None,
        transport_name: str,
    ) -> None:
        self.policy = ai_fallback
        self._session_id = session_id
        self._gateway = gateway
        self._seat = int(seat)
        self._config = dict(config or {})
        self._transport_name = transport_name

    def _build_envelope(self, call) -> _ExternalAiDecisionEnvelope:
        request = call.request
        player_id = int(request.player_id if request.player_id is not None else -1) + 1
        contract_version = str(self._config.get("contract_version", "v1") or "v1").strip().lower()
        raw_capabilities = self._config.get("required_capabilities") or []
        required_capabilities = [
            str(capability).strip()
            for capability in raw_capabilities
            if isinstance(capability, str) and str(capability).strip()
        ]
        return _ExternalAiDecisionEnvelope(
            request_id=f"{self._session_id}_ext_{uuid.uuid4().hex[:10]}",
            session_id=self._session_id,
            seat=self._seat,
            player_id=player_id,
            method_name=call.invocation.method_name,
            request_type=request.request_type,
            fallback_policy=request.fallback_policy,
            public_context=dict(request.public_context),
            legal_choices=[dict(choice) for choice in getattr(call, "legal_choices", [])],
            transport=self._transport_name,
            worker_contract_version=contract_version,
            required_capabilities=required_capabilities,
            participant_config=dict(self._config),
        )

    def _publish(
        self,
        call,
        resolver,
        public_context_patch: dict[str, object] | None = None,
        *,
        pass_public_context: bool = False,
    ):
        request = call.request
        public_context = dict(request.public_context)
        public_context.setdefault("participant_client", ParticipantClientType.EXTERNAL_AI.value)
        public_context.setdefault("participant_seat", self._seat)
        public_context.setdefault("participant_transport", self._transport_name)
        if self._config:
            public_context.setdefault("participant_config", dict(self._config))
        if public_context_patch:
            public_context.update(public_context_patch)
        if pass_public_context:
            wrapped_resolver = lambda: resolver(public_context)
        else:
            wrapped_resolver = resolver
        player_id = int(request.player_id if request.player_id is not None else -1) + 1
        return self._gateway.resolve_ai_decision(
            request_type=request.request_type,
            player_id=player_id,
            public_context=public_context,
            resolver=wrapped_resolver,
            choice_serializer=call.choice_serializer,
        )


class _LoopbackExternalAiTransport(_ExternalAiTransportBase):
    """Default external-AI transport adapter using a local loopback sender."""

    def __init__(self, *, session_id: str, ai_fallback, gateway: DecisionGateway, seat: int, config: dict[str, object] | None = None) -> None:
        super().__init__(
            session_id=session_id,
            ai_fallback=ai_fallback,
            gateway=gateway,
            seat=seat,
            config=config,
            transport_name="loopback",
        )

    def resolve(self, call):
        ai_callable = getattr(self.policy, call.invocation.method_name)
        envelope = self._build_envelope(call)
        return self._publish(
            call,
            resolver=lambda: ai_callable(*call.invocation.args, **call.invocation.kwargs),
        )


class _ExternalAiDecisionClient:
    def __init__(self, *, transport: _LoopbackExternalAiTransport) -> None:
        self.policy = getattr(transport, "policy", None)
        self._transport = transport

    def resolve(self, call):
        return self._transport.resolve(call)


class _HttpExternalAiTransport(_ExternalAiTransportBase):
    """HTTP-shaped external-AI transport seam with an injectable sender."""

    def __init__(
        self,
        *,
        session_id: str,
        ai_fallback,
        gateway: DecisionGateway,
        seat: int,
        config: dict[str, object] | None = None,
        sender=None,
        healthchecker=None,
    ) -> None:
        super().__init__(
            session_id=session_id,
            ai_fallback=ai_fallback,
            gateway=gateway,
            seat=seat,
            config=config,
            transport_name="http",
        )
        self._sender = sender
        self._healthchecker = healthchecker

    def resolve(self, call):
        ai_callable = getattr(self.policy, call.invocation.method_name)
        envelope = self._build_envelope(call)
        parser = getattr(call, "choice_parser", None)
        retry_count = max(0, int(self._config.get("retry_count", 1) or 0))
        max_attempt_count = max(1, int(self._config.get("max_attempt_count", 3) or 1))
        effective_attempt_count = min(retry_count + 1, max_attempt_count)
        backoff_ms = max(0, int(self._config.get("backoff_ms", 250) or 0))
        fallback_mode = str(self._config.get("fallback_mode", "local_ai") or "local_ai").strip().lower()
        diagnostics: dict[str, object] = {
            "external_ai_transport_mode": "http",
            "external_ai_resolution_status": "pending",
            "external_ai_ready_state": "-",
            "external_ai_attempt_count": 0,
            "external_ai_attempt_limit": effective_attempt_count,
            "external_ai_worker_profile": "-",
            "external_ai_policy_mode": "-",
            "external_ai_worker_adapter": "-",
            "external_ai_policy_class": "-",
            "external_ai_decision_style": "-",
        }

        def _resolve_via_sender(public_context: dict[str, object]):
            last_error: Exception | None = None
            for attempt in range(effective_attempt_count):
                try:
                    public_context["external_ai_attempt_count"] = attempt + 1
                    health = self._check_worker_health()
                    if isinstance(health, dict):
                        ready_state = _external_ai_ready_state_value(health)
                        if ready_state is not None:
                            public_context["external_ai_ready_state"] = ready_state
                        if bool(self._config.get("require_ready", False)) and health.get("ready") is not True:
                            raise RuntimeError("external_ai_worker_not_ready")
                        _validate_external_ai_transport_support(health, envelope.transport)
                        _validate_external_ai_request_type_support(health, envelope.request_type)
                        worker_id = str(health.get("worker_id") or "").strip()
                        if worker_id:
                            public_context["external_ai_worker_id"] = worker_id
                        worker_profile = str(health.get("worker_profile") or "").strip()
                        if worker_profile:
                            public_context["external_ai_worker_profile"] = worker_profile
                        policy_mode = str(health.get("policy_mode") or "").strip()
                        if policy_mode:
                            public_context["external_ai_policy_mode"] = policy_mode
                        worker_adapter = str(health.get("worker_adapter") or "").strip()
                        if worker_adapter:
                            public_context["external_ai_worker_adapter"] = worker_adapter
                        policy_class = str(health.get("policy_class") or "").strip()
                        if policy_class:
                            public_context["external_ai_policy_class"] = policy_class
                        decision_style = str(health.get("decision_style") or "").strip()
                        if decision_style:
                            public_context["external_ai_decision_style"] = decision_style
                    response = self._sender(envelope) if self._sender is not None else _default_external_ai_http_sender(envelope)
                    if not isinstance(response, dict):
                        raise ValueError("external_ai_response_not_object")
                    ready_state = _external_ai_ready_state_value(response)
                    if ready_state is not None:
                        public_context["external_ai_ready_state"] = ready_state
                    _validate_external_ai_response_payload(response, envelope.participant_config)
                    _validate_external_ai_transport_support(response, envelope.transport)
                    _validate_external_ai_request_type_support(response, envelope.request_type)
                    _validate_external_ai_identity(response, envelope.participant_config)
                    worker_id = str(response.get("worker_id") or "").strip()
                    if worker_id:
                        public_context["external_ai_worker_id"] = worker_id
                    worker_profile = str(response.get("worker_profile") or "").strip()
                    if worker_profile:
                        public_context["external_ai_worker_profile"] = worker_profile
                    policy_mode = str(response.get("policy_mode") or "").strip()
                    if policy_mode:
                        public_context["external_ai_policy_mode"] = policy_mode
                    worker_adapter = str(response.get("worker_adapter") or "").strip()
                    if worker_adapter:
                        public_context["external_ai_worker_adapter"] = worker_adapter
                    policy_class = str(response.get("policy_class") or "").strip()
                    if policy_class:
                        public_context["external_ai_policy_class"] = policy_class
                    decision_style = str(response.get("decision_style") or "").strip()
                    if decision_style:
                        public_context["external_ai_decision_style"] = decision_style
                    choice_id = response.get("choice_id")
                    if not isinstance(choice_id, str) or not choice_id.strip():
                        raise ValueError("external_ai_missing_choice_id")
                    public_context["external_ai_resolution_status"] = "resolved_by_worker"
                    if callable(parser):
                        return parser(choice_id.strip(), call.invocation.args, call.invocation.kwargs, call.invocation.state, call.invocation.player)
                    return choice_id.strip()
                except Exception as exc:
                    last_error = exc
                    public_context["external_ai_failure_code"] = _classify_external_ai_error(exc)
                    public_context["external_ai_failure_detail"] = str(exc)
                    public_context["external_ai_resolution_status"] = "worker_failed"
                    if attempt < effective_attempt_count - 1 and backoff_ms > 0:
                        time.sleep(backoff_ms / 1000.0)
                        continue
            if fallback_mode == "local_ai":
                public_context["external_ai_fallback_mode"] = "local_ai"
                public_context["external_ai_resolution_status"] = "resolved_by_local_fallback"
                return ai_callable(*call.invocation.args, **call.invocation.kwargs)
            raise last_error or RuntimeError("external_ai_transport_failed")

        return self._publish(
            call,
            resolver=_resolve_via_sender,
            public_context_patch=diagnostics,
            pass_public_context=True,
        )

    def _check_worker_health(self) -> dict[str, object] | None:
        healthcheck_policy = str(self._config.get("healthcheck_policy", "auto") or "auto").strip().lower()
        if healthcheck_policy == "disabled":
            return None
        if healthcheck_policy != "required" and self._sender is not None and self._healthchecker is None:
            return None
        checker = self._healthchecker or _default_external_ai_healthcheck
        payload = checker(dict(self._config))
        if not isinstance(payload, dict):
            raise ValueError("external_ai_health_response_not_object")
        if self._healthchecker is not None or healthcheck_policy == "required":
            _validate_external_ai_health_payload(payload, self._config)
        return payload if isinstance(payload, dict) else None


def _default_external_ai_http_sender(envelope: _ExternalAiDecisionEnvelope) -> dict[str, object]:
    endpoint = str(envelope.participant_config.get("endpoint") or "").strip()
    if not endpoint:
        raise ValueError("external_ai_missing_endpoint")
    timeout_ms = int(
        envelope.participant_config.get("timeout_ms", DEFAULT_EXTERNAL_AI_TIMEOUT_MS) or DEFAULT_EXTERNAL_AI_TIMEOUT_MS
    )
    headers = {"Content-Type": "application/json"}
    _merge_external_ai_auth_headers(headers, envelope.participant_config)
    raw_headers = envelope.participant_config.get("headers") or {}
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value
    body = json.dumps(envelope.to_payload()).encode("utf-8")
    request = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(request, timeout=max(0.001, timeout_ms / 1000.0)) as response:
            payload = response.read().decode("utf-8")
    except urllib_error.URLError as exc:
        raise RuntimeError("external_ai_http_error") from exc
    parsed = json.loads(payload or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("external_ai_response_not_object")
    _validate_external_ai_identity(parsed, envelope.participant_config)
    return parsed


_EXTERNAL_AI_HEALTH_CACHE: dict[str, tuple[float, dict[str, object]]] = {}


def _external_ai_health_cache_key(config: dict[str, object], endpoint: str, healthcheck_path: str) -> str:
    required_version = str(config.get("contract_version", "v1") or "v1").strip().lower()
    expected_worker_id = str(config.get("expected_worker_id") or "").strip()
    healthcheck_policy = str(config.get("healthcheck_policy", "auto") or "auto").strip().lower()
    require_ready = "1" if bool(config.get("require_ready", False)) else "0"
    required_capabilities = sorted(
        str(item).strip()
        for item in (config.get("required_capabilities") or [])
        if isinstance(item, str) and str(item).strip()
    )
    required_request_types = sorted(
        str(item).strip()
        for item in (config.get("required_request_types") or [])
        if isinstance(item, str) and str(item).strip()
    )
    required_policy_mode = str(config.get("required_policy_mode") or "").strip()
    required_worker_adapter = str(config.get("required_worker_adapter") or "").strip()
    required_policy_class = str(config.get("required_policy_class") or "").strip()
    required_decision_style = str(config.get("required_decision_style") or "").strip()
    auth_header_name = str(config.get("auth_header_name", "Authorization") or "Authorization").strip()
    auth_scheme = str(config.get("auth_scheme", "Bearer") or "Bearer").strip()
    return "|".join(
        [
            endpoint,
            healthcheck_path,
            required_version,
            expected_worker_id,
            healthcheck_policy,
            require_ready,
            ",".join(required_capabilities),
            ",".join(required_request_types),
            required_policy_mode,
            required_worker_adapter,
            required_policy_class,
            required_decision_style,
            auth_header_name,
            auth_scheme,
        ]
    )


def _default_external_ai_healthcheck(config: dict[str, object]) -> dict[str, object]:
    endpoint = str(config.get("endpoint") or "").strip()
    if not endpoint:
        raise ValueError("external_ai_missing_endpoint")
    healthcheck_path = str(config.get("healthcheck_path", "/health") or "/health").strip() or "/health"
    timeout_ms = int(config.get("timeout_ms", DEFAULT_EXTERNAL_AI_TIMEOUT_MS) or DEFAULT_EXTERNAL_AI_TIMEOUT_MS)
    ttl_ms = max(0, int(config.get("healthcheck_ttl_ms", 10000) or 0))
    required_version = str(config.get("contract_version", "v1") or "v1").strip().lower()
    required_capabilities = {
        str(item).strip()
        for item in (config.get("required_capabilities") or [])
        if isinstance(item, str) and str(item).strip()
    }
    cache_key = _external_ai_health_cache_key(config, endpoint, healthcheck_path)
    now = time.time() * 1000.0
    cached = _EXTERNAL_AI_HEALTH_CACHE.get(cache_key)
    if cached is not None and ttl_ms > 0 and now - cached[0] <= ttl_ms:
        return dict(cached[1])

    base_url = endpoint.rsplit("/", 1)[0] if "/" in endpoint[8:] else endpoint
    health_url = f"{base_url.rstrip('/')}/{healthcheck_path.lstrip('/')}"
    headers = {}
    _merge_external_ai_auth_headers(headers, config)
    raw_headers = config.get("headers") or {}
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value
    request = urllib_request.Request(health_url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(request, timeout=max(0.001, timeout_ms / 1000.0)) as response:
            payload = response.read().decode("utf-8")
    except urllib_error.URLError as exc:
        raise RuntimeError("external_ai_healthcheck_failed") from exc
    parsed = json.loads(payload or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("external_ai_health_response_not_object")
    _validate_external_ai_health_payload(
        parsed,
        {
            **config,
            "contract_version": required_version,
            "required_capabilities": list(required_capabilities),
        },
    )
    _EXTERNAL_AI_HEALTH_CACHE[cache_key] = (now, dict(parsed))
    return parsed


def _merge_external_ai_auth_headers(headers: dict[str, str], config: dict[str, object]) -> None:
    auth_token = str(config.get("auth_token") or "").strip()
    if not auth_token:
        return
    header_name = str(config.get("auth_header_name", "Authorization") or "Authorization").strip() or "Authorization"
    auth_scheme = str(config.get("auth_scheme", "Bearer") or "Bearer").strip()
    headers[header_name] = f"{auth_scheme} {auth_token}".strip() if auth_scheme else auth_token


def _validate_external_ai_identity(payload: dict[str, object], config: dict[str, object]) -> None:
    expected_worker_id = str(config.get("expected_worker_id") or "").strip()
    if not expected_worker_id:
        return
    worker_id = str(payload.get("worker_id") or "").strip()
    if worker_id != expected_worker_id:
        raise RuntimeError("external_ai_worker_identity_mismatch")


def _validate_external_ai_health_payload(payload: dict[str, object], config: dict[str, object]) -> None:
    if payload.get("ok") is not True:
        raise RuntimeError("external_ai_health_not_ok")
    _validate_external_ai_identity(payload, config)
    required_version = str(config.get("contract_version", "v1") or "v1").strip().lower()
    worker_version = str(payload.get("worker_contract_version") or "").strip().lower()
    if required_version and worker_version and worker_version != required_version:
        raise RuntimeError("external_ai_contract_version_mismatch")
    required_capabilities = {
        str(item).strip()
        for item in (config.get("required_capabilities") or [])
        if isinstance(item, str) and str(item).strip()
    }
    required_request_types = {
        str(item).strip()
        for item in (config.get("required_request_types") or [])
        if isinstance(item, str) and str(item).strip()
    }
    available_capabilities = {
        str(item).strip()
        for item in (payload.get("capabilities") or [])
        if isinstance(item, str) and str(item).strip()
    }
    available_request_types = {
        str(item).strip()
        for item in (payload.get("supported_request_types") or [])
        if isinstance(item, str) and str(item).strip()
    }
    required_policy_mode = str(config.get("required_policy_mode") or "").strip()
    required_worker_adapter = str(config.get("required_worker_adapter") or "").strip()
    required_policy_class = str(config.get("required_policy_class") or "").strip()
    required_decision_style = str(config.get("required_decision_style") or "").strip()
    actual_policy_mode = str(payload.get("policy_mode") or "").strip()
    actual_worker_adapter = str(payload.get("worker_adapter") or "").strip()
    actual_policy_class = str(payload.get("policy_class") or "").strip()
    actual_decision_style = str(payload.get("decision_style") or "").strip()
    if required_capabilities and not required_capabilities.issubset(available_capabilities):
        raise RuntimeError("external_ai_missing_required_capability")
    if required_request_types and not required_request_types.issubset(available_request_types):
        raise RuntimeError("external_ai_missing_required_request_type")
    if required_policy_mode and actual_policy_mode != required_policy_mode:
        raise RuntimeError("external_ai_policy_mode_mismatch")
    if required_worker_adapter and actual_worker_adapter != required_worker_adapter:
        raise RuntimeError("external_ai_worker_adapter_mismatch")
    if required_policy_class and actual_policy_class != required_policy_class:
        raise RuntimeError("external_ai_policy_class_mismatch")
    if required_decision_style and actual_decision_style != required_decision_style:
        raise RuntimeError("external_ai_decision_style_mismatch")


def _external_ai_ready_state_value(payload: dict[str, object]) -> str | None:
    ready = payload.get("ready")
    if isinstance(ready, bool):
        return "ready" if ready else "not_ready"
    return None


def _validate_external_ai_response_payload(payload: dict[str, object], config: dict[str, object]) -> None:
    _validate_external_ai_identity(payload, config)
    if bool(config.get("require_ready", False)) and payload.get("ready") is False:
        raise RuntimeError("external_ai_worker_not_ready")


def _validate_external_ai_request_type_support(payload: dict[str, object], request_type: str) -> None:
    supported_request_types = payload.get("supported_request_types")
    if not isinstance(supported_request_types, list):
        return
    supported = {
        str(item).strip()
        for item in supported_request_types
        if isinstance(item, str) and str(item).strip()
    }
    if supported and request_type not in supported:
        raise RuntimeError("external_ai_missing_request_type_support")


def _validate_external_ai_transport_support(payload: dict[str, object], transport_name: str) -> None:
    supported_transports = payload.get("supported_transports")
    if not isinstance(supported_transports, list):
        return
    supported = {
        str(item).strip()
        for item in supported_transports
        if isinstance(item, str) and str(item).strip()
    }
    if supported and transport_name not in supported:
        raise RuntimeError("external_ai_missing_transport_support")


def _classify_external_ai_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message in {
        "external_ai_http_error",
        "external_ai_healthcheck_failed",
        "external_ai_worker_identity_mismatch",
        "external_ai_contract_version_mismatch",
        "external_ai_missing_required_capability",
        "external_ai_missing_required_request_type",
        "external_ai_policy_mode_mismatch",
        "external_ai_worker_adapter_mismatch",
        "external_ai_policy_class_mismatch",
        "external_ai_decision_style_mismatch",
        "external_ai_worker_not_ready",
        "external_ai_missing_request_type_support",
        "external_ai_missing_transport_support",
        "external_ai_missing_choice_id",
        "external_ai_response_not_object",
        "external_ai_health_response_not_object",
        "external_ai_health_not_ok",
        "external_ai_missing_endpoint",
    }:
        return message
    if isinstance(exc, TimeoutError):
        return "external_ai_timeout"
    if isinstance(exc, ValueError):
        return message or "external_ai_value_error"
    if isinstance(exc, RuntimeError):
        return message or "external_ai_runtime_error"
    return exc.__class__.__name__.lower()


class _LocalHumanDecisionClient:
    def __init__(self, *, human_seats: list[int], ai_fallback, gateway: DecisionGateway) -> None:
        if not human_seats:
            self.policy = None
            return
        RuntimeService._ensure_engine_import_path()
        from viewer.human_policy import HumanHttpPolicy

        self.policy = HumanHttpPolicy(
            human_seat=human_seats[0],
            human_seats=human_seats,
            ai_fallback=ai_fallback,
        )
        self.policy._ask = self._ask  # type: ignore[method-assign]
        self._gateway = gateway
        self._active_call = None

    @property
    def prompt_seq(self) -> int:
        if self.policy is None:
            return 0
        return int(getattr(self.policy, "_prompt_seq", 0))

    def bump_prompt_seq(self) -> None:
        if self.policy is not None:
            self.policy._prompt_seq += 1  # type: ignore[attr-defined]

    def set_prompt_seq(self, value: int) -> None:
        if self.policy is not None:
            self.policy._prompt_seq = max(0, int(value))  # type: ignore[attr-defined]

    def _ask(self, prompt: dict, parser, fallback_fn):
        envelope = dict(prompt)
        self.bump_prompt_seq()
        envelope.setdefault("prompt_instance_id", self.prompt_seq)
        active_call = self._active_call
        if active_call is not None:
            request = getattr(active_call, "request", None)
            if request is not None:
                envelope.setdefault("request_type", getattr(request, "request_type", None))
                internal_player_id = getattr(request, "player_id", None)
                if internal_player_id is not None:
                    envelope["player_id"] = int(internal_player_id) + 1 if internal_player_id is not None else None
                else:
                    envelope.setdefault("player_id", None)
                envelope.setdefault("fallback_policy", getattr(request, "fallback_policy", None))
                prompt_context = dict(envelope.get("public_context") or {})
                request_context = dict(getattr(request, "public_context", {}) or {})
                envelope["public_context"] = {**prompt_context, **request_context}
            self._attach_active_module_continuation(envelope, active_call)
        return self._gateway.resolve_human_prompt(envelope, parser, fallback_fn)

    def _attach_active_module_continuation(self, envelope: dict, active_call) -> None:  # noqa: ANN001
        invocation = getattr(active_call, "invocation", None)
        state = getattr(invocation, "state", None)
        if state is None or str(getattr(state, "runtime_runner_kind", "") or "").lower() != "module":
            return
        frame, module = self._active_frame_and_module(state)
        if frame is None or module is None:
            return
        public_context = dict(envelope.get("public_context") or {})
        if not str(envelope.get("request_id") or "").strip():
            stable_request_id = getattr(self._gateway, "_stable_prompt_request_id", None)
            if callable(stable_request_id):
                envelope["request_id"] = str(stable_request_id(envelope, public_context))
        request_id = str(envelope.get("request_id") or "").strip()
        if not request_id:
            return
        request = getattr(active_call, "request", None)
        request_type = str(envelope.get("request_type") or getattr(request, "request_type", "") or "")
        internal_player_id = getattr(request, "player_id", None)
        if internal_player_id is None:
            internal_player_id = int(envelope.get("player_id", 1) or 1) - 1
        legal_choices = envelope.get("legal_choices")
        if not isinstance(legal_choices, list):
            legal_choices = list(getattr(active_call, "legal_choices", []) or [])
            envelope["legal_choices"] = legal_choices
        RuntimeService._ensure_engine_import_path()
        from runtime_modules.prompts import PromptApi

        existing_continuation = getattr(state, "runtime_active_prompt", None)
        if self._is_matching_prompt_continuation(
            existing_continuation,
            request_id=request_id,
            frame_id=str(getattr(frame, "frame_id", "") or ""),
            module_id=str(getattr(module, "module_id", "") or ""),
            player_id=int(internal_player_id),
            request_type=request_type,
        ):
            continuation = existing_continuation
        else:
            continuation = PromptApi().create_continuation(
                request_id=request_id,
                prompt_instance_id=int(envelope.get("prompt_instance_id", 0) or 0),
                frame=frame,
                module=module,
                player_id=int(internal_player_id),
                request_type=request_type,
                legal_choices=[dict(choice) for choice in legal_choices if isinstance(choice, dict)],
                public_context=public_context,
            )
        state.runtime_active_prompt = continuation
        state.runtime_active_prompt_batch = None
        module_fields = {
            "runner_kind": "module",
            "frame_type": str(getattr(frame, "frame_type", "") or ""),
            "frame_id": continuation.frame_id,
            "module_id": continuation.module_id,
            "module_type": continuation.module_type,
            "module_cursor": continuation.module_cursor,
            "idempotency_key": str(getattr(module, "idempotency_key", "") or ""),
        }
        envelope.update(
            {
                "runner_kind": "module",
                "resume_token": continuation.resume_token,
                "frame_id": continuation.frame_id,
                "module_id": continuation.module_id,
                "module_type": continuation.module_type,
                "module_cursor": continuation.module_cursor,
                "runtime_module": module_fields,
            }
        )

    @staticmethod
    def _is_matching_prompt_continuation(
        continuation,
        *,
        request_id: str,
        frame_id: str,
        module_id: str,
        player_id: int,
        request_type: str,
    ) -> bool:  # noqa: ANN001
        if continuation is None:
            return False
        continuation_player_id = getattr(continuation, "player_id", None)
        if continuation_player_id is None:
            return False
        return (
            str(getattr(continuation, "request_id", "") or "") == request_id
            and str(getattr(continuation, "frame_id", "") or "") == frame_id
            and str(getattr(continuation, "module_id", "") or "") == module_id
            and int(continuation_player_id) == int(player_id)
            and str(getattr(continuation, "request_type", "") or "") == request_type
        )

    @staticmethod
    def _active_frame_and_module(state) -> tuple[object | None, object | None]:  # noqa: ANN001
        frames = getattr(state, "runtime_frame_stack", None)
        if not isinstance(frames, list):
            return None, None
        for frame in reversed(frames):
            active_module_id = getattr(frame, "active_module_id", None)
            if not active_module_id:
                continue
            for module in getattr(frame, "module_queue", []) or []:
                if getattr(module, "module_id", None) == active_module_id:
                    return frame, module
        return None, None

    def resolve(self, call):
        if self.policy is None:
            raise AttributeError(call.invocation.method_name)
        self._active_call = call
        try:
            return getattr(self.policy, call.invocation.method_name)(*call.invocation.args, **call.invocation.kwargs)
        finally:
            self._active_call = None


class _ServerDecisionClientRouter:
    def __init__(
        self,
        *,
        session_seats: list[SeatConfig] | None = None,
        human_seats: list[int] | None = None,
        human_client: _LocalHumanDecisionClient,
        ai_client: _LocalAiDecisionClient,
        participant_clients: dict[object, object] | None = None,
    ) -> None:
        self._seat_types_by_player_id: dict[int, SeatType] = {}
        if session_seats:
            self._seat_types_by_player_id = {
                max(0, int(seat.seat) - 1): seat.seat_type
                for seat in session_seats
            }
        else:
            self._seat_types_by_player_id = {
                int(seat): SeatType.HUMAN
                for seat in (human_seats or [])
            }
        self._human_client = human_client
        self._ai_client = ai_client
        self._participant_clients = dict(participant_clients or {})

    def attribute_target(self, name: str):
        human_policy = self._human_client.policy
        if human_policy is not None and hasattr(human_policy, name):
            return human_policy
        return self._ai_client.policy

    def client_for_call(self, call):
        player_id = call.request.player_id
        if isinstance(player_id, int) and player_id in self._participant_clients:
            return self._participant_clients[player_id]
        if self.seat_type_for_player_id(player_id) == SeatType.HUMAN and self._human_client.policy is not None:
            return self._human_client
        return self._ai_client

    def seat_type_for_player_id(self, player_id: int | None) -> SeatType | None:
        if not isinstance(player_id, int):
            return None
        return self._seat_types_by_player_id.get(player_id)


class _ServerDecisionClientFactory:
    def __init__(self, *, external_ai_sender=None, external_ai_healthchecker=None) -> None:
        self._external_ai_sender = external_ai_sender
        self._external_ai_healthchecker = external_ai_healthchecker

    def create_ai_client(self, *, ai_fallback, gateway: DecisionGateway):
        return _LocalAiDecisionClient(ai_fallback=ai_fallback, gateway=gateway)

    def create_human_client(self, *, human_seats: list[int], ai_fallback, gateway: DecisionGateway):
        return _LocalHumanDecisionClient(
            human_seats=human_seats,
            ai_fallback=ai_fallback,
            gateway=gateway,
        )

    def create_participant_clients(self, *, session_seats: list[SeatConfig], human_client, ai_fallback, gateway: DecisionGateway):
        clients: dict[object, object] = {}
        default_ai_client = self.create_ai_client(ai_fallback=ai_fallback, gateway=gateway)
        clients["__default_ai__"] = default_ai_client
        for seat in session_seats:
            player_id = max(0, int(seat.seat) - 1)
            participant_client = seat.participant_client
            if seat.seat_type == SeatType.HUMAN:
                clients[player_id] = human_client
                continue
            if participant_client == ParticipantClientType.EXTERNAL_AI:
                transport = self.create_external_ai_transport(
                    session_id=gateway._session_id,  # type: ignore[attr-defined]
                    ai_fallback=ai_fallback,
                    gateway=gateway,
                    seat=seat.seat,
                    config=seat.participant_config,
                )
                clients[player_id] = _ExternalAiDecisionClient(transport=transport)
                continue
            clients[player_id] = default_ai_client
        return clients

    def create_external_ai_transport(
        self,
        *,
        session_id: str,
        ai_fallback,
        gateway: DecisionGateway,
        seat: int,
        config: dict[str, object] | None = None,
    ):
        transport_kind = str((config or {}).get("transport", "loopback")).strip().lower()
        if transport_kind == "http":
            return _HttpExternalAiTransport(
                session_id=session_id,
                ai_fallback=ai_fallback,
                gateway=gateway,
                seat=seat,
                config=config,
                sender=self._external_ai_sender,
                healthchecker=self._external_ai_healthchecker,
            )
        return _LoopbackExternalAiTransport(
            session_id=session_id,
            ai_fallback=ai_fallback,
            gateway=gateway,
            seat=seat,
            config=config,
        )


class _FanoutVisEventStream:
    """Engine event stream bridge that forwards events to StreamService immediately."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        stream_service,
        session_id: str,
        touch_activity,
        *,
        human_player_ids: list[int] | None = None,
        spectator_event_delay_ms: int = 0,
    ) -> None:
        self._loop = loop
        self._stream_service = stream_service
        self._session_id = session_id
        self._events: list = []
        self._touch_activity = touch_activity
        self._human_player_ids = frozenset(int(player_id) for player_id in (human_player_ids or []))
        self._spectator_event_delay_ms = max(0, int(spectator_event_delay_ms))

    def append(self, event) -> None:
        self._events.append(event)
        self._touch_activity(self._session_id)
        payload = event.to_dict()
        latest_seq = 0
        if callable(getattr(self._stream_service, "latest_seq", None)):
            latest_seq_fut = asyncio.run_coroutine_threadsafe(
                self._stream_service.latest_seq(self._session_id),
                self._loop,
            )
            latest_seq = int(latest_seq_fut.result() or 0)
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, "event", payload),
            self._loop,
        )
        published = fut.result()
        published_seq = int(getattr(published, "seq", 0) or 0)
        if published_seq > latest_seq:
            write_game_debug_log(
                "engine",
                str(payload.get("event_type") or "engine_event"),
                session_id=self._session_id,
                **_runtime_module_debug_fields(payload),
                payload=payload,
            )
        else:
            return
        delay_seconds = self._delay_seconds_after_event(payload)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    @property
    def events(self) -> list:
        return list(self._events)

    def __iter__(self):
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def _delay_seconds_after_event(self, payload: dict[str, object]) -> float:
        if self._spectator_event_delay_ms <= 0:
            return 0.0
        event_type = str(payload.get("event_type") or "").strip()
        if event_type not in {
            "turn_start",
            "weather_reveal",
            "draft_pick",
            "final_character_choice",
            "dice_roll",
            "player_move",
            "landing_resolved",
            "rent_paid",
            "tile_purchased",
            "fortune_drawn",
            "fortune_resolved",
            "start_reward_chosen",
            "lap_reward_chosen",
            "marker_transferred",
            "marker_flip",
            "trick_used",
            "game_end",
            "turn_end_snapshot",
        }:
            return 0.0
        # Always linger a bit on dice results and the actual move so both
        # human and AI turns read like visible motion instead of instant jumps.
        if event_type in {"dice_roll", "player_move"}:
            return max(self._spectator_event_delay_ms, 900) / 1000.0
        actor = payload.get("acting_player_id")
        if not isinstance(actor, int):
            actor = payload.get("player_id")
        if not isinstance(actor, int):
            actor = payload.get("player")
        if not isinstance(actor, int):
            return 0.0
        return self._spectator_event_delay_ms / 1000.0 if actor not in self._human_player_ids else 0.0
