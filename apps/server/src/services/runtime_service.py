from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import functools
import inspect
import json
import os
import random
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.domain.protocol_identity import display_identity_fields
from apps.server.src.domain.protocol_ids import int_or_default, turn_label as protocol_turn_label
from apps.server.src.domain.prompt_sequence import (
    clear_prompt_boundary_state,
    prompt_instance_id_from_resume,
    prompt_resume_matches_next_instance,
    prompt_sequence_after_resume,
    record_prompt_boundary_state,
    runtime_prompt_sequence_seed,
)
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
from apps.server.src.services.prompt_boundary_builder import (
    PromptBoundaryBuilder,
    attach_active_module_continuation_to_envelope as _attach_active_module_continuation_to_envelope,
)
from apps.server.src.services.session_service import SessionNotFoundError
from apps.server.src.services.command_execution_gate import CommandExecutionGate
from apps.server.src.services.command_boundary_runner import CommandBoundaryRunner
from apps.server.src.services.engine_config_factory import EngineConfigFactory
from apps.server.src.services.command_processing_guard import CommandProcessingGuardService
from apps.server.src.services.command_recovery import CommandRecoveryService
from apps.server.src.services.parameter_service import DEFAULT_EXTERNAL_AI_TIMEOUT_MS
from apps.server.src.services.realtime_persistence import ViewCommitSequenceConflict

_VIEW_COMMIT_SCHEMA_VERSION = 1
_PROMPT_BOUNDARY_PUBLISH_TIMEOUT_SECONDS = 5.0
_PROMPT_BOUNDARY_PUBLISH_ATTEMPTS = 3
_EVENT_STREAM_PUBLISH_TIMEOUT_SECONDS = 1.0
_DEFAULT_RUNTIME_AI_DECISION_DELAY_MS = 1000
_PROTOCOL_IDENTITY_FIELD_NAMES = (
    "legacy_player_id",
    "seat_index",
    "turn_order_index",
    "player_label",
    "public_player_id",
    "seat_id",
    "viewer_id",
)


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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
    prompt_instance_id: int = 0
    batch_id: str = ""
    provider: str = "human"
    batch_responses_by_player_id: dict[int, dict[str, Any]] = field(default_factory=dict)
    batch_responses_by_public_player_id: dict[str, dict[str, Any]] = field(default_factory=dict)


class RuntimeDecisionResumeMismatch(ValueError):
    pass


@dataclass(slots=True)
class _RuntimeTransitionContext:
    session: Any
    resolved: dict[str, Any]
    runtime: dict[str, Any]
    runner_kind: str
    checkpoint_schema_version: int
    policy: Any
    config: Any
    state: Any
    engine: Any
    runtime_recovery_checkpoint: dict | None
    base_commit_seq: int


_COMMAND_BOUNDARY_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "refused",
        "rejected",
        "stale",
        "success",
        "unavailable",
        "waiting_input",
    }
)


def _is_command_boundary_terminal_status(status: object) -> bool:
    return str(status or "") in _COMMAND_BOUNDARY_TERMINAL_STATUSES


