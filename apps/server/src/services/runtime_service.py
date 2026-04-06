from __future__ import annotations

import asyncio
import json
import random
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.session_models import ParticipantClientType, SeatConfig, SeatType, SessionStatus
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import (
    DecisionGateway,
    DecisionInvocation,
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
                session_seats=session.seats,
                human_seats=human_seats,
                ai_fallback=ai_policy,
                prompt_service=self._prompt_service,
                stream_service=self._stream_service,
                loop=loop,
                touch_activity=self._touch_activity,
                fallback_executor=self.execute_prompt_fallback,
                client_factory=self._decision_client_factory,
            )
        vis_stream = _FanoutVisEventStream(loop, self._stream_service, session_id, self._touch_activity)
        engine = GameEngine(
            config=self._config_factory.create(resolved),
            policy=policy,
            decision_port=policy if hasattr(policy, "request") else None,
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
        session_seats: list[SeatConfig] | None = None,
        human_seats: list[int],
        ai_fallback,
        prompt_service,
        stream_service,
        loop: asyncio.AbstractEventLoop,
        touch_activity,
        fallback_executor,
        client_factory=None,
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
        backoff_ms = max(0, int(self._config.get("backoff_ms", 250) or 0))
        fallback_mode = str(self._config.get("fallback_mode", "local_ai") or "local_ai").strip().lower()
        diagnostics: dict[str, object] = {
            "external_ai_transport_mode": "http",
            "external_ai_resolution_status": "pending",
            "external_ai_attempt_count": 0,
        }

        def _resolve_via_sender(public_context: dict[str, object]):
            last_error: Exception | None = None
            for attempt in range(retry_count + 1):
                try:
                    public_context["external_ai_attempt_count"] = attempt + 1
                    health = self._check_worker_health()
                    if isinstance(health, dict):
                        _validate_external_ai_request_type_support(health, envelope.request_type)
                        worker_id = str(health.get("worker_id") or "").strip()
                        if worker_id:
                            public_context["external_ai_worker_id"] = worker_id
                    response = self._sender(envelope) if self._sender is not None else _default_external_ai_http_sender(envelope)
                    if not isinstance(response, dict):
                        raise ValueError("external_ai_response_not_object")
                    _validate_external_ai_request_type_support(response, envelope.request_type)
                    _validate_external_ai_identity(response, envelope.participant_config)
                    worker_id = str(response.get("worker_id") or "").strip()
                    if worker_id:
                        public_context["external_ai_worker_id"] = worker_id
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
                    if attempt < retry_count and backoff_ms > 0:
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
        if self._sender is not None and self._healthchecker is None:
            return None
        checker = self._healthchecker or _default_external_ai_healthcheck
        payload = checker(dict(self._config))
        if self._healthchecker is not None:
            if not isinstance(payload, dict):
                raise ValueError("external_ai_health_response_not_object")
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
    cache_key = f"{endpoint}|{healthcheck_path}"
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
    available_capabilities = {
        str(item).strip()
        for item in (payload.get("capabilities") or [])
        if isinstance(item, str) and str(item).strip()
    }
    if required_capabilities and not required_capabilities.issubset(available_capabilities):
        raise RuntimeError("external_ai_missing_required_capability")


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


def _classify_external_ai_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message in {
        "external_ai_http_error",
        "external_ai_healthcheck_failed",
        "external_ai_worker_identity_mismatch",
        "external_ai_contract_version_mismatch",
        "external_ai_missing_required_capability",
        "external_ai_missing_request_type_support",
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

    def resolve(self, call):
        if self.policy is None:
            raise AttributeError(call.invocation.method_name)
        return getattr(self.policy, call.invocation.method_name)(*call.invocation.args, **call.invocation.kwargs)


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
