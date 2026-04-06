from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.session_models import SeatType, SessionStatus
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import (
    DecisionGateway,
    DecisionInvocation,
    build_decision_invocation,
    build_canonical_decision_request,
    prepare_decision_method_from_invocation,
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
    ) -> None:
        self._session_service = session_service
        self._stream_service = stream_service
        self._prompt_service = prompt_service
        self._config_factory = config_factory or EngineConfigFactory()
        self._runtime_tasks: dict[str, asyncio.Task] = {}
        self._watchdogs: dict[str, asyncio.Task] = {}
        self._status: dict[str, dict] = {}
        self._last_activity_ms: dict[str, int] = {}
        self._fallback_history: dict[str, list[dict]] = {}
        self._watchdog_timeout_ms = int(watchdog_timeout_ms)
        self._initialize_recovery_state()

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str | None = None) -> None:
        existing = self._runtime_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        now_ms = self._now_ms()
        self._last_activity_ms[session_id] = now_ms
        self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
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
        log_event("runtime_stop_requested", session_id=session_id, reason=reason)

    def runtime_status(self, session_id: str) -> dict:
        self._refresh_status(session_id)
        task = self._runtime_tasks.get(session_id)
        if task is not None and not task.done():
            base = dict(self._status.get(session_id, {"status": "running"}))
            base.setdefault("status", "running")
            base["last_activity_ms"] = self._last_activity_ms.get(session_id)
            base["recent_fallbacks"] = list(self._fallback_history.get(session_id, []))[-10:]
            return base
        base = dict(self._status.get(session_id, {"status": "idle"}))
        try:
            session = self._session_service.get_session(session_id)
        except Exception:
            session = None
        if session is not None and session.status == SessionStatus.IN_PROGRESS:
            base["status"] = "recovery_required"
            base.setdefault("reason", "runtime_task_missing_after_restart")
        base["recent_fallbacks"] = list(self._fallback_history.get(session_id, []))[-10:]
        return base

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

        choice_id = str(
            prompt_payload.get("fallback_choice_id")
            or prompt_payload.get("default_choice_id")
            or "timeout_fallback"
        )
        record = {
            "request_id": request_id,
            "player_id": player_id,
            "fallback_policy": fallback_policy,
            "choice_id": choice_id,
            "executed_at_ms": self._now_ms(),
        }
        self._fallback_history.setdefault(session_id, []).append(record)
        self._touch_activity(session_id)
        log_event(
            "runtime_fallback_executed",
            session_id=session_id,
            request_id=request_id,
            player_id=player_id,
            fallback_policy=fallback_policy,
            choice_id=choice_id,
        )
        return {"status": "executed", "choice_id": choice_id}

    async def _run_engine_async(
        self,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(
                self._run_engine_sync,
                loop,
                session_id,
                seed,
                policy_mode,
            )
            self._session_service.finish_session(session_id)
            self._status[session_id] = {"status": "finished"}
            self._touch_activity(session_id)
            log_event("runtime_finished", session_id=session_id)
        except Exception as exc:
            self._status[session_id] = {"status": "failed", "error": str(exc)}
            self._touch_activity(session_id)
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

    def _run_engine_sync(
        self,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        seed: int,
        policy_mode: str | None,
    ) -> None:
        self._ensure_gpt_import_path()
        from engine import GameEngine
        from policy.factory import PolicyFactory

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
        policy = ai_policy
        if self._stream_service is not None:
            policy = _ServerDecisionPolicyBridge(
                session_id=session_id,
                human_seats=human_seats,
                ai_fallback=ai_policy,
                prompt_service=self._prompt_service,
                stream_service=self._stream_service,
                loop=loop,
                touch_activity=self._touch_activity,
                fallback_executor=self.execute_prompt_fallback,
            )
        vis_stream = _FanoutVisEventStream(loop, self._stream_service, session_id, self._touch_activity)
        engine = GameEngine(
            config=self._config_factory.create(resolved),
            policy=policy,
            rng=random.Random(seed),
            event_stream=vis_stream,
        )
        engine.run()

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
                await asyncio.sleep(2.0)
                continue
            if idle_ms > self._watchdog_timeout_ms and not warned:
                warned = True
                current = dict(self._status.get(session_id, {"status": "running"}))
                current["watchdog_state"] = "stalled_warning"
                current["last_activity_ms"] = last
                self._status[session_id] = current
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
            await asyncio.sleep(2.0)

    def _touch_activity(self, session_id: str) -> None:
        self._last_activity_ms[session_id] = self._now_ms()

    def _refresh_status(self, session_id: str) -> None:
        task = self._runtime_tasks.get(session_id)
        if not task:
            return
        current = self._status.get(session_id, {})
        status = current.get("status")
        if status == "running" and task.done():
            self._status[session_id] = {"status": "finished"}

    @staticmethod
    def _now_ms() -> int:
        import time

        return int(time.time() * 1000)

    @staticmethod
    def _ensure_gpt_import_path() -> None:
        root = Path(__file__).resolve().parents[4]
        gpt_dir = root / "GPT"
        gpt_text = str(gpt_dir)
        if gpt_text not in sys.path:
            sys.path.insert(0, gpt_text)

    def _initialize_recovery_state(self) -> None:
        try:
            sessions = self._session_service.list_sessions()
        except Exception:
            return
        for session in sessions:
            if session.status != SessionStatus.IN_PROGRESS:
                continue
            self._status.setdefault(
                session.session_id,
                {
                    "status": "recovery_required",
                    "reason": "runtime_task_missing_after_restart",
                },
            )


class _ServerDecisionPolicyBridge:
    """Server runtime adapter: normalizes human and AI seats through one decision contract."""

    def __init__(
        self,
        *,
        session_id: str,
        human_seats: list[int],
        ai_fallback,
        prompt_service,
        stream_service,
        loop: asyncio.AbstractEventLoop,
        touch_activity,
        fallback_executor,
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
        )
        self._ai_provider = _ServerAiDecisionProvider(ai_fallback=ai_fallback, gateway=self._gateway)
        self._human_provider = _ServerHumanDecisionProvider(
            human_seats=human_seats,
            ai_fallback=ai_fallback,
            gateway=self._gateway,
        )
        self._router = _ServerDecisionProviderRouter(
            human_seats=human_seats,
            human_provider=self._human_provider,
            ai_provider=self._ai_provider,
        )
        self._inner = self._human_provider.policy if self._human_provider is not None else None

    def _ask(self, prompt: dict, parser, fallback_fn):
        if self._human_provider is not None:
            self._human_provider.bump_prompt_seq()
            prompt = dict(prompt)
            prompt["prompt_instance_id"] = self._human_provider.prompt_seq
        return self._gateway.resolve_human_prompt(prompt, parser, fallback_fn)

    def __getattr__(self, name: str):
        target = self._router.attribute_target(name)
        attr = getattr(target, name)
        if not name.startswith("choose_") or not callable(attr):
            return attr

        def _wrapped(*args, **kwargs):
            invocation = build_decision_invocation(name, args, kwargs)
            provider = self._router.provider_for_choice(invocation)
            return provider.call(invocation)

        return _wrapped


_ServerHumanPolicyBridge = _ServerDecisionPolicyBridge


class _ServerAiDecisionProvider:
    def __init__(self, *, ai_fallback, gateway: DecisionGateway) -> None:
        self.policy = ai_fallback
        self._gateway = gateway

    def call(self, invocation: DecisionInvocation):
        ai_callable = getattr(self.policy, invocation.method_name)
        request = build_canonical_decision_request(invocation, fallback_policy="ai")
        player_id = int(request.player_id if request.player_id is not None else -1) + 1
        return self._gateway.resolve_ai_decision(
            request_type=request.request_type,
            player_id=player_id,
            public_context=request.public_context,
            resolver=lambda: ai_callable(*invocation.args, **invocation.kwargs),
            choice_serializer=prepare_decision_method_from_invocation(invocation).choice_serializer,
        )


class _ServerHumanDecisionProvider:
    def __init__(self, *, human_seats: list[int], ai_fallback, gateway: DecisionGateway) -> None:
        if not human_seats:
            self.policy = None
            return
        from viewer.human_policy import HumanHttpPolicy

        self.policy = HumanHttpPolicy(
            human_seat=human_seats[0],
            human_seats=human_seats,
            ai_fallback=ai_fallback,
        )
        self.policy._ask = self._ask  # type: ignore[method-assign]
        self._gateway = gateway

    @property
    def prompt_seq(self) -> int:
        if self.policy is None:
            return 0
        return int(getattr(self.policy, "_prompt_seq", 0))

    def bump_prompt_seq(self) -> None:
        if self.policy is not None:
            self.policy._prompt_seq += 1  # type: ignore[attr-defined]

    def _ask(self, prompt: dict, parser, fallback_fn):
        return self._gateway.resolve_human_prompt(prompt, parser, fallback_fn)

    def call(self, invocation: DecisionInvocation):
        if self.policy is None:
            raise AttributeError(invocation.method_name)
        return getattr(self.policy, invocation.method_name)(*invocation.args, **invocation.kwargs)


class _ServerDecisionProviderRouter:
    def __init__(
        self,
        *,
        human_seats: list[int],
        human_provider: _ServerHumanDecisionProvider,
        ai_provider: _ServerAiDecisionProvider,
    ) -> None:
        self._human_seats = frozenset(int(seat) for seat in human_seats)
        self._human_provider = human_provider
        self._ai_provider = ai_provider

    def attribute_target(self, name: str):
        human_policy = self._human_provider.policy
        if human_policy is not None and hasattr(human_policy, name):
            return human_policy
        return self._ai_provider.policy

    def provider_for_choice(self, invocation: DecisionInvocation):
        player_id = invocation.player_id
        if (
            isinstance(player_id, int)
            and player_id in self._human_seats
            and self._human_provider.policy is not None
        ):
            return self._human_provider
        return self._ai_provider


class _FanoutVisEventStream:
    """Engine event stream bridge that forwards events to StreamService immediately."""

    def __init__(self, loop: asyncio.AbstractEventLoop, stream_service, session_id: str, touch_activity) -> None:
        self._loop = loop
        self._stream_service = stream_service
        self._session_id = session_id
        self._events: list = []
        self._touch_activity = touch_activity

    def append(self, event) -> None:
        self._events.append(event)
        self._touch_activity(self._session_id)
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, "event", event.to_dict()),
            self._loop,
        )
        fut.result()

    @property
    def events(self) -> list:
        return list(self._events)

    def __iter__(self):
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)
