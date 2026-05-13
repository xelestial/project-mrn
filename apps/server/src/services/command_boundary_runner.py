from __future__ import annotations

import time
from typing import Any, Callable

from apps.server.src.services.command_boundary_finalizer import CommandBoundaryFinalizer
from apps.server.src.services.command_boundary_store import CommandBoundaryGameStateStore

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


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _is_command_boundary_terminal_status(status: object) -> bool:
    return str(status or "") in _COMMAND_BOUNDARY_TERMINAL_STATUSES


class CommandBoundaryRunner:
    def __init__(
        self,
        *,
        game_state_store: object,
        latest_view_commit_seq: Callable[..., int],
        prepare_transition_context: Callable[..., object],
        run_transition_once: Callable[..., dict],
        emit_latest_view_commit: Callable[..., object],
        materialize_prompt_boundaries: Callable[..., object],
        commit_guard: Callable[[str], dict[str, Any] | None],
        store_factory: Callable[..., object] = CommandBoundaryGameStateStore,
        finalizer_factory: Callable[..., CommandBoundaryFinalizer] = CommandBoundaryFinalizer,
    ) -> None:
        self._game_state_store = game_state_store
        self._latest_view_commit_seq = latest_view_commit_seq
        self._prepare_transition_context = prepare_transition_context
        self._run_transition_once = run_transition_once
        self._emit_latest_view_commit = emit_latest_view_commit
        self._materialize_prompt_boundaries = materialize_prompt_boundaries
        self._commit_guard = commit_guard
        self._store_factory = store_factory
        self._finalizer_factory = finalizer_factory

    def run(
        self,
        loop: object,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        *,
        max_transitions: int | None = None,
        first_command_consumer_name: str | None,
        first_command_seq: int,
    ) -> dict:
        loop_started = time.perf_counter()
        if self._game_state_store is None:
            raise RuntimeError("command_boundary_requires_game_state_store")
        original_store = self._game_state_store
        boundary_store = self._store_factory(
            original_store,
            session_id=session_id,
            base_commit_seq=self._latest_view_commit_seq(session_id),
        )
        transitions = 0
        last_step: dict = {"status": "unavailable", "reason": "not_started"}
        module_trace: list[dict] = []
        checkpoint_command_consumer_name = first_command_consumer_name
        checkpoint_command_seq = int(first_command_seq)
        prepare_started = time.perf_counter()
        transition_context = self._prepare_transition_context(
            loop,
            session_id,
            seed,
            policy_mode,
            publish_external_side_effects=False,
            game_state_store_override=boundary_store,
        )
        engine_prepare_ms = _duration_ms(prepare_started)
        transition_loop_started = time.perf_counter()
        while max_transitions is None or transitions < max(1, int(max_transitions)):
            command_consumer_name = first_command_consumer_name if transitions == 0 else None
            command_seq = int(first_command_seq) if transitions == 0 else None
            last_step = self._run_transition_once(
                loop,
                session_id,
                seed,
                policy_mode,
                False,
                command_consumer_name,
                command_seq,
                checkpoint_command_consumer_name=checkpoint_command_consumer_name,
                checkpoint_command_seq=checkpoint_command_seq,
                publish_external_side_effects=False,
                transition_context=transition_context,
                game_state_store_override=boundary_store,
            )
            transitions += 1
            module_trace.append(_command_module_trace_entry(transitions, last_step))
            if _is_command_boundary_terminal_status(last_step.get("status")):
                break
        engine_transition_loop_ms = _duration_ms(transition_loop_started)

        terminal_status = str(last_step.get("status", ""))
        terminal_reason = str(last_step.get("reason") or terminal_status or "unknown")
        finalization = self._finalizer_factory(
            authoritative_store=original_store,
            emit_latest_view_commit=self._emit_latest_view_commit,
            materialize_prompt_boundaries=self._materialize_prompt_boundaries,
            commit_guard=self._commit_guard,
        ).finalize(
            loop=loop,
            session_id=session_id,
            boundary_store=boundary_store,
            processed_command_seq=checkpoint_command_seq,
            terminal_status=terminal_status,
            terminal_boundary_reason=terminal_reason,
        )
        result_step = dict(last_step)
        if finalization.blocked_reason is not None:
            result_step.update(
                {
                    "status": "stale",
                    "reason": finalization.blocked_reason,
                    **(finalization.blocked_fields or {}),
                }
            )
        return {
            **result_step,
            "transitions": transitions,
            "module_transition_count": transitions,
            "redis_commit_count": finalization.redis_commit_count,
            "view_commit_count": finalization.view_commit_count,
            "internal_redis_commit_attempt_count": boundary_store.redis_commit_count,
            "internal_view_commit_attempt_count": boundary_store.view_commit_count,
            "internal_state_stage_count": boundary_store.internal_state_stage_count,
            "terminal_status": terminal_status,
            "terminal_boundary_reason": terminal_reason,
            "module_trace": module_trace,
            "engine_loop_total_ms": _duration_ms(loop_started),
            "engine_prepare_ms": engine_prepare_ms,
            "engine_transition_loop_ms": engine_transition_loop_ms,
            **finalization.result_fields(),
        }


def _command_module_trace_entry(index: int, step: dict) -> dict:
    entry = {
        "index": int(index),
        "status": str(step.get("status") or ""),
        "reason": str(step.get("reason") or ""),
    }
    for key in (
        "runner_kind",
        "module_type",
        "module_id",
        "frame_id",
        "module_cursor",
        "request_id",
        "request_type",
        "player_id",
    ):
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


__all__ = ["CommandBoundaryRunner"]