def _normalize_decision_choice_payload(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _batch_response_choice_payload(response: dict[str, Any]) -> dict:
    choice_payload = response.get("choice_payload")
    if not isinstance(choice_payload, dict):
        decision = response.get("decision")
        if isinstance(decision, dict):
            choice_payload = decision.get("choice_payload")
    return _normalize_decision_choice_payload(choice_payload)


def _batch_responses_by_public_player_id(
    explicit_public_responses: object,
    responses_by_player_id: dict[int, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    responses: dict[str, dict[str, Any]] = {}
    if isinstance(explicit_public_responses, dict):
        for raw_public_player_id, raw_response in explicit_public_responses.items():
            public_player_id = str(raw_public_player_id or "").strip()
            if public_player_id and isinstance(raw_response, dict):
                responses[public_player_id] = dict(raw_response)
    for response in responses_by_player_id.values():
        public_player_id = str(response.get("public_player_id") or "").strip()
        if public_player_id:
            responses.setdefault(public_player_id, dict(response))
    return responses


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


def _runtime_prompt_external_player_id(prompt: dict, payload: dict) -> int | None:
    raw_player_id = _optional_int(prompt.get("player_id"))
    pending_player_id = _optional_int(payload.get("pending_prompt_player_id"))
    player_count = len([item for item in payload.get("players") or [] if isinstance(item, dict)])
    if raw_player_id is None:
        return pending_player_id
    if pending_player_id is not None and raw_player_id == pending_player_id:
        return raw_player_id
    if pending_player_id is not None and raw_player_id + 1 == pending_player_id:
        return pending_player_id
    if 0 <= raw_player_id < player_count:
        return raw_player_id + 1
    return raw_player_id


def _runtime_continuation_debug_fields(payload: dict | None, decision_resume: object | None = None) -> dict[str, object]:
    payload = dict(payload or {})
    active_prompt = payload.get("runtime_active_prompt")
    active_prompt = dict(active_prompt) if isinstance(active_prompt, dict) else {}
    active_batch = payload.get("runtime_active_prompt_batch")
    active_batch = dict(active_batch) if isinstance(active_batch, dict) else {}
    active_prompt_internal_player_id = _optional_int(active_prompt.get("player_id"))
    active_prompt_external_player_id = _runtime_prompt_external_player_id(active_prompt, payload) if active_prompt else None
    candidates: dict[str, object] = {
        "waiting_prompt_request_id": payload.get("pending_prompt_request_id"),
        "waiting_prompt_type": payload.get("pending_prompt_type"),
        "waiting_prompt_player_id": payload.get("pending_prompt_player_id"),
        "waiting_prompt_instance_id": payload.get("pending_prompt_instance_id"),
        "prompt_sequence": payload.get("prompt_sequence"),
        "runtime_active_prompt_request_id": active_prompt.get("request_id"),
        "runtime_active_prompt_request_type": active_prompt.get("request_type"),
        "runtime_active_prompt_player_id": active_prompt_external_player_id,
        "runtime_active_prompt_internal_player_id": active_prompt_internal_player_id,
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
                "decision_resume_prompt_instance_id": getattr(decision_resume, "prompt_instance_id", None),
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


def _sync_state_prompt_request_id(state: object | None, prompt_payload: dict | None) -> None:
    if state is None or not isinstance(prompt_payload, dict):
        return
    request_id = str(prompt_payload.get("request_id") or "").strip()
    if not request_id:
        return
    if hasattr(state, "pending_prompt_request_id"):
        state.pending_prompt_request_id = request_id
    prompt_instance_id = _optional_int(prompt_payload.get("prompt_instance_id"))
    active_prompt = getattr(state, "runtime_active_prompt", None)
    if active_prompt is not None and (
        prompt_instance_id is None
        or int(getattr(active_prompt, "prompt_instance_id", 0) or 0) == prompt_instance_id
    ):
        active_prompt.request_id = request_id
    active_batch = getattr(state, "runtime_active_prompt_batch", None)
    prompts_by_player_id = getattr(active_batch, "prompts_by_player_id", None) if active_batch is not None else None
    if isinstance(prompts_by_player_id, dict):
        for continuation in prompts_by_player_id.values():
            if prompt_instance_id is not None and int(getattr(continuation, "prompt_instance_id", 0) or 0) != prompt_instance_id:
                continue
            continuation.request_id = request_id


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


def _runtime_frame_type_from_frame_id(frame_id: object) -> str:
    text = str(frame_id or "")
    if text.startswith("round:"):
        return "round"
    if text.startswith("turn:"):
        return "turn"
    if text.startswith("seq:"):
        return "sequence"
    if text.startswith("simul:"):
        return "simultaneous"
    return ""


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
        runtime_ai_decision_delay_ms: int = _DEFAULT_RUNTIME_AI_DECISION_DELAY_MS,
        runtime_engine_workers: int | None = None,
        runtime_executor: concurrent.futures.Executor | None = None,
    ) -> None:
        self._session_service = session_service
        self._stream_service = stream_service
        self._prompt_service = prompt_service
        self._config_factory = config_factory or EngineConfigFactory()
        self._decision_client_factory = decision_client_factory or _ServerDecisionClientFactory()
        self._runtime_tasks: dict[str, asyncio.Task] = {}
        self._command_execution_gate = CommandExecutionGate(
            runtime_task_provider=lambda session_id: self._runtime_tasks.get(session_id),
        )
        self._watchdogs: dict[str, asyncio.Task] = {}
        self._status: dict[str, dict] = {}
        self._last_activity_ms: dict[str, int] = {}
        self._fallback_history: dict[str, list[dict]] = {}
        self._watchdog_timeout_ms = int(watchdog_timeout_ms)
        self._session_completed_callbacks: list = []
        self._runtime_state_store = runtime_state_store
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._command_recovery = CommandRecoveryService(
            command_store=command_store,
            checkpoint_provider=lambda session_id: self.recovery_checkpoint(session_id),
        )
        self._command_processing_guard_service = CommandProcessingGuardService(
            command_store=command_store,
            command_recovery=self._command_recovery,
            prompt_lifecycle_provider=lambda session_id, command: self._prompt_lifecycle_for_command(session_id, command),
            now_ms=self._now_ms,
        )
        self._runtime_ai_decision_delay_ms = max(0, int(runtime_ai_decision_delay_ms))
        self._runtime_engine_workers = self._resolve_runtime_engine_workers(runtime_engine_workers)
        self._runtime_executor = runtime_executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=self._runtime_engine_workers,
            thread_name_prefix="mrn-runtime",
        )
        self._worker_id = f"runtime_{uuid.uuid4().hex[:12]}"
        self._lease_ttl_ms = max(5000, self._watchdog_timeout_ms * 2)
        self._held_runtime_leases: set[str] = set()
        self._runtime_lease_tracking_lock = threading.Lock()
        self._initialize_recovery_state()

    @staticmethod
    def _resolve_runtime_engine_workers(value: int | None) -> int:
        if value is None:
            raw = os.getenv("MRN_RUNTIME_ENGINE_WORKERS", "").strip()
            if raw:
                try:
                    value = int(raw)
                except ValueError:
                    value = None
        if value is None:
            value = max(1, min(8, os.cpu_count() or 1))
        return max(1, int(value))

    def _resolve_ai_decision_delay_ms(self, runtime: dict[str, Any] | None) -> int:
        if isinstance(runtime, dict) and "ai_decision_delay_ms" in runtime:
            return max(0, int(runtime.get("ai_decision_delay_ms") or 0))
        return self._runtime_ai_decision_delay_ms

    async def _run_in_runtime_executor(self, func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._runtime_executor,
            functools.partial(func, *args, **kwargs),
        )

    def add_session_completed_callback(self, callback) -> None:
        if callback is None:
            return
        self._session_completed_callbacks.append(callback)

    @property
    def command_recovery_service(self) -> CommandRecoveryService:
        return self._command_recovery

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
        existing = self._runtime_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        if self._command_processing_active(session_id):
            self._status[session_id] = {
                "status": "running_elsewhere",
                "reason": "command_processing_already_active",
                "worker_id": self._worker_id,
            }
            self._persist_runtime_state(session_id)
            log_event(
                "runtime_start_skipped_command_processing_active",
                session_id=session_id,
                worker_id=self._worker_id,
            )
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
        return self._command_recovery.has_unprocessed_runtime_commands(session_id, consumer_name=consumer_name)

    @staticmethod
    def _checkpoint_waiting_prompt_request_ids(checkpoint: dict) -> set[str]:
        return CommandRecoveryService.checkpoint_waiting_prompt_request_ids(checkpoint)

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
        return self._command_recovery.pending_resume_command(session_id, consumer_name=consumer_name)

    def _command_for_seq(self, session_id: str, command_seq: int) -> dict | None:
        return self._command_recovery.command_for_seq(session_id, command_seq)

    def _matching_resume_command_for_seq(
        self,
        session_id: str,
        command_seq: int,
        *,
        include_resolved: bool = False,
    ) -> dict | None:
        return self._command_recovery.matching_resume_command_for_seq(
            session_id,
            command_seq,
            include_resolved=include_resolved,
        )

    def has_pending_resume_command(self, session_id: str, consumer_name: str = "runtime_wakeup") -> bool:
        return self._command_recovery.has_pending_resume_command(session_id, consumer_name=consumer_name)

    def _load_command_consumer_offset(self, session_id: str, consumer_name: str) -> int | None:
        return self._command_recovery.load_command_consumer_offset(session_id, consumer_name)

    def _command_processing_guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        return self._command_processing_guard_service.guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage=stage,
        )

    def _begin_command_processing(self, session_id: str) -> bool:
        return self._command_execution_gate.begin(session_id)

    def _command_processing_active(self, session_id: str) -> bool:
        return self._command_execution_gate.active(session_id)

    def _end_command_processing(self, session_id: str) -> None:
        self._command_execution_gate.end(session_id)

    def _runtime_task_processing_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        return self._command_execution_gate.runtime_task_guard(
            session_id=session_id,
            command_seq=command_seq,
            consumer_name=consumer_name,
            stage=stage,
        )

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
        if session is not None and session.status == SessionStatus.IN_PROGRESS and self._command_processing_active(session_id):
            base = dict(base)
            base["status"] = "running_elsewhere"
            base["watchdog_state"] = "running"
            base["reason"] = "command_processing_active"
            base["worker_id"] = self._worker_id
            base["last_activity_ms"] = self._last_activity_ms.get(session_id, base.get("last_activity_ms"))
            base["recent_fallbacks"] = self._recent_fallbacks(session_id)
            if recovery.get("available"):
                base["recovery_checkpoint"] = recovery
            return base
        if session is not None and session.status == SessionStatus.IN_PROGRESS and base.get("status") == "rejected":
            base = dict(base)
            base["recent_fallbacks"] = self._recent_fallbacks(session_id)
            if recovery.get("available"):
                base["recovery_checkpoint"] = recovery
            return base
        if session is not None and session.status == SessionStatus.IN_PROGRESS and checkpoint_waiting_input:
            base = self._mark_checkpoint_waiting_input(session_id, base=base, reason="checkpoint_waiting_input")
        elif (
            session is not None
            and session.status == SessionStatus.IN_PROGRESS
            and base.get("status") == "waiting_input"
            and recovery.get("reason") != "game_state_store_unavailable"
        ):
            base["status"] = "recovery_required"
            base["watchdog_state"] = "recovery_required"
            base["reason"] = "stale_waiting_input_checkpoint"
            self._status[session_id] = dict(base)
            self._persist_runtime_state(session_id)
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
        current = dict(base or self._load_runtime_state(session_id))
        if current.get("status") == "rejected":
            return current
        status_payload = {
            key: value
            for key, value in current.items()
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
        for key in (
            "legacy_request_id",
            "public_request_id",
            "public_prompt_instance_id",
            "legacy_player_id",
            "public_player_id",
            "seat_id",
            "viewer_id",
        ):
            value = prompt_payload.get(key)
            if value is not None and str(value).strip():
                record[key] = value
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

    def runtime_task_processing_guard(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        stage: str,
    ) -> dict | None:
        return self._runtime_task_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage=stage,
        )

    def begin_command_processing(self, session_id: str) -> bool:
        return self._begin_command_processing(session_id)

    def end_command_processing(self, session_id: str) -> None:
        self._end_command_processing(session_id)

    def command_processing_guard(
        self,
        *,
        session_id: str,
        consumer_name: str,
        command_seq: int,
        stage: str,
    ) -> dict | None:
        return self._command_processing_guard(
            session_id=session_id,
            consumer_name=consumer_name,
            command_seq=command_seq,
            stage=stage,
        )

    def acquire_runtime_lease(self, session_id: str) -> bool:
        return self._acquire_runtime_lease(session_id)

    def runtime_lease_owner(self, session_id: str) -> str | None:
        return self._runtime_state_store.lease_owner(session_id) if self._runtime_state_store is not None else None

    def release_runtime_lease(self, session_id: str) -> bool:
        return self._release_runtime_lease(session_id)

    def start_runtime_lease_renewer(
        self,
        *,
        session_id: str,
        reason: str,
        command_seq: int | None = None,
        consumer_name: str | None = None,
    ) -> object | None:
        return self._start_runtime_lease_renewer(
            session_id,
            reason=reason,
            command_seq=command_seq,
            consumer_name=consumer_name,
        )

    def stop_runtime_lease_renewer(self, handle: object | None) -> None:
        self._stop_runtime_lease_renewer(handle)

    def mark_command_processing_started(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
    ) -> None:
        now_ms = self._now_ms()
        self._mark_command_state(
            session_id,
            command_seq,
            "processing",
            reason="runtime_lease_acquired",
            server_time_ms=now_ms,
            consumer_name=consumer_name,
            worker_id=self._worker_id,
        )
        self._last_activity_ms[session_id] = now_ms
        self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
        self._persist_runtime_state(session_id)

    async def run_command_boundary(
        self,
        *,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        consumer_name: str,
        command_seq: int,
    ) -> dict:
        loop = asyncio.get_running_loop()
        return await self._run_in_runtime_executor(
            self._run_engine_transition_loop_sync,
            loop,
            session_id,
            seed,
            policy_mode,
            first_command_consumer_name=consumer_name,
            first_command_seq=command_seq,
        )

    def record_command_process_timing(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        result: dict,
        process_started: float,
        pre_executor_ms: int,
        executor_wall_ms: int,
    ) -> None:
        status = str(result.get("status", ""))
        total_ms = _duration_ms(process_started)
        engine_loop_total_ms = result.get("engine_loop_total_ms")
        executor_overhead_ms = None
        if isinstance(engine_loop_total_ms, int):
            executor_overhead_ms = max(0, executor_wall_ms - engine_loop_total_ms)
        log_event(
            "runtime_command_process_timing",
            session_id=session_id,
            command_seq=command_seq,
            consumer_name=consumer_name,
            result_status=status,
            reason=result.get("reason"),
            transitions=result.get("transitions"),
            module_transition_count=result.get("module_transition_count"),
            redis_commit_count=result.get("redis_commit_count"),
            view_commit_count=result.get("view_commit_count"),
            internal_redis_commit_attempt_count=result.get("internal_redis_commit_attempt_count"),
            internal_view_commit_attempt_count=result.get("internal_view_commit_attempt_count"),
            internal_state_stage_count=result.get("internal_state_stage_count"),
            terminal_status=result.get("terminal_status") or status,
            terminal_boundary_reason=result.get("terminal_boundary_reason") or result.get("reason"),
            duplicate_request_count=result.get("duplicate_request_count", 0),
            deduped_request_id=result.get("deduped_request_id"),
            busy_rejection_count=result.get("busy_rejection_count", 0),
            idempotency_hit=bool(result.get("idempotency_hit", False)),
            command_boundary_finalization_ms=result.get("command_boundary_finalization_ms"),
            deferred_commit_copy_ms=result.get("deferred_commit_copy_ms"),
            authoritative_commit_ms=result.get("authoritative_commit_ms"),
            view_commit_emit_ms=result.get("view_commit_emit_ms"),
            prompt_materialize_ms=result.get("prompt_materialize_ms"),
            pre_executor_ms=pre_executor_ms,
            executor_wall_ms=executor_wall_ms,
            engine_loop_total_ms=engine_loop_total_ms,
            engine_prepare_ms=result.get("engine_prepare_ms"),
            engine_transition_loop_ms=result.get("engine_transition_loop_ms"),
            executor_overhead_ms=executor_overhead_ms,
            total_ms=total_ms,
        )

    async def apply_command_process_result(self, *, session_id: str, result: dict) -> None:
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
        elif status == "rejected":
            persisted_status = self._load_runtime_state(session_id)
            status_payload = dict(persisted_status) if isinstance(persisted_status, dict) else {}
            status_payload.update(result)
            status_payload["status"] = "rejected"
            status_payload["watchdog_state"] = "rejected"
            self._status[session_id] = status_payload
        else:
            self._status[session_id] = {"status": "idle", "last_transition": result}
        self._touch_activity(session_id)
        self._persist_runtime_state(session_id)

    async def handle_command_commit_conflict(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        exc: ViewCommitSequenceConflict,
    ) -> dict:
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

    def handle_command_failure(self, *, session_id: str, exc: Exception) -> None:
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

    async def _run_engine_async(
        self,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        try:
            result = await self._run_in_runtime_executor(
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
        loop_started = time.perf_counter()
        if first_command_seq is not None and self._game_state_store is not None:
            return self._run_engine_command_boundary_loop_sync(
                loop,
                session_id,
                seed,
                policy_mode,
                max_transitions=max_transitions,
                first_command_consumer_name=first_command_consumer_name,
                first_command_seq=first_command_seq,
            )
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
                return {**last_step, "transitions": transitions, "engine_loop_total_ms": _duration_ms(loop_started)}
            if self._prompt_service is not None and self._prompt_service.has_pending_for_session(session_id):
                current = dict(self._status.get(session_id, {"status": "running"}))
                current["status"] = "waiting_input"
                current["watchdog_state"] = "waiting_input"
                self._status[session_id] = current
                self._persist_runtime_state(session_id)
                return {**last_step, "status": "waiting_input", "transitions": transitions, "engine_loop_total_ms": _duration_ms(loop_started)}
        return {**last_step, "transitions": transitions, "engine_loop_total_ms": _duration_ms(loop_started)}

    def _prepare_runtime_transition_context_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        *,
        publish_external_side_effects: bool,
        game_state_store_override: object | None = None,
    ) -> _RuntimeTransitionContext:
        game_state_store = game_state_store_override if game_state_store_override is not None else self._game_state_store
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
        human_seats = [
            max(0, int(seat.seat) - 1)
            for seat in session.seats
            if seat.seat_type == SeatType.HUMAN
        ]
        if loop is not None and self._stream_service is not None:
            ai_decision_delay_ms = self._resolve_ai_decision_delay_ms(runtime)
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
        state = self._hydrate_engine_state(
            session_id,
            config,
            GameState,
            runner_kind,
            game_state_store_override=game_state_store,
        )
        runtime_recovery_checkpoint: dict | None = None
        if game_state_store is not None and callable(getattr(game_state_store, "load_checkpoint", None)):
            loaded_checkpoint = game_state_store.load_checkpoint(session_id)
            if isinstance(loaded_checkpoint, dict):
                runtime_recovery_checkpoint = loaded_checkpoint
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
                identity_fields_for_player=lambda player_id: self._session_service.protocol_identity_fields(
                    session_id, player_id
                ),
            )
            if publish_external_side_effects and loop is not None and self._stream_service is not None
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
        if state is not None:
            self._apply_runner_kind(state, runner_kind, checkpoint_schema_version)
            state = engine.prepare_run(initial_state=state)
        return _RuntimeTransitionContext(
            session=session,
            resolved=resolved,
            runtime=runtime,
            runner_kind=runner_kind,
            checkpoint_schema_version=checkpoint_schema_version,
            policy=policy,
            config=config,
            state=state,
            engine=engine,
            runtime_recovery_checkpoint=runtime_recovery_checkpoint,
            base_commit_seq=self._latest_view_commit_seq(
                session_id,
                game_state_store_override=game_state_store,
            ),
        )

    def _run_engine_command_boundary_loop_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        *,
        max_transitions: int | None = None,
        first_command_consumer_name: str | None,
        first_command_seq: int,
    ) -> dict:
        return CommandBoundaryRunner(
            game_state_store=self._game_state_store,
            latest_view_commit_seq=self._latest_view_commit_seq,
            prepare_transition_context=self._prepare_runtime_transition_context_sync,
            run_transition_once=self._run_engine_transition_once_sync,
            emit_latest_view_commit=self._emit_latest_view_commit_sync,
            materialize_prompt_boundaries=self._materialize_prompt_boundaries_from_checkpoint_sync,
            commit_guard=self._command_boundary_commit_guard,
        ).run(
            loop,
            session_id,
            seed,
            policy_mode,
            max_transitions=max_transitions,
            first_command_consumer_name=first_command_consumer_name,
            first_command_seq=first_command_seq,
        )

    def _command_boundary_commit_guard(self, session_id: str) -> dict[str, Any] | None:
        lease_owner_before_write = self._runtime_lease_owner(session_id)
        lease_check_required = self._runtime_state_store is not None and (
            self._runtime_lease_held_by_this_process(session_id)
            or lease_owner_before_write is not None
        )
        if not lease_check_required or lease_owner_before_write == self._worker_id:
            return None
        return {
            "reason": "runtime_lease_lost_before_commit",
            "lease_owner": lease_owner_before_write,
            "worker_id": self._worker_id,
        }

    @staticmethod
    def _command_module_trace_entry(index: int, step: dict) -> dict:
        entry = {
            "index": int(index),
            "status": str(step.get("status") or ""),
            "reason": str(step.get("reason") or ""),
        }
        for key in ("runner_kind", "module_type", "module_id", "frame_id", "module_cursor", "request_id", "request_type", "player_id"):
            value = step.get(key)
            if value not in (None, ""):
                entry[key] = value
        runtime_module = step.get("runtime_module")
        if isinstance(runtime_module, dict):
            entry["runtime_module"] = {
                key: value
                for key, value in runtime_module.items()
                if key in {"runner_kind", "module_type", "module_id", "frame_id", "module_cursor"} and value not in (None, "")
            }
        return entry

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
            persisted = self._load_runtime_state(session.session_id)
            persisted_status = str(persisted.get("status") or "").strip()
            if persisted_status and persisted_status != "idle":
                self._status.setdefault(session.session_id, dict(persisted))
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
        return CommandRecoveryService.command_payload(command)

    @staticmethod
    def _command_payload_field(command: dict, name: str) -> str:
        return CommandRecoveryService.command_payload_field(command, name)

    @staticmethod
    def _command_is_timeout_fallback(command: dict) -> bool:
        return CommandRecoveryService.command_is_timeout_fallback(command)

    @staticmethod
    def _command_module_identity_mismatch(checkpoint: dict, command: dict) -> bool:
        return CommandRecoveryService.command_module_identity_mismatch(checkpoint, command)

    def _acquire_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_lease_held_by_this_process(session_id):
            log_event(
                "runtime_lease_reentrant_acquire_blocked",
                session_id=session_id,
                worker_id=self._worker_id,
            )
            return False
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

    def _hydrate_engine_state(
        self,
        session_id: str,
        config,
        game_state_cls,
        runner_kind: str | None = None,
        *,
        game_state_store_override: object | None = None,
    ):
        del runner_kind
        game_state_store = game_state_store_override if game_state_store_override is not None else self._game_state_store
        if game_state_store is None:
            return None
        if not callable(getattr(game_state_store, "load_checkpoint", None)) or not callable(
            getattr(game_state_store, "load_current_state", None)
        ):
            return None
        checkpoint = game_state_store.load_checkpoint(session_id)
        current_state = game_state_store.load_current_state(session_id)
        if not isinstance(checkpoint, dict) or not isinstance(current_state, dict):
            return None
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
            command_type = str(command.get("type") or "").strip()
            payload = command.get("payload")
            if not isinstance(payload, dict):
                return None
            if command_type == "batch_complete":
                return self._decision_resume_from_batch_complete_payload(session_id, payload)
            if command_type != "decision_submitted":
                return None
            decision = payload.get("decision")
            decision = decision if isinstance(decision, dict) else {}

            def _field(name: str) -> str:
                return str(payload.get(name) or decision.get(name) or "").strip()

            def _int_field(name: str) -> int:
                value = self._int_or_none(payload.get(name))
                if value is None:
                    value = self._int_or_none(decision.get(name))
                return int(value or 0)

            choice_payload = payload.get("choice_payload")
            if not isinstance(choice_payload, dict):
                choice_payload = decision.get("choice_payload")
            provider = str(payload.get("provider") or decision.get("provider") or "human").strip().lower()
            if provider not in {"human", "ai"}:
                provider = "human"
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
                prompt_instance_id=_int_field("prompt_instance_id"),
                batch_id=_field("batch_id"),
                provider=provider,
            )
        return None

    def _decision_resume_from_batch_complete_payload(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> RuntimeDecisionResume | None:
        responses = payload.get("responses_by_player_id")
        normalized: dict[int, dict[str, Any]] = {}
        if isinstance(responses, dict):
            for raw_player_id, raw_response in responses.items():
                try:
                    player_id = int(raw_player_id)
                except (TypeError, ValueError):
                    continue
                if not isinstance(raw_response, dict):
                    continue
                response = dict(raw_response)
                response.setdefault("player_id", player_id)
                response.setdefault("batch_id", str(payload.get("batch_id") or ""))
                normalized[player_id] = response
        public_response_map = payload.get("responses_by_public_player_id")
        if not normalized and isinstance(public_response_map, dict):
            for raw_public_player_id, raw_response in public_response_map.items():
                if not isinstance(raw_response, dict):
                    continue
                public_player_id = str(raw_response.get("public_player_id") or raw_public_player_id or "").strip()
                if not public_player_id:
                    continue
                try:
                    resolved_player_id = self._session_service.resolve_protocol_player_id(
                        session_id,
                        public_player_id=public_player_id,
                    )
                except SessionNotFoundError:
                    resolved_player_id = None
                if resolved_player_id is None:
                    continue
                player_id = int(resolved_player_id)
                response = dict(raw_response)
                response.setdefault("public_player_id", public_player_id)
                response.setdefault("player_id", player_id)
                response.setdefault("batch_id", str(payload.get("batch_id") or ""))
                normalized.setdefault(player_id, response)
        if not normalized:
            return None
        public_responses = _batch_responses_by_public_player_id(
            payload.get("responses_by_public_player_id"),
            normalized,
        )
        expected = [
            int(raw)
            for raw in payload.get("expected_player_ids", [])
            if self._int_or_none(raw) is not None and int(raw) in normalized
        ]
        if not expected:
            for raw_public_player_id in payload.get("expected_public_player_ids", []):
                try:
                    resolved_player_id = self._session_service.resolve_protocol_player_id(
                        session_id,
                        public_player_id=str(raw_public_player_id or "").strip(),
                    )
                except SessionNotFoundError:
                    resolved_player_id = None
                if resolved_player_id is not None and int(resolved_player_id) in normalized:
                    expected.append(int(resolved_player_id))
        primary_player_id = expected[-1] if expected else sorted(normalized)[-1]
        primary = normalized[primary_player_id]
        choice_payload = _batch_response_choice_payload(primary)
        decision = primary.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        provider = str(primary.get("provider") or decision.get("provider") or "human").strip().lower()
        if provider not in {"human", "ai"}:
            provider = "human"
        batch_id = str(primary.get("batch_id") or payload.get("batch_id") or "").strip()
        return RuntimeDecisionResume(
            request_id=str(primary.get("request_id") or ""),
            player_id=int(primary.get("player_id") or primary_player_id),
            request_type=str(primary.get("request_type") or ""),
            choice_id=str(primary.get("choice_id") or ""),
            choice_payload=_normalize_decision_choice_payload(choice_payload),
            resume_token=str(primary.get("resume_token") or ""),
            frame_id=str(primary.get("frame_id") or ""),
            module_id=str(primary.get("module_id") or ""),
            module_type=str(primary.get("module_type") or ""),
            module_cursor=str(primary.get("module_cursor") or ""),
            prompt_instance_id=int(self._int_or_none(primary.get("prompt_instance_id")) or 0),
            batch_id=batch_id,
            provider=provider,
            batch_responses_by_player_id=normalized,
            batch_responses_by_public_player_id=public_responses,
        )

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

    def _apply_collected_batch_responses_to_state(self, state, resume: RuntimeDecisionResume) -> None:  # noqa: ANN001
        if not resume.batch_responses_by_player_id:
            return
        from runtime_modules.prompts import PromptApi

        batch = getattr(state, "runtime_active_prompt_batch", None)
        if batch is None:
            return
        if resume.batch_id and str(getattr(batch, "batch_id", "") or "") != resume.batch_id:
            raise ValueError("batch id mismatch")
        prompt_api = PromptApi()
        resume_internal_player_id = max(0, int(resume.player_id) - 1)
        for external_player_id, response in sorted(resume.batch_responses_by_player_id.items()):
            internal_player_id = max(0, int(external_player_id) - 1)
            if internal_player_id == resume_internal_player_id:
                continue
            if internal_player_id in getattr(batch, "responses_by_player_id", {}):
                continue
            prompt_api.record_batch_response(
                batch,
                player_id=internal_player_id,
                request_id=str(response.get("request_id") or ""),
                resume_token=str(response.get("resume_token") or ""),
                choice_id=str(response.get("choice_id") or ""),
                response={"choice_payload": _batch_response_choice_payload(response)},
            )

    def _mark_command_state(
        self,
        session_id: str,
        command_seq: int | None,
        status: str,
        *,
        reason: str | None = None,
        server_time_ms: int | None = None,
        **extra: Any,
    ) -> None:
        self._command_processing_guard_service.mark_command_state(
            session_id,
            command_seq,
            status,
            reason=reason,
            server_time_ms=server_time_ms,
            **extra,
        )

    def _save_rejected_command_offset(
        self,
        command_consumer_name: str | None,
        session_id: str,
        command_seq: int | None,
        *,
        reason: str = "rejected",
        status: str = "rejected",
    ) -> None:
        self._command_processing_guard_service.save_rejected_command_offset(
            command_consumer_name,
            session_id,
            command_seq,
            reason=reason,
            status=status,
        )

    def _stale_command_terminal_state(self, session_id: str, command: dict | None) -> str:
        return self._command_processing_guard_service.stale_command_terminal_state(session_id, command)

    def _stale_command_terminal_reason(
        self,
        session_id: str,
        command: dict | None,
        *,
        default_reason: str,
    ) -> str:
        return self._command_processing_guard_service.stale_command_terminal_reason(
            session_id,
            command,
            default_reason=default_reason,
        )

    def _prompt_lifecycle_for_command(self, session_id: str, command: dict | None) -> dict | None:
        if command is None or self._prompt_service is None:
            return None
        request_id = self._command_payload_field(command, "request_id")
        if not request_id:
            return None
        get_lifecycle = getattr(self._prompt_service, "get_prompt_lifecycle", None)
        if not callable(get_lifecycle):
            return None
        try:
            lifecycle = get_lifecycle(request_id, session_id=session_id)
        except Exception as exc:
            log_event(
                "runtime_prompt_lifecycle_lookup_failed",
                session_id=session_id,
                request_id=request_id,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return None
        return dict(lifecycle) if isinstance(lifecycle, dict) else None

    def _mark_runtime_command_rejected(
        self,
        session_id: str,
        *,
        reason: str,
        command_consumer_name: str | None,
        command_seq: int | None,
        decision_resume: RuntimeDecisionResume | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "status": "rejected",
            "watchdog_state": "rejected",
            "reason": reason,
            "processed_command_seq": command_seq,
            "processed_command_consumer": command_consumer_name,
            "runner_kind": "module",
        }
        if decision_resume is not None:
            payload.update(
                {
                    "request_id": decision_resume.request_id,
                    "player_id": decision_resume.player_id,
                    "choice_id": decision_resume.choice_id,
                    "request_type": decision_resume.request_type,
                    "module_type": decision_resume.module_type,
                    "module_id": decision_resume.module_id,
                    "frame_id": decision_resume.frame_id,
                    "module_cursor": decision_resume.module_cursor,
                }
            )
        self._status[session_id] = dict(payload)
        self._persist_runtime_state(session_id)
        return payload

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
        publish_external_side_effects: bool = True,
        transition_context: _RuntimeTransitionContext | None = None,
        game_state_store_override: object | None = None,
    ) -> dict:
        game_state_store = game_state_store_override if game_state_store_override is not None else self._game_state_store
        self._ensure_engine_import_path()
        from engine import GameEngine
        from policy.factory import PolicyFactory
        from state import GameState

        transition_started = time.perf_counter()
        phase_started = transition_started
        phase_timings: dict[str, int] = {}

        def _mark_phase(name: str) -> None:
            nonlocal phase_started
            phase_timings[f"{name}_ms"] = _duration_ms(phase_started)
            phase_started = time.perf_counter()

        prepared_state = transition_context is not None
        if transition_context is None:
            session = self._session_service.get_session(session_id)
            resolved = dict(session.resolved_parameters or {})
            runtime = dict(resolved.get("runtime", {}))
            runner_kind = resolve_runtime_runner_kind(runtime)
            checkpoint_schema_version = runtime_checkpoint_schema_version_for_runner(runner_kind)
            selected_policy_mode = policy_mode or runtime.get("policy_mode") or "heuristic_v3_engine"
            ai_policy = PolicyFactory.create_runtime_policy(
                policy_mode=selected_policy_mode,
                lap_policy_mode=selected_policy_mode,
            )
            policy = ai_policy
            base_commit_seq = self._latest_view_commit_seq(
                session_id,
                game_state_store_override=game_state_store,
            )
            human_seats = [
                max(0, int(seat.seat) - 1)
                for seat in session.seats
                if seat.seat_type == SeatType.HUMAN
            ]
            if loop is not None and self._stream_service is not None:
                ai_decision_delay_ms = self._resolve_ai_decision_delay_ms(runtime)
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
            state = self._hydrate_engine_state(
                session_id,
                config,
                GameState,
                runner_kind,
                game_state_store_override=game_state_store,
            )
            runtime_recovery_checkpoint: dict | None = None
            if game_state_store is not None and callable(getattr(game_state_store, "load_checkpoint", None)):
                loaded_checkpoint = game_state_store.load_checkpoint(session_id)
                if isinstance(loaded_checkpoint, dict):
                    runtime_recovery_checkpoint = loaded_checkpoint
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
                    identity_fields_for_player=lambda player_id: self._session_service.protocol_identity_fields(
                        session_id, player_id
                    ),
                )
                if publish_external_side_effects and loop is not None and self._stream_service is not None
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
        else:
            session = transition_context.session
            runtime = transition_context.runtime
            runner_kind = transition_context.runner_kind
            checkpoint_schema_version = transition_context.checkpoint_schema_version
            policy = transition_context.policy
            config = transition_context.config
            state = transition_context.state
            engine = transition_context.engine
            runtime_recovery_checkpoint = transition_context.runtime_recovery_checkpoint
            base_commit_seq = transition_context.base_commit_seq
        decision_resume = None
        if state is None:
            if require_checkpoint:
                return {"status": "unavailable", "reason": "checkpoint_missing"}
        if state is not None:
            self._apply_runner_kind(state, runner_kind, checkpoint_schema_version)
            decision_resume = self._decision_resume_from_command(session_id, command_seq)
            if decision_resume is not None:
                self._apply_collected_batch_responses_to_state(state, decision_resume)
            if callable(getattr(policy, "set_prompt_sequence", None)):
                policy.set_prompt_sequence(
                    runtime_prompt_sequence_seed(state, runtime_recovery_checkpoint, decision_resume)
                )
            if decision_resume is not None:
                try:
                    self._validate_decision_resume_against_checkpoint(state, decision_resume)
                except ValueError as exc:
                    self._save_rejected_command_offset(
                        command_consumer_name,
                        session_id,
                        command_seq,
                        reason=str(exc),
                    )
                    return self._mark_runtime_command_rejected(
                        session_id,
                        reason=str(exc),
                        command_consumer_name=command_consumer_name,
                        command_seq=command_seq,
                        decision_resume=decision_resume,
                    )
                if callable(getattr(policy, "set_decision_resume", None)):
                    policy.set_decision_resume(decision_resume)
        _mark_phase("hydrate_and_prepare_policy")
        try:
            prompt_boundary_payload: dict | None = None
            if state is None:
                state = engine.create_initial_state()
                self._apply_runner_kind(state, runner_kind, checkpoint_schema_version)
                state = engine.prepare_run(initial_state=state)
            elif not prepared_state:
                state = engine.prepare_run(initial_state=state)
            if decision_resume is None:
                step = engine.run_next_transition(state)
            else:
                step = engine.run_next_transition(state, decision_resume=decision_resume)
        except (RuntimeDecisionResumeMismatch, PromptFingerprintMismatch) as exc:
            self._save_rejected_command_offset(
                command_consumer_name,
                session_id,
                command_seq,
                reason=str(exc),
            )
            return self._mark_runtime_command_rejected(
                session_id,
                reason=str(exc),
                command_consumer_name=command_consumer_name,
                command_seq=command_seq,
                decision_resume=decision_resume,
            )
        except PromptRequired as exc:
            state = state or getattr(engine, "_last_prepared_state", None)
            if state is None:
                raise
            prompt_boundary_payload = dict(exc.prompt)
            record_prompt_boundary_state(state, exc.prompt)
            step = {
                "status": "waiting_input",
                "reason": "prompt_required",
                "request_id": exc.prompt.get("request_id"),
                "request_type": exc.prompt.get("request_type"),
                "player_id": exc.prompt.get("player_id"),
            }
        else:
            prompt_boundary_payload = None
            clear_prompt_boundary_state(state)
            _clear_resolved_runtime_prompt_continuation(state, step)
        if transition_context is not None:
            transition_context.state = state
        _mark_phase("engine_transition")
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
        defer_runtime_status_persist = (
            not publish_external_side_effects
            and getattr(game_state_store, "defer_authoritative_transition_commit", False)
            and not _is_command_boundary_terminal_status(step.get("status"))
        )
        if not defer_runtime_status_persist:
            self._persist_runtime_state(session_id)
        _mark_phase("status_stage" if defer_runtime_status_persist else "status_persist")
        if game_state_store is not None:
            payload = state.to_checkpoint_payload()
            validate_checkpoint_payload(payload)
            _mark_phase("checkpoint_payload")
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
            if publish_external_side_effects and latest_event_type == "prompt_required" and prompt_boundary_payload:
                prompt_publish_payload = self._materialize_prompt_boundary_sync(
                    loop,
                    session_id,
                    prompt_boundary_payload,
                    state=state,
                    publish=False,
                )
                if prompt_publish_payload is not None:
                    _sync_state_prompt_request_id(state, prompt_publish_payload)
                    payload = state.to_checkpoint_payload()
                    validate_checkpoint_payload(payload)
                    runtime_active_prompt = payload.get("runtime_active_prompt")
                    runtime_active_prompt = runtime_active_prompt if isinstance(runtime_active_prompt, dict) else {}
                    runtime_active_prompt_batch = payload.get("runtime_active_prompt_batch")
                    runtime_active_prompt_batch = runtime_active_prompt_batch if isinstance(runtime_active_prompt_batch, dict) else {}
            _mark_phase("prompt_materialize")
            commit_seq = base_commit_seq + 1
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
            stage_internal_transition = getattr(game_state_store, "stage_internal_transition", None)
            if (
                not publish_external_side_effects
                and getattr(game_state_store, "defer_authoritative_transition_commit", False)
                and not _is_command_boundary_terminal_status(step.get("status"))
                and callable(stage_internal_transition)
            ):
                stage_internal_transition(session_id, current_state=payload)
                _mark_phase("internal_state_stage")
                log_event(
                    "runtime_transition_phase_timing",
                    session_id=session_id,
                    processed_command_seq=processed_command_seq,
                    processed_command_consumer=processed_command_consumer,
                    base_commit_seq=base_commit_seq,
                    commit_seq=commit_seq,
                    source_event_seq=None,
                    result_status=step.get("status"),
                    reason=step.get("reason"),
                    request_id=step.get("request_id"),
                    request_type=step.get("request_type"),
                    player_id=step.get("player_id"),
                    total_ms=_duration_ms(transition_started),
                    command_boundary_staged=True,
                    **phase_timings,
                    **module_debug_fields,
                    **continuation_debug_fields,
                )
                return {
                    **step,
                    "runner_kind": effective_runner_kind,
                    **module_debug_fields,
                    **continuation_debug_fields,
                }
            previous_source_event_seq = self._latest_committed_source_event_seq(
                session_id,
                game_state_store_override=game_state_store,
            )
            latest_stream_seq = self._latest_stream_seq_sync(loop, session_id)
            source_messages = self._source_history_sync(loop, session_id, latest_stream_seq)
            _mark_phase("source_history")
            snapshot_pulse_specs = _snapshot_pulse_specs_from_source_messages(
                source_messages,
                after_seq=previous_source_event_seq,
            )
            _mark_phase("snapshot_pulse_plan")
            source_event_seq = latest_stream_seq
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
                "runtime_active_prompt_external_player_id": _runtime_prompt_external_player_id(runtime_active_prompt, payload)
                if runtime_active_prompt
                else None,
                "runtime_active_prompt_internal_player_id": _optional_int(runtime_active_prompt.get("player_id"))
                if runtime_active_prompt
                else None,
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
                command_consumer_name=processed_command_consumer,
                command_seq=processed_command_seq,
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
            _mark_phase("runtime_checkpoint_build")
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
            _mark_phase("view_commit_build")
            public_view_state = {}
            spectator_commit = view_commits.get("spectator") or view_commits.get("public") or {}
            if isinstance(spectator_commit, dict) and isinstance(spectator_commit.get("view_state"), dict):
                public_view_state = dict(spectator_commit["view_state"])
            latest_commit_seq_before_write = self._latest_view_commit_seq(
                session_id,
                game_state_store_override=game_state_store,
            )
            _mark_phase("precommit_validation")
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
            game_state_store.commit_transition(
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
            if offset_consumer_name and offset_command_seq is not None:
                self._mark_command_state(
                    session_id,
                    offset_command_seq,
                    "committed",
                    reason=str(step.get("status") or "transition_committed"),
                    server_time_ms=updated_at_ms,
                    consumer_name=offset_consumer_name,
                    commit_seq=commit_seq,
                    source_event_seq=source_event_seq,
                )
            _mark_phase("redis_commit")
            if publish_external_side_effects:
                self._emit_latest_view_commit_sync(loop, session_id)
            _mark_phase("view_commit_emit")
            if publish_external_side_effects and prompt_publish_payload:
                self._publish_prompt_boundary_sync(loop, session_id, prompt_publish_payload)
            _mark_phase("prompt_publish")
            if publish_external_side_effects:
                self._emit_snapshot_pulses_sync(loop, session_id, snapshot_pulse_specs)
            _mark_phase("snapshot_pulse_emit")
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
            _mark_phase("debug_log")
        if publish_external_side_effects and step.get("status") == "waiting_input":
            self._publish_active_module_prompt_batch_sync(loop, session_id, state)
            _mark_phase("active_prompt_batch_publish")
        if game_state_store is not None:
            log_event(
                "runtime_transition_phase_timing",
                session_id=session_id,
                processed_command_seq=processed_command_seq,
                processed_command_consumer=processed_command_consumer,
                base_commit_seq=base_commit_seq,
                commit_seq=commit_seq,
                source_event_seq=source_event_seq,
                result_status=step.get("status"),
                reason=step.get("reason"),
                request_id=step.get("request_id"),
                request_type=step.get("request_type"),
                player_id=step.get("player_id"),
                total_ms=_duration_ms(transition_started),
                **phase_timings,
                **module_debug_fields,
                **continuation_debug_fields,
            )
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

    def _latest_committed_source_event_seq(
        self,
        session_id: str,
        *,
        game_state_store_override: object | None = None,
    ) -> int:
        game_state_store = game_state_store_override if game_state_store_override is not None else self._game_state_store
        if game_state_store is None:
            return 0
        if callable(getattr(game_state_store, "load_view_commit_index", None)):
            index = game_state_store.load_view_commit_index(session_id)
            if isinstance(index, dict):
                value = self._int_or_none(index.get("latest_source_event_seq"))
                if value is not None:
                    return value
        if callable(getattr(game_state_store, "load_checkpoint", None)):
            checkpoint = game_state_store.load_checkpoint(session_id)
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

    def _latest_view_commit_seq(
        self,
        session_id: str,
        *,
        game_state_store_override: object | None = None,
    ) -> int:
        game_state_store = game_state_store_override if game_state_store_override is not None else self._game_state_store
        if game_state_store is None:
            return 0
        candidates: list[int] = []

        if callable(getattr(game_state_store, "load_checkpoint", None)):
            checkpoint = game_state_store.load_checkpoint(session_id)
            if isinstance(checkpoint, dict):
                commit_seq = self._int_or_none(checkpoint.get("latest_commit_seq"))
                if commit_seq is not None:
                    candidates.append(commit_seq)

        index: dict | None = None
        if callable(getattr(game_state_store, "load_view_commit_index", None)):
            loaded_index = game_state_store.load_view_commit_index(session_id)
            if isinstance(loaded_index, dict):
                index = loaded_index
                commit_seq = self._int_or_none(index.get("latest_commit_seq"))
                if commit_seq is not None:
                    candidates.append(commit_seq)

        if callable(getattr(game_state_store, "load_view_commit", None)):
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
                        payload = game_state_store.load_view_commit(session_id, "player", player_id=player_id)
                else:
                    payload = game_state_store.load_view_commit(session_id, label)
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
                        **self._view_commit_viewer_identity_fields(session_id, external_player_id),
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

    def _view_commit_viewer_identity_fields(self, session_id: str, external_player_id: int) -> dict[str, Any]:
        fallback = display_identity_fields(external_player_id, legacy_player_id=external_player_id)
        try:
            fields = self._session_service.protocol_identity_fields(session_id, external_player_id)
        except Exception:
            return fallback
        if not fields:
            return fallback
        return {**fallback, **fields}

    def _prompt_batch_identity_companion_fields(
        self,
        *,
        session_id: str,
        missing_player_ids: object,
        resume_tokens_by_player_id: object,
    ) -> dict[str, Any]:
        external_player_ids = [
            int(raw)
            for raw in missing_player_ids or []
            if self._int_or_none(raw) is not None
        ] if isinstance(missing_player_ids, list) else []
        if not external_player_ids:
            return {}

        identity_by_player_id = {
            player_id: self._view_commit_viewer_identity_fields(session_id, player_id)
            for player_id in external_player_ids
        }
        result: dict[str, Any] = {
            "missing_public_player_ids": [
                str(identity_by_player_id[player_id]["public_player_id"])
                for player_id in external_player_ids
                if str(identity_by_player_id[player_id].get("public_player_id") or "").strip()
            ],
            "missing_seat_ids": [
                str(identity_by_player_id[player_id]["seat_id"])
                for player_id in external_player_ids
                if str(identity_by_player_id[player_id].get("seat_id") or "").strip()
            ],
            "missing_viewer_ids": [
                str(identity_by_player_id[player_id]["viewer_id"])
                for player_id in external_player_ids
                if str(identity_by_player_id[player_id].get("viewer_id") or "").strip()
            ],
        }
        if isinstance(resume_tokens_by_player_id, dict):
            for output_key, identity_key in (
                ("resume_tokens_by_public_player_id", "public_player_id"),
                ("resume_tokens_by_seat_id", "seat_id"),
                ("resume_tokens_by_viewer_id", "viewer_id"),
            ):
                mapped: dict[str, str] = {}
                for raw_player_id, token in resume_tokens_by_player_id.items():
                    player_id = self._int_or_none(raw_player_id)
                    if player_id is None or player_id not in identity_by_player_id:
                        continue
                    identity_value = str(identity_by_player_id[player_id].get(identity_key) or "").strip()
                    token_value = str(token or "").strip()
                    if identity_value and token_value:
                        mapped[identity_value] = token_value
                if mapped:
                    result[output_key] = mapped
        return {key: value for key, value in result.items() if value not in ([], {})}

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
        player_id = self._int_or_none(payload.get("player_id"))
        if player_id is not None:
            payload.update(self._view_commit_viewer_identity_fields(session_id, player_id))
        payload.update(
            self._prompt_batch_identity_companion_fields(
                session_id=session_id,
                missing_player_ids=payload.get("missing_player_ids"),
                resume_tokens_by_player_id=payload.get("resume_tokens_by_player_id"),
            )
        )
        try:
            pending_prompt = self._prompt_service.create_prompt(session_id=session_id, prompt=payload)
            payload = dict(pending_prompt.payload)
        except ValueError as exc:
            if str(exc) not in {"duplicate_pending_request_id", "duplicate_recent_request_id"}:
                raise
            if str(exc) == "duplicate_pending_request_id":
                pending_prompt = self._prompt_service.get_pending_prompt(request_id, session_id=session_id)
                if pending_prompt is not None:
                    payload = dict(pending_prompt.payload)
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
        identity_fields = {key: payload[key] for key in _PROTOCOL_IDENTITY_FIELD_NAMES if key in payload}
        identity_fields.update(
            {
                key: payload[key]
                for key in ("legacy_request_id", "public_request_id", "public_prompt_instance_id")
                if str(payload.get(key) or "").strip()
            }
        )
        requested = build_decision_requested_payload(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            fallback_policy=str(payload.get("fallback_policy") or "required"),
            provider=str(payload.get("provider") or "human"),
            round_index=public_context.get("round_index"),
            turn_index=public_context.get("turn_index"),
            public_context=public_context,
            identity_fields=identity_fields,
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

    def _materialize_prompt_boundaries_from_checkpoint_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        checkpoint_payload: dict,
    ) -> None:
        if loop is None or self._stream_service is None or self._prompt_service is None:
            return
        for payload in self._prompt_boundary_payloads_from_checkpoint(checkpoint_payload):
            self._materialize_prompt_boundary_sync(loop, session_id, {**payload, "provider": "human"})

    def _prompt_boundary_payloads_from_checkpoint(self, checkpoint_payload: dict) -> list[dict]:
        payloads: list[dict] = []
        active_prompt = checkpoint_payload.get("runtime_active_prompt")
        if isinstance(active_prompt, dict) and str(active_prompt.get("request_id") or "").strip():
            player_id = _runtime_prompt_external_player_id(active_prompt, checkpoint_payload)
            if player_id is None:
                player_id = int(active_prompt.get("player_id") or 0)
            payloads.append(
                self._prompt_boundary_payload_from_continuation(
                    active_prompt,
                    player_id=int(player_id),
                    batch_payload=None,
                )
            )

        active_batch = checkpoint_payload.get("runtime_active_prompt_batch")
        if isinstance(active_batch, dict):
            prompts = active_batch.get("prompts_by_player_id")
            prompts = prompts if isinstance(prompts, dict) else {}
            missing_player_ids = active_batch.get("missing_player_ids")
            missing_player_ids = missing_player_ids if isinstance(missing_player_ids, list) else []
            for raw_internal_player_id in missing_player_ids:
                internal_player_id = _optional_int(raw_internal_player_id)
                if internal_player_id is None:
                    continue
                continuation = prompts.get(str(internal_player_id))
                if not isinstance(continuation, dict):
                    continuation = prompts.get(internal_player_id)
                if not isinstance(continuation, dict):
                    continue
                payloads.append(
                    self._prompt_boundary_payload_from_continuation(
                        continuation,
                        player_id=internal_player_id + 1,
                        batch_payload=active_batch,
                    )
                )
        return payloads

    @staticmethod
    def _prompt_boundary_payload_from_continuation(
        continuation: dict,
        *,
        player_id: int,
        batch_payload: dict | None,
    ) -> dict:
        public_context = dict(continuation.get("public_context") or {})
        payload = {
            "request_id": str(continuation.get("request_id") or ""),
            "request_type": str(continuation.get("request_type") or ""),
            "player_id": int(player_id),
            "prompt_instance_id": int(continuation.get("prompt_instance_id") or 0),
            "legal_choices": list(continuation.get("legal_choices") or []),
            "public_context": public_context,
            "timeout_ms": DEFAULT_HUMAN_PROMPT_TIMEOUT_MS,
            "fallback_policy": "required",
            "runner_kind": "module",
            "resume_token": str(continuation.get("resume_token") or ""),
            "frame_id": str(continuation.get("frame_id") or ""),
            "module_id": str(continuation.get("module_id") or ""),
            "module_type": str(continuation.get("module_type") or ""),
            "module_cursor": str(continuation.get("module_cursor") or ""),
            "runtime_module": {
                "runner_kind": "module",
                "frame_type": "simultaneous"
                if batch_payload
                else _runtime_frame_type_from_frame_id(continuation.get("frame_id")),
                "frame_id": str(continuation.get("frame_id") or ""),
                "module_id": str(continuation.get("module_id") or ""),
                "module_type": str(continuation.get("module_type") or ""),
                "module_cursor": str(continuation.get("module_cursor") or ""),
            },
        }
        if batch_payload:
            prompts = batch_payload.get("prompts_by_player_id")
            prompts = prompts if isinstance(prompts, dict) else {}
            missing_player_ids = [
                int(missing_player_id) + 1
                for missing_player_id in list(batch_payload.get("missing_player_ids") or [])
                if _optional_int(missing_player_id) is not None
            ]
            payload["batch_id"] = str(batch_payload.get("batch_id") or "")
            payload["missing_player_ids"] = missing_player_ids
            payload["resume_tokens_by_player_id"] = {
                str(int(internal_player_id) + 1): str(prompt.get("resume_token") or "")
                for internal_player_id, prompt in prompts.items()
                if _optional_int(internal_player_id) is not None and isinstance(prompt, dict)
            }
        return payload

    @staticmethod
    def _enrich_prompt_boundary_from_active_batch(payload: dict, state: object | None) -> None:
        def _field(source: object | None, key: str, default: object | None = None) -> object | None:
            if isinstance(source, dict):
                return source.get(key, default)
            return getattr(source, key, default)

        def _text_field(source: object | None, key: str) -> str:
            return str(_field(source, key, "") or "").strip()

        request_id = str(payload.get("request_id") or "").strip()
        payload_batch_id = str(payload.get("batch_id") or "").strip()
        effective_batch_id = payload_batch_id

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
            submitted_internal_player_id = _optional_int(payload.get("player_id"))
            if submitted_internal_player_id is not None:
                submitted_internal_player_id -= 1
            if (
                active_batch_id
                and effective_batch_id == active_batch_id
                and submitted_internal_player_id == continuation_internal_player_id
            ):
                matching_prompt = continuation
                break
        if matching_prompt is None and (not active_batch_id or effective_batch_id != active_batch_id):
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
        self._prompt_boundary_builder = PromptBoundaryBuilder(
            stable_request_id_resolver=getattr(self._gateway, "_stable_prompt_request_id", None),
            ensure_engine_import_path=RuntimeService._ensure_engine_import_path,
        )
        factory = client_factory or _ServerDecisionClientFactory()
        create_human_client_kwargs = {
            "human_seats": human_seats,
            "ai_fallback": ai_fallback,
            "gateway": self._gateway,
        }
        create_human_client = factory.create_human_client
        if "prompt_boundary_builder" in inspect.signature(create_human_client).parameters:
            create_human_client_kwargs["prompt_boundary_builder"] = self._prompt_boundary_builder
        self._human_client = create_human_client(**create_human_client_kwargs)
        if callable(getattr(self._human_client, "set_prompt_boundary_builder", None)):
            self._human_client.set_prompt_boundary_builder(self._prompt_boundary_builder)
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
        self._prompt_boundary_builder.set_prompt_sequence(value)

    def current_prompt_sequence(self) -> int:
        return int(self._prompt_boundary_builder.current_prompt_sequence())

    def _ask(self, prompt: dict, parser, fallback_fn):
        if self._human_client is not None:
            prompt = self._prompt_boundary_builder.prepare(
                prompt,
                replace_prompt_instance_id=True,
            )
        return self._gateway.resolve_human_prompt(prompt, parser, fallback_fn)

    def request(self, request):
        started = time.perf_counter()
        phase_started = started
        phase_timings: dict[str, int] = {}
        invocation = None
        call = None
        client = None
        error: BaseException | None = None

        def _mark_phase(name: str) -> None:
            nonlocal phase_started
            phase_timings[f"{name}_ms"] = _duration_ms(phase_started)
            phase_started = time.perf_counter()

        try:
            invocation = build_decision_invocation_from_request(request)
            fallback_policy = str(getattr(request, "fallback_policy", "required") or "required")
            _mark_phase("build_invocation")
            call = build_routed_decision_call(invocation, fallback_policy=fallback_policy)
            _mark_phase("build_routed_call")
            resume_matches = self._decision_resume is not None and self._decision_resume_matches_call(call, self._decision_resume)
            _mark_phase("resume_match")
            if resume_matches:
                try:
                    return self._consume_decision_resume(call)
                finally:
                    _mark_phase("consume_resume")
            client = self._router.client_for_call(call)
            _mark_phase("route_client")
            client_policy = getattr(client, "policy", None)
            if callable(getattr(request, "fallback", None)) and (
                client_policy is None or not hasattr(client_policy, invocation.method_name)
            ):
                try:
                    return request.fallback()
                finally:
                    _mark_phase("request_fallback")
            try:
                return client.resolve(call)
            finally:
                _mark_phase("client_resolve")
        except BaseException as exc:
            error = exc
            raise
        finally:
            total_ms = _duration_ms(started)
            if total_ms >= 500 or (error is not None and not isinstance(error, PromptRequired)):
                routed_request = getattr(call, "request", None)
                player_id = getattr(routed_request, "player_id", None)
                log_event(
                    "runtime_decision_request_timing",
                    session_id=self._session_id,
                    total_ms=total_ms,
                    method_name=str(getattr(invocation, "method_name", "") or ""),
                    request_type=str(getattr(routed_request, "request_type", "") or getattr(request, "decision_name", "") or ""),
                    player_id=int(player_id) + 1 if player_id is not None else None,
                    fallback_policy=str(getattr(routed_request, "fallback_policy", "") or getattr(request, "fallback_policy", "") or ""),
                    client_class=client.__class__.__name__ if client is not None else None,
                    error_type=error.__class__.__name__ if error is not None and not isinstance(error, PromptRequired) else None,
                    **phase_timings,
                )

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
        return prompt_resume_matches_next_instance(
            current_prompt_sequence=self._prompt_boundary_builder.current_prompt_sequence(),
            resume_prompt_instance_id=prompt_instance_id_from_resume(resume),
        )

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
            log_event(
                "decision_resume_regenerated_legal_mismatch",
                session_id=self._session_id,
                request_id=resume.request_id,
                player_id=int(resume.player_id),
                request_type=str(resume.request_type),
                choice_id=str(resume.choice_id),
                regenerated_legal_choice_ids=sorted(choice_id for choice_id in legal if choice_id),
                frame_id=resume.frame_id,
                module_id=resume.module_id,
                module_type=resume.module_type,
                module_cursor=resume.module_cursor,
            )
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
            provider=resume.provider if resume.provider in {"human", "ai"} else "human",
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
            recovered = _ServerDecisionPolicyBridge._recover_hidden_trick_resume_choice(call, resume)
            if recovered is not None:
                log_event(
                    "decision_resume_hidden_trick_payload_recovered",
                    request_id=resume.request_id,
                    player_id=int(resume.player_id),
                    request_type=str(resume.request_type),
                    choice_id=str(resume.choice_id),
                    deck_index=getattr(recovered, "deck_index", None),
                )
                return recovered
            raise RuntimeDecisionResumeMismatch("decision resume parse failed") from exc

    @staticmethod
    def _recover_hidden_trick_resume_choice(call, resume: RuntimeDecisionResume):  # noqa: ANN001
        if str(call.request.request_type or "") != "hidden_trick_card":
            return None
        payload = resume.choice_payload if isinstance(resume.choice_payload, dict) else {}
        raw_deck_index = payload.get("deck_index", resume.choice_id)
        try:
            deck_index = int(raw_deck_index)
        except (TypeError, ValueError):
            return None
        label = payload.get("label") or payload.get("name") or str(deck_index)
        description = payload.get("description") or ""
        return SimpleNamespace(deck_index=deck_index, name=str(label), description=str(description))

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
        next_instance_id = prompt_sequence_after_resume(
            current_prompt_sequence=self._prompt_boundary_builder.current_prompt_sequence(),
            resume_prompt_instance_id=prompt_instance_id_from_resume(resume),
        )
        self._prompt_boundary_builder.set_prompt_sequence(next_instance_id)

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
        parser = getattr(call, "choice_parser", None)
        retry_count = max(0, int(self._config.get("retry_count", 1) or 0))
        max_attempt_count = max(1, int(self._config.get("max_attempt_count", 3) or 1))
        effective_attempt_count = min(retry_count + 1, max_attempt_count)
        request = call.request
        public_context = dict(request.public_context)
        public_context.setdefault("participant_client", ParticipantClientType.EXTERNAL_AI.value)
        public_context.setdefault("participant_seat", self._seat)
        public_context.setdefault("participant_transport", self._transport_name)
        if self._config:
            public_context.setdefault("participant_config", dict(self._config))
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
        public_context.update(diagnostics)
        player_id = int(request.player_id if request.player_id is not None else -1) + 1
        timeout_ms = int(self._config.get("timeout_ms", DEFAULT_EXTERNAL_AI_TIMEOUT_MS) or DEFAULT_EXTERNAL_AI_TIMEOUT_MS)
        stable_request_id = getattr(self._gateway, "_stable_ai_request_id", None)
        request_id = ""
        if callable(stable_request_id):
            request_id = str(
                stable_request_id(
                    request_type=request.request_type,
                    player_id=player_id,
                    public_context=public_context,
                )
            )
        envelope: dict[str, object] = {
            "request_id": request_id,
            "request_type": request.request_type,
            "player_id": player_id,
            "fallback_policy": request.fallback_policy,
            "public_context": public_context,
            "legal_choices": [dict(choice) for choice in getattr(call, "legal_choices", [])],
        }
        _attach_active_module_continuation_to_envelope(
            envelope,
            call,
            stable_request_id_resolver=getattr(self._gateway, "_stable_prompt_request_id", None),
            ensure_engine_import_path=RuntimeService._ensure_engine_import_path,
        )

        def _parse_decision(response: dict[str, object]):
            choice_id = str(response.get("choice_id") or "").strip()
            if callable(parser):
                return parser(choice_id, call.invocation.args, call.invocation.kwargs, call.invocation.state, call.invocation.player)
            return choice_id

        return self._gateway.resolve_external_ai_prompt(
            request_id=str(envelope.get("request_id") or ""),
            request_type=request.request_type,
            player_id=player_id,
            public_context=public_context,
            legal_choices=[dict(choice) for choice in getattr(call, "legal_choices", [])],
            timeout_ms=timeout_ms,
            prompt_metadata=_external_ai_prompt_metadata_from_envelope(envelope),
            parser=_parse_decision,
            fallback_fn=lambda: ai_callable(*call.invocation.args, **call.invocation.kwargs),
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


def _external_ai_prompt_metadata_from_envelope(envelope: dict[str, object]) -> dict[str, object]:
    prompt_metadata_keys = {
        "prompt_instance_id",
        "runner_kind",
        "resume_token",
        "frame_type",
        "frame_id",
        "module_id",
        "module_type",
        "module_cursor",
        "runtime_module",
        "batch_id",
        "missing_player_ids",
        "resume_tokens_by_player_id",
    }
    return {key: envelope[key] for key in prompt_metadata_keys if key in envelope}


class _LocalHumanDecisionClient:
    def __init__(
        self,
        *,
        human_seats: list[int],
        ai_fallback,
        gateway: DecisionGateway,
        prompt_boundary_builder: PromptBoundaryBuilder | None = None,
    ) -> None:
        self._prompt_boundary_builder = prompt_boundary_builder or PromptBoundaryBuilder(
            stable_request_id_resolver=getattr(gateway, "_stable_prompt_request_id", None),
            ensure_engine_import_path=RuntimeService._ensure_engine_import_path,
        )
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

    def set_prompt_boundary_builder(self, builder: PromptBoundaryBuilder) -> None:
        self._prompt_boundary_builder = builder

    def _ask(self, prompt: dict, parser, fallback_fn):
        started = time.perf_counter()
        phase_started = started
        phase_timings: dict[str, int] = {}
        error: BaseException | None = None

        def _mark_phase(name: str) -> None:
            nonlocal phase_started
            phase_timings[f"{name}_ms"] = _duration_ms(phase_started)
            phase_started = time.perf_counter()

        active_call = self._active_call
        envelope = self._prompt_boundary_builder.prepare(
            prompt,
            active_call=active_call,
        )
        _mark_phase("envelope_prepare")
        _mark_phase("active_call_attach")
        try:
            try:
                return self._gateway.resolve_human_prompt(envelope, parser, fallback_fn)
            finally:
                _mark_phase("gateway_resolve")
        except BaseException as exc:
            error = exc
            raise
        finally:
            total_ms = _duration_ms(started)
            if total_ms >= 500 or (error is not None and not isinstance(error, PromptRequired)):
                log_event(
                    "runtime_local_human_prompt_timing",
                    total_ms=total_ms,
                    request_id=str(envelope.get("request_id") or ""),
                    request_type=str(envelope.get("request_type") or ""),
                    player_id=envelope.get("player_id"),
                    prompt_instance_id=envelope.get("prompt_instance_id"),
                    error_type=error.__class__.__name__ if error is not None and not isinstance(error, PromptRequired) else None,
                    **phase_timings,
                )

    def resolve(self, call):
        if self.policy is None:
            raise AttributeError(call.invocation.method_name)
        started = time.perf_counter()
        error: BaseException | None = None
        self._active_call = call
        try:
            return getattr(self.policy, call.invocation.method_name)(*call.invocation.args, **call.invocation.kwargs)
        except BaseException as exc:
            error = exc
            raise
        finally:
            total_ms = _duration_ms(started)
            if total_ms >= 500 or (error is not None and not isinstance(error, PromptRequired)):
                request = getattr(call, "request", None)
                player_id = getattr(request, "player_id", None)
                log_event(
                    "runtime_local_human_policy_timing",
                    total_ms=total_ms,
                    method_name=str(getattr(call.invocation, "method_name", "") or ""),
                    request_type=str(getattr(request, "request_type", "") or ""),
                    player_id=int(player_id) + 1 if player_id is not None else None,
                    error_type=error.__class__.__name__ if error is not None and not isinstance(error, PromptRequired) else None,
                )
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

    def create_human_client(
        self,
        *,
        human_seats: list[int],
        ai_fallback,
        gateway: DecisionGateway,
        prompt_boundary_builder: PromptBoundaryBuilder | None = None,
    ):
        return _LocalHumanDecisionClient(
            human_seats=human_seats,
            ai_fallback=ai_fallback,
            gateway=gateway,
            prompt_boundary_builder=prompt_boundary_builder,
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
        identity_fields_for_player: Callable[[int], dict[str, Any]] | None = None,
    ) -> None:
        self._loop = loop
        self._stream_service = stream_service
        self._session_id = session_id
        self._events: list = []
        self._touch_activity = touch_activity
        self._human_player_ids = frozenset(int(player_id) for player_id in (human_player_ids or []))
        self._spectator_event_delay_ms = max(0, int(spectator_event_delay_ms))
        self._identity_fields_for_player = identity_fields_for_player

    def _run_stream_operation(self, failure_event: str, operation: str, coroutine_factory):
        coro = None
        future: concurrent.futures.Future | None = None
        started = time.perf_counter()
        try:
            coro = coroutine_factory()
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=_EVENT_STREAM_PUBLISH_TIMEOUT_SECONDS)
        except Exception as exc:
            if future is not None and isinstance(exc, concurrent.futures.TimeoutError):
                future.cancel()
            if future is None and inspect.iscoroutine(coro):
                coro.close()
            log_event(
                failure_event,
                session_id=self._session_id,
                operation=operation,
                timeout_seconds=_EVENT_STREAM_PUBLISH_TIMEOUT_SECONDS,
                duration_ms=_duration_ms(started),
                error=str(exc).strip() or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
                exception_repr=repr(exc),
            )
            return None

    def append(self, event) -> None:
        self._events.append(event)
        self._touch_activity(self._session_id)
        payload = event.to_dict()
        payload = self._with_protocol_identity(payload)
        latest_seq = 0
        if callable(getattr(self._stream_service, "latest_seq", None)):
            latest_seq_value = self._run_stream_operation(
                "runtime_event_stream_latest_seq_failed",
                "latest_seq",
                lambda: self._stream_service.latest_seq(self._session_id),
            )
            if latest_seq_value is not None:
                latest_seq = int(latest_seq_value or 0)
        published = self._run_stream_operation(
            "runtime_event_stream_publish_failed",
            "publish",
            lambda: self._stream_service.publish(self._session_id, "event", payload),
        )
        if published is None:
            return
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

    def _with_protocol_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._identity_fields_for_player is None:
            return payload
        enriched = dict(payload)
        self._merge_identity_fields(enriched, enriched.get("player_id"))
        self._merge_identity_fields(enriched, enriched.get("acting_player_id"), prefix="acting")
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            enriched["snapshot"] = self._with_snapshot_protocol_identity(snapshot)
        for field_name, value in payload.items():
            if field_name in {"player_id", "acting_player_id"}:
                continue
            if field_name.endswith("_player_id"):
                prefix = field_name[: -len("_player_id")]
                if prefix:
                    self._merge_identity_fields(enriched, value, prefix=prefix)
            elif field_name.endswith("_player_ids"):
                prefix = field_name[: -len("_player_ids")]
                if prefix:
                    self._merge_identity_list_fields(enriched, value, prefix=prefix)
            elif field_name == "winner_ids":
                self._merge_identity_list_fields(enriched, value, prefix="winner")
        return enriched

    def _with_snapshot_protocol_identity(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(snapshot)
        players = snapshot.get("players")
        if isinstance(players, list):
            enriched["players"] = [self._with_snapshot_player_identity(item) for item in players]
        board = snapshot.get("board")
        if isinstance(board, dict):
            enriched["board"] = self._with_snapshot_board_identity(board)
        return enriched

    def _with_snapshot_player_identity(self, player: object) -> object:
        if not isinstance(player, dict):
            return player
        enriched = dict(player)
        self._merge_identity_fields(enriched, enriched.get("player_id"), include_legacy=False)
        return enriched

    def _with_snapshot_board_identity(self, board: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(board)
        self._merge_identity_fields(enriched, enriched.get("marker_owner_player_id"), prefix="marker_owner")
        tiles = board.get("tiles")
        if isinstance(tiles, list):
            enriched["tiles"] = [self._with_snapshot_tile_identity(item) for item in tiles]
        return enriched

    def _with_snapshot_tile_identity(self, tile: object) -> object:
        if not isinstance(tile, dict):
            return tile
        enriched = dict(tile)
        self._merge_identity_fields(enriched, enriched.get("owner_player_id"), prefix="owner")
        self._merge_identity_list_fields(enriched, enriched.get("pawn_player_ids"), prefix="pawn")
        return enriched

    def _merge_identity_fields(
        self,
        payload: dict[str, Any],
        player_id: object,
        *,
        prefix: str | None = None,
        include_legacy: bool = True,
    ) -> None:
        numeric_player_id = self._numeric_player_id(player_id)
        if numeric_player_id is None or self._identity_fields_for_player is None:
            return
        identity_fields = self._identity_fields_for_player(numeric_player_id)
        for name, value in identity_fields.items():
            if name == "legacy_player_id" and not include_legacy:
                continue
            field_name = f"{prefix}_{name}" if prefix else name
            payload.setdefault(field_name, value)

    def _merge_identity_list_fields(self, payload: dict[str, Any], player_ids: object, *, prefix: str) -> None:
        if not isinstance(player_ids, list) or self._identity_fields_for_player is None:
            return
        collected: dict[str, list[Any]] = {}
        for item in player_ids:
            numeric_player_id = self._numeric_player_id(item)
            if numeric_player_id is None:
                return
            identity_fields = self._identity_fields_for_player(numeric_player_id)
            for name, value in identity_fields.items():
                list_name = self._identity_list_field_name(prefix, name)
                collected.setdefault(list_name, []).append(value)
        for name, values in collected.items():
            payload.setdefault(name, values)

    @staticmethod
    def _identity_list_field_name(prefix: str, identity_field_name: str) -> str:
        if identity_field_name.endswith("_id"):
            return f"{prefix}_{identity_field_name[:-3]}_ids"
        if identity_field_name.endswith("_index"):
            return f"{prefix}_{identity_field_name[:-6]}_indices"
        return f"{prefix}_{identity_field_name}s"

    @staticmethod
    def _numeric_player_id(player_id: object) -> int | None:
        if isinstance(player_id, bool):
            return None
        if isinstance(player_id, int):
            return player_id
        if isinstance(player_id, str):
            stripped = player_id.strip()
            if stripped.isdecimal():
                return int(stripped)
        return None
