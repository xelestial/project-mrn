from __future__ import annotations

import asyncio
import inspect
import json
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from urllib import error as urllib_error
from urllib import request as urllib_request

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.session_models import ParticipantClientType, SeatConfig, SeatType, SessionStatus
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import (
    DecisionGateway,
    DecisionInvocation,
    PromptRequired,
    build_decision_invocation,
    build_decision_invocation_from_request,
    build_routed_decision_call,
)
from apps.server.src.services.engine_config_factory import EngineConfigFactory


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
        self._session_finished_callbacks: list = []
        self._runtime_state_store = runtime_state_store
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._worker_id = f"runtime_{uuid.uuid4().hex[:12]}"
        self._lease_ttl_ms = max(5000, self._watchdog_timeout_ms * 2)
        self._initialize_recovery_state()

    def add_session_finished_callback(self, callback) -> None:
        if callback is None:
            return
        self._session_finished_callbacks.append(callback)

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
        existing = self._runtime_tasks.get(session_id)
        if existing is not None and not existing.done():
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
        self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
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
        lease_expires_at_ms = int(base.get("lease_expires_at_ms", 0) or 0)
        if session is not None and session.status == SessionStatus.IN_PROGRESS and (
            base.get("status") in {None, "idle", "running", "stop_requested"} and lease_expires_at_ms <= self._now_ms()
        ):
            base["status"] = "recovery_required"
            base.setdefault("reason", "runtime_task_missing_after_restart")
            self._status[session_id] = dict(base)
            self._persist_runtime_state(session_id)
        base["recent_fallbacks"] = self._recent_fallbacks(session_id)
        recovery = self.recovery_checkpoint(session_id)
        if recovery.get("available"):
            base["recovery_checkpoint"] = recovery
        return base

    def public_runtime_status(self, session_id: str) -> dict:
        status = dict(self.runtime_status(session_id))
        recovery = status.get("recovery_checkpoint")
        if isinstance(recovery, dict):
            public_recovery = {
                "available": bool(recovery.get("available")),
                "checkpoint": recovery.get("checkpoint") if isinstance(recovery.get("checkpoint"), dict) else {},
                "view_state": recovery.get("view_state") if isinstance(recovery.get("view_state"), dict) else {},
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
        try:
            view_state = self._game_state_store.load_projected_view_state(session_id, "public")
        except Exception:
            view_state = None
        if not isinstance(view_state, dict):
            view_state = self._game_state_store.load_view_state(session_id)
        if not isinstance(checkpoint, dict):
            return {"available": False, "reason": "checkpoint_missing"}
        if not isinstance(current_state, dict):
            return {"available": False, "reason": "current_state_missing", "checkpoint": checkpoint}
        return {
            "available": True,
            "checkpoint": checkpoint,
            "current_state": current_state,
            "view_state": view_state if isinstance(view_state, dict) else {},
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
        explicit = str(
            prompt_payload.get("fallback_choice_id")
            or prompt_payload.get("default_choice_id")
            or ""
        ).strip()
        if explicit:
            return explicit
        legal_choices = prompt_payload.get("legal_choices")
        if isinstance(legal_choices, list):
            for choice in legal_choices:
                if not isinstance(choice, dict):
                    continue
                choice_id = str(choice.get("choice_id") or "").strip()
                if choice_id:
                    return choice_id
        return "timeout_fallback"

    async def process_command_once(
        self,
        *,
        session_id: str,
        command_seq: int,
        consumer_name: str,
        seed: int = 42,
        policy_mode: str | None = None,
    ) -> dict:
        if not self._acquire_runtime_lease(session_id):
            return {
                "status": "running_elsewhere",
                "lease_owner": self._runtime_state_store.lease_owner(session_id) if self._runtime_state_store is not None else None,
            }
        now_ms = self._now_ms()
        self._last_activity_ms[session_id] = now_ms
        self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
        self._persist_runtime_state(session_id)
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.to_thread(
                self._run_engine_transition_loop_sync,
                loop,
                session_id,
                seed,
                policy_mode,
                first_command_consumer_name=consumer_name,
                first_command_seq=int(command_seq),
            )
            status = str(result.get("status", ""))
            if status == "waiting_input":
                self._status[session_id] = {"status": "waiting_input", "watchdog_state": "waiting_input", "last_transition": result}
            elif status == "finished":
                self._session_service.finish_session(session_id)
                await self._notify_session_finished(session_id)
                self._status[session_id] = {"status": "finished"}
            else:
                self._status[session_id] = {"status": "idle", "last_transition": result}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            return result
        except Exception as exc:
            self._status[session_id] = {"status": "failed", "error": str(exc)}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            raise
        finally:
            self._release_runtime_lease(session_id)

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
                return
            self._session_service.finish_session(session_id)
            await self._notify_session_finished(session_id)
            self._status[session_id] = {"status": "finished"}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            self._release_runtime_lease(session_id)
            log_event("runtime_finished", session_id=session_id)
        except Exception as exc:
            self._status[session_id] = {"status": "failed", "error": str(exc)}
            self._touch_activity(session_id)
            self._persist_runtime_state(session_id)
            self._release_runtime_lease(session_id)
            log_event("runtime_failed", session_id=session_id, error=str(exc))
            await self._stream_service.publish(
                session_id,
                "error",
                build_error_payload(
                    code="RUNTIME_EXECUTION_FAILED",
                    message=str(exc),
                    retryable=False,
                ),
            )

    async def _notify_session_finished(self, session_id: str) -> None:
        for callback in list(self._session_finished_callbacks):
            try:
                result = callback(session_id)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                log_event("session_finished_callback_failed", session_id=session_id, error=str(exc))
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
    ) -> dict | None:
        if self._game_state_store is not None:
            return self._run_engine_transition_loop_sync(loop, session_id, seed, policy_mode)
        self._run_legacy_engine_sync(loop, session_id, seed, policy_mode)
        return None

    def _run_legacy_engine_sync(
        self,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> None:
        self._ensure_gpt_import_path()
        from engine import GameEngine
        from policy.factory import PolicyFactory
        from state import GameState

        session = self._session_service.get_session(session_id)
        resolved = dict(session.resolved_parameters or {})
        runtime = dict(resolved.get("runtime", {}))
        selected_policy_mode = policy_mode or runtime.get("policy_mode") or "heuristic_v3_gpt"
        ai_policy = PolicyFactory.create_runtime_policy(
            policy_mode=selected_policy_mode,
            lap_policy_mode=selected_policy_mode,
        )
        human_seats = [
            max(0, int(seat.seat) - 1)
            for seat in session.seats
            if seat.seat_type == SeatType.HUMAN
        ]
        human_player_ids = [
            int(seat.seat)
            for seat in session.seats
            if seat.seat_type == SeatType.HUMAN
        ]
        policy = ai_policy
        if self._stream_service is not None:
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
                blocking_human_prompts=True,
            )
        spectator_event_delay_ms = int(
            runtime.get(
                "spectator_event_delay_ms",
                0 if os.environ.get("PYTEST_CURRENT_TEST") else 350,
            )
            or 0
        )
        vis_stream = _FanoutVisEventStream(
            loop,
            self._stream_service,
            session_id,
            self._touch_activity,
            human_player_ids=human_player_ids,
            spectator_event_delay_ms=spectator_event_delay_ms,
        )
        engine_config = self._config_factory.create(resolved)
        engine = GameEngine(
            config=engine_config,
            policy=policy,
            decision_port=policy if hasattr(policy, "request") else None,
            rng=random.Random(seed),
            event_stream=vis_stream,
        )
        initial_state = self._hydrate_engine_state(session_id, engine_config, GameState)
        if initial_state is None:
            engine.run()
        else:
            engine.run(initial_state=initial_state)

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
            )
            transitions += 1
            status = str(last_step.get("status", ""))
            if status in {"finished", "unavailable", "waiting_input"}:
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
            if status in {"finished", "failed", "idle"}:
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
        current = self._status.get(session_id, {})
        status = current.get("status")
        if status == "running" and task.done():
            self._status[session_id] = {"status": "finished"}
            self._persist_runtime_state(session_id)

    @staticmethod
    def _now_ms() -> int:
        import time

        return int(time.time() * 1000)

    @staticmethod
    def _ensure_gpt_import_path() -> None:
        root = Path(__file__).resolve().parents[4]
        gpt_dir = root / "GPT"
        claude_dir = root / "CLAUDE"
        gpt_text = str(gpt_dir)
        if gpt_text in sys.path:
            sys.path.remove(gpt_text)
        sys.path.insert(0, gpt_text)
        for name, module in list(sys.modules.items()):
            if isinstance(module, ModuleType) and _module_belongs_to_root(module, claude_dir):
                sys.modules.pop(name, None)

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
    def _prompt_sequence_seed_for_transition(state) -> int:
        prompt_sequence = int(getattr(state, "prompt_sequence", 0) or 0)
        pending_request_id = str(getattr(state, "pending_prompt_request_id", "") or "")
        pending_prompt_type = str(getattr(state, "pending_prompt_type", "") or "")
        pending_instance_id = int(getattr(state, "pending_prompt_instance_id", 0) or 0)
        if pending_request_id and pending_instance_id > 0:
            if (
                pending_prompt_type in {"draft_card", "final_character"}
                or ":draft_card:" in pending_request_id
                or ":final_character:" in pending_request_id
            ):
                # Draft/final-character prompts happen inside round setup before
                # the next priority order is committed. The previous round order
                # can still be present in checkpoints, so identify this replay by
                # prompt type and consume resolved draft decisions from the start.
                return 0
            if pending_prompt_type == "movement" or ":movement:" in pending_request_id:
                pending_actions = getattr(state, "pending_actions", None) or []
                first_action = pending_actions[0] if pending_actions else None
                action_type = (
                    first_action.get("type")
                    if isinstance(first_action, dict)
                    else getattr(first_action, "type", "")
                )
                action_payload = (
                    first_action.get("payload")
                    if isinstance(first_action, dict)
                    else getattr(first_action, "payload", {})
                )
                if (
                    action_type == "continue_after_trick_phase"
                    and isinstance(action_payload, dict)
                    and action_payload.get("hidden_trick_synced")
                ):
                    return max(0, pending_instance_id - 1)
                return max(0, pending_instance_id - 2)
            return max(0, pending_instance_id - 1)
        return prompt_sequence

    def _acquire_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        return bool(self._runtime_state_store.acquire_lease(session_id, self._worker_id, self._lease_ttl_ms))

    def _refresh_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        return bool(self._runtime_state_store.refresh_lease(session_id, self._worker_id, self._lease_ttl_ms))

    def _release_runtime_lease(self, session_id: str) -> bool:
        if self._runtime_state_store is None:
            return True
        return bool(self._runtime_state_store.release_lease(session_id, self._worker_id))

    def _hydrate_engine_state(self, session_id: str, config, game_state_cls):
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
        return self._run_engine_transition_once_sync(
            None,
            session_id,
            seed,
            policy_mode,
            True,
            None,
            None,
        )

    def _run_engine_transition_once_sync(
        self,
        loop: asyncio.AbstractEventLoop | None,
        session_id: str,
        seed: int,
        policy_mode: str | None,
        require_checkpoint: bool,
        command_consumer_name: str | None,
        command_seq: int | None,
    ) -> dict:
        self._ensure_gpt_import_path()
        from engine import GameEngine
        from policy.factory import PolicyFactory
        from state import GameState

        session = self._session_service.get_session(session_id)
        resolved = dict(session.resolved_parameters or {})
        runtime = dict(resolved.get("runtime", {}))
        selected_policy_mode = policy_mode or runtime.get("policy_mode") or "heuristic_v3_gpt"
        ai_policy = PolicyFactory.create_runtime_policy(policy_mode=selected_policy_mode, lap_policy_mode=selected_policy_mode)
        policy = ai_policy
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
        state = self._hydrate_engine_state(session_id, config, GameState)
        if state is None:
            if require_checkpoint:
                return {"status": "unavailable", "reason": "checkpoint_missing"}
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
        try:
            state = engine.prepare_run(initial_state=state) if state is not None else engine.prepare_run()
            if callable(getattr(policy, "set_prompt_sequence", None)):
                policy.set_prompt_sequence(self._prompt_sequence_seed_for_transition(state))
            step = engine.run_next_transition(state)
        except PromptRequired as exc:
            state = state or getattr(engine, "_last_prepared_state", None)
            if state is None:
                raise
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
            state.pending_prompt_request_id = ""
            state.pending_prompt_type = ""
            state.pending_prompt_player_id = 0
            state.pending_prompt_instance_id = 0
        if self._game_state_store is not None:
            payload = state.to_checkpoint_payload()
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
            self._game_state_store.commit_transition(
                session_id,
                current_state=payload,
                checkpoint={
                    "schema_version": 1,
                    "session_id": session_id,
                    "latest_seq": self._latest_stream_seq_sync(loop, session_id),
                    "latest_event_type": latest_event_type,
                    "round_index": int(payload.get("rounds_completed", 0)) + 1,
                    "turn_index": int(payload.get("turn_index", 0)),
                    "has_snapshot": True,
                    "waiting_prompt_request_id": payload.get("pending_prompt_request_id"),
                    "waiting_prompt_type": payload.get("pending_prompt_type"),
                    "waiting_prompt_player_id": payload.get("pending_prompt_player_id"),
                    "waiting_prompt_instance_id": payload.get("pending_prompt_instance_id"),
                    "prompt_sequence": payload.get("prompt_sequence"),
                    "pending_action_count": len(payload.get("pending_actions") or []),
                    "scheduled_action_count": len(payload.get("scheduled_actions") or []),
                    "pending_action_types": pending_action_types,
                    "scheduled_action_types": scheduled_action_types,
                    "next_action_type": pending_action_types[0] if pending_action_types else "",
                    "next_scheduled_action_type": scheduled_action_types[0] if scheduled_action_types else "",
                    "has_pending_actions": bool(payload.get("pending_actions")),
                    "has_scheduled_actions": bool(payload.get("scheduled_actions")),
                    "has_pending_turn_completion": bool(payload.get("pending_turn_completion")),
                    "processed_command_seq": command_seq,
                    "processed_command_consumer": command_consumer_name,
                    "updated_at_ms": updated_at_ms,
                },
                command_consumer_name=command_consumer_name,
                command_seq=command_seq,
                runtime_event_payload={
                    "event_type": latest_event_type,
                    "status": step.get("status"),
                    "reason": step.get("reason"),
                    "request_id": step.get("request_id"),
                    "request_type": step.get("request_type"),
                    "player_id": step.get("player_id"),
                    "processed_command_seq": command_seq,
                    "processed_command_consumer": command_consumer_name,
                    "pending_action_count": len(payload.get("pending_actions") or []),
                    "scheduled_action_count": len(payload.get("scheduled_actions") or []),
                },
                runtime_event_server_time_ms=updated_at_ms,
            )
        return step

    def _latest_stream_seq_sync(self, loop: asyncio.AbstractEventLoop | None, session_id: str) -> int:
        if loop is None or self._stream_service is None:
            return 0
        future = asyncio.run_coroutine_threadsafe(self._stream_service.latest_seq(session_id), loop)
        return int(future.result(timeout=5))


def _module_belongs_to_root(module: ModuleType, root_dir: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        try:
            return Path(module_file).resolve().is_relative_to(root_dir)
        except OSError:
            return False
    module_path = getattr(module, "__path__", None)
    if module_path is None:
        return False
    try:
        return any(Path(entry).resolve().is_relative_to(root_dir) for entry in module_path)
    except OSError:
        return False


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

    def set_prompt_sequence(self, value: int) -> None:
        if self._human_client is not None:
            self._human_client.set_prompt_seq(value)

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
        client = self._router.client_for_call(call)
        client_policy = getattr(client, "policy", None)
        if callable(getattr(request, "fallback", None)) and (client_policy is None or not hasattr(client_policy, invocation.method_name)):
            return request.fallback()
        return client.resolve(call)

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
    timeout_ms = int(envelope.participant_config.get("timeout_ms", 15000) or 15000)
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
    timeout_ms = int(config.get("timeout_ms", 15000) or 15000)
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
        RuntimeService._ensure_gpt_import_path()
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
                envelope.setdefault("player_id", getattr(request, "player_id", None))
                envelope.setdefault("fallback_policy", getattr(request, "fallback_policy", None))
                prompt_context = dict(envelope.get("public_context") or {})
                request_context = dict(getattr(request, "public_context", {}) or {})
                envelope["public_context"] = {**prompt_context, **request_context}
        return self._gateway.resolve_human_prompt(envelope, parser, fallback_fn)

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
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, "event", payload),
            self._loop,
        )
        fut.result()
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
