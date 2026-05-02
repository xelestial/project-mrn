from __future__ import annotations

import time
import threading
from dataclasses import dataclass


@dataclass(slots=True)
class PendingPrompt:
    session_id: str
    request_id: str
    player_id: int
    timeout_ms: int
    created_at_ms: int
    payload: dict


class PromptService:
    """In-memory prompt lifecycle manager (B3 baseline)."""

    def __init__(self, prompt_store=None, command_store=None) -> None:
        self._pending: dict[str, PendingPrompt] = {}
        self._resolved: dict[str, tuple[int, str]] = {}
        self._decisions: dict[str, dict] = {}
        self._waiters: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._resolved_ttl_ms = 5 * 60 * 1000
        self._prompt_store = prompt_store
        self._command_store = command_store

    def create_prompt(self, session_id: str, prompt: dict) -> PendingPrompt:
        superseded_waiters: list[threading.Event] = []
        with self._lock:
            self._prune_resolved()
            request_id = str(prompt.get("request_id", "")).strip()
            if not request_id:
                raise ValueError("missing_request_id")
            if self._has_pending_request(request_id):
                raise ValueError("duplicate_pending_request_id")
            if self._has_recently_resolved_request(request_id):
                raise ValueError("duplicate_recent_request_id")
            if _is_module_prompt(prompt):
                _require_module_continuation(prompt)
            player_id = int(prompt.get("player_id", 0))
            timeout_ms = int(prompt.get("timeout_ms", 30000))
            superseded_waiters = self._supersede_pending_for_player(
                session_id=session_id,
                player_id=player_id,
                keep_request_id=request_id,
            )
            item = PendingPrompt(
                session_id=session_id,
                request_id=request_id,
                player_id=player_id,
                timeout_ms=timeout_ms,
                created_at_ms=self._now_ms(),
                payload=prompt,
            )
            self._set_pending(item)
            self._waiters[request_id] = threading.Event()
        for waiter in superseded_waiters:
            waiter.set()
        return item

    def submit_decision(self, payload: dict) -> dict:
        waiter: threading.Event | None = None
        with self._lock:
            self._prune_resolved()
            request_id = str(payload.get("request_id", "")).strip()
            if not request_id:
                return {"status": "rejected", "reason": "missing_request_id"}
            choice_id = str(payload.get("choice_id", "")).strip()
            if not choice_id:
                return {"status": "rejected", "reason": "missing_choice_id"}

            pending = self._get_pending(request_id)
            if pending is None:
                if self._has_recently_resolved_request(request_id):
                    return {"status": "stale", "reason": "already_resolved"}
                return {"status": "stale", "reason": "request_not_pending"}

            now = self._now_ms()
            if now > (pending.created_at_ms + pending.timeout_ms):
                self._delete_pending(request_id)
                self._record_resolved(request_id=request_id, reason="prompt_timeout")
                waiter = self._waiters.pop(request_id, None)
                self._delete_decision(request_id)
                result = {"status": "stale", "reason": "prompt_timeout"}
            else:
                player_id = int(payload.get("player_id", 0))
                if player_id != pending.player_id:
                    return {"status": "rejected", "reason": "player_mismatch"}
                if _is_module_prompt(pending.payload):
                    mismatch = _module_decision_mismatch(pending.payload, payload)
                    if mismatch:
                        return {"status": "rejected", "reason": mismatch}
                    legal = {
                        str(choice.get("choice_id") or "").strip()
                        for choice in pending.payload.get("legal_choices", [])
                        if isinstance(choice, dict)
                    }
                    if legal and choice_id not in legal:
                        return {"status": "rejected", "reason": "choice_not_legal"}

                decision_payload = dict(payload)
                command_payload = {
                    "request_id": request_id,
                    "player_id": player_id,
                    "choice_id": choice_id,
                    "decision": decision_payload,
                    "submitted_at_ms": now,
                }
                resolved_payload = {"resolved_at_ms": now, "reason": "accepted"}
                atomic_accept = getattr(self._prompt_store, "accept_decision_with_command", None)
                if callable(atomic_accept) and self._command_store is not None:
                    accepted = atomic_accept(
                        session_id=pending.session_id,
                        request_id=request_id,
                        decision_payload=decision_payload,
                        resolved_payload=resolved_payload,
                        command_store=self._command_store,
                        command_type="decision_submitted",
                        command_payload=command_payload,
                        server_time_ms=now,
                    )
                    if accepted is None:
                        return {"status": "stale", "reason": "request_not_pending"}
                else:
                    self._delete_pending(request_id)
                    self._set_decision(request_id, decision_payload)
                    if self._command_store is not None:
                        self._command_store.append_command(
                            pending.session_id,
                            "decision_submitted",
                            command_payload,
                            request_id=request_id,
                            server_time_ms=now,
                        )
                    self._record_resolved(request_id=request_id, reason="accepted", now_ms=now)
                waiter = self._waiters.get(request_id)
                result = {"status": "accepted", "reason": None}
        if waiter is not None:
            waiter.set()
        return result

    def timeout_pending(self, now_ms: int | None = None, session_id: str | None = None) -> list[PendingPrompt]:
        now = now_ms if now_ms is not None else self._now_ms()
        timed_out: list[PendingPrompt] = []
        to_notify: list[threading.Event] = []
        with self._lock:
            for request_id, pending in list(self._iter_pending_items()):
                if session_id is not None and pending.session_id != session_id:
                    continue
                if now > (pending.created_at_ms + pending.timeout_ms):
                    timed_out.append(pending)
                    self._delete_pending(request_id)
                    self._record_resolved(request_id=request_id, reason="prompt_timeout", now_ms=now)
                    waiter = self._waiters.pop(request_id, None)
                    self._delete_decision(request_id)
                    if waiter is not None:
                        to_notify.append(waiter)
        for waiter in to_notify:
            waiter.set()
        return timed_out

    def record_timeout_fallback_decision(
        self,
        pending: PendingPrompt,
        *,
        choice_id: str,
        submitted_at_ms: int | None = None,
    ) -> dict:
        now = submitted_at_ms if submitted_at_ms is not None else self._now_ms()
        request_id = str(pending.request_id).strip()
        fallback_choice_id = str(choice_id or "timeout_fallback").strip() or "timeout_fallback"
        decision_payload = {
            "type": "decision",
            "request_id": request_id,
            "player_id": int(pending.player_id),
            "choice_id": fallback_choice_id,
            "choice_payload": {},
            "provider": "timeout_fallback",
        }
        command_payload = {
            "request_id": request_id,
            "player_id": int(pending.player_id),
            "choice_id": fallback_choice_id,
            "decision": decision_payload,
            "submitted_at_ms": now,
            "source": "timeout_fallback",
        }
        with self._lock:
            self._set_decision(request_id, decision_payload)
            if self._command_store is not None:
                self._command_store.append_command(
                    pending.session_id,
                    "decision_submitted",
                    command_payload,
                    request_id=request_id,
                    server_time_ms=now,
                )
        return decision_payload

    def wait_for_decision(self, request_id: str, timeout_ms: int) -> dict | None:
        if timeout_ms <= 0:
            timeout_ms = 1
        with self._lock:
            self._prune_resolved()
            decision = self._get_decision(request_id)
            if decision is not None:
                return decision
            waiter = self._waiters.get(request_id)
            if waiter is None:
                pending = self._get_pending(request_id)
                if pending is None:
                    return None
                waiter = threading.Event()
                self._waiters[request_id] = waiter
        deadline = self._now_ms() + timeout_ms
        while self._now_ms() < deadline:
            waiter.wait(min(50, max(1, deadline - self._now_ms())) / 1000.0)
            with self._lock:
                decision = self._get_decision(request_id)
                if decision is not None:
                    self._waiters.pop(request_id, None)
                    return decision
        with self._lock:
            decision = self._get_decision(request_id)
            self._waiters.pop(request_id, None)
            return decision

    def expire_prompt(self, request_id: str, reason: str = "prompt_timeout") -> PendingPrompt | None:
        waiter: threading.Event | None = None
        with self._lock:
            pending = self._get_pending(request_id)
            if pending is None:
                return None
            self._delete_pending(request_id)
            self._record_resolved(request_id=request_id, reason=reason)
            self._delete_decision(request_id)
            waiter = self._waiters.pop(request_id, None)
        if waiter is not None:
            waiter.set()
        return pending

    def has_pending_for_session(self, session_id: str) -> bool:
        with self._lock:
            for pending in self._iter_pending_values():
                if pending.session_id == session_id:
                    return True
        return False

    def delete_session_data(self, session_id: str) -> None:
        with self._lock:
            for request_id, pending in list(self._iter_pending_items()):
                if pending.session_id != session_id:
                    continue
                self._delete_pending(request_id)
                self._delete_decision(request_id)
                self._waiters.pop(request_id, None)

    def _record_resolved(self, request_id: str, reason: str, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        if self._prompt_store is not None:
            self._prompt_store.save_resolved(request_id, {"resolved_at_ms": now, "reason": reason})
        else:
            self._resolved[request_id] = (now, reason)
        self._prune_resolved(now)

    def _prune_resolved(self, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        cutoff = now - self._resolved_ttl_ms
        if self._prompt_store is not None:
            for request_id, payload in self._prompt_store.list_resolved().items():
                resolved_at = int(payload.get("resolved_at_ms", 0))
                if resolved_at < cutoff:
                    self._prompt_store.delete_resolved(request_id)
                    self._prompt_store.delete_decision(request_id)
            return
        for request_id, (resolved_at, _) in list(self._resolved.items()):
            if resolved_at < cutoff:
                self._resolved.pop(request_id, None)
                self._decisions.pop(request_id, None)

    def _supersede_pending_for_player(
        self,
        *,
        session_id: str,
        player_id: int,
        keep_request_id: str,
    ) -> list[threading.Event]:
        waiters: list[threading.Event] = []
        now = self._now_ms()
        for existing_request_id, pending in list(self._iter_pending_items()):
            if existing_request_id == keep_request_id:
                continue
            if pending.session_id != session_id or pending.player_id != player_id:
                continue
            self._delete_pending(existing_request_id)
            self._delete_decision(existing_request_id)
            self._record_resolved(
                request_id=existing_request_id,
                reason="superseded",
                now_ms=now,
            )
            waiter = self._waiters.pop(existing_request_id, None)
            if waiter is not None:
                waiters.append(waiter)
        return waiters

    def _has_pending_request(self, request_id: str) -> bool:
        if self._prompt_store is not None:
            return self._prompt_store.get_pending(request_id) is not None
        return request_id in self._pending

    def _has_recently_resolved_request(self, request_id: str) -> bool:
        if self._prompt_store is not None:
            return self._prompt_store.get_resolved(request_id) is not None
        return request_id in self._resolved

    def _set_pending(self, pending: PendingPrompt) -> None:
        if self._prompt_store is not None:
            self._prompt_store.save_pending(
                pending.request_id,
                {
                    "session_id": pending.session_id,
                    "request_id": pending.request_id,
                    "player_id": pending.player_id,
                    "timeout_ms": pending.timeout_ms,
                    "created_at_ms": pending.created_at_ms,
                    "payload": dict(pending.payload),
                },
            )
            return
        self._pending[pending.request_id] = pending

    def _get_pending(self, request_id: str) -> PendingPrompt | None:
        if self._prompt_store is not None:
            raw = self._prompt_store.get_pending(request_id)
            if raw is None:
                return None
            return PendingPrompt(
                session_id=str(raw.get("session_id", "")),
                request_id=str(raw.get("request_id", "")),
                player_id=int(raw.get("player_id", 0)),
                timeout_ms=int(raw.get("timeout_ms", 0)),
                created_at_ms=int(raw.get("created_at_ms", 0)),
                payload=dict(raw.get("payload", {})),
            )
        return self._pending.get(request_id)

    def _delete_pending(self, request_id: str) -> None:
        if self._prompt_store is not None:
            self._prompt_store.delete_pending(request_id)
            return
        self._pending.pop(request_id, None)

    def _iter_pending_values(self) -> list[PendingPrompt]:
        if self._prompt_store is not None:
            return [self._get_pending(str(item.get("request_id", ""))) for item in self._prompt_store.list_pending() if self._get_pending(str(item.get("request_id", ""))) is not None]  # type: ignore[list-item]
        return list(self._pending.values())

    def _iter_pending_items(self) -> list[tuple[str, PendingPrompt]]:
        items: list[tuple[str, PendingPrompt]] = []
        if self._prompt_store is not None:
            for raw in self._prompt_store.list_pending():
                request_id = str(raw.get("request_id", "")).strip()
                pending = self._get_pending(request_id)
                if pending is not None:
                    items.append((request_id, pending))
            return items
        return list(self._pending.items())

    def _set_decision(self, request_id: str, payload: dict) -> None:
        if self._prompt_store is not None:
            self._prompt_store.save_decision(request_id, payload)
            return
        self._decisions[request_id] = payload

    def _get_decision(self, request_id: str) -> dict | None:
        if self._prompt_store is not None:
            getter = getattr(self._prompt_store, "get_decision", None)
            if callable(getter):
                return getter(request_id)
            return self._prompt_store.pop_decision(request_id)
        decision = self._decisions.get(request_id)
        return dict(decision) if decision is not None else None

    def _pop_decision(self, request_id: str) -> dict | None:
        if self._prompt_store is not None:
            return self._prompt_store.pop_decision(request_id)
        return self._decisions.pop(request_id, None)

    def _delete_decision(self, request_id: str) -> None:
        if self._prompt_store is not None:
            self._prompt_store.delete_decision(request_id)
            return
        self._decisions.pop(request_id, None)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)


def _is_module_prompt(prompt: dict) -> bool:
    return (
        str(prompt.get("runner_kind") or prompt.get("runtime_runner_kind") or "").strip() == "module"
        or isinstance(prompt.get("runtime_module"), dict)
        or bool(prompt.get("resume_token"))
    )


def _require_module_continuation(prompt: dict) -> None:
    required = ("resume_token", "frame_id", "module_id", "module_type")
    missing = [field for field in required if not str(prompt.get(field) or "").strip()]
    if missing:
        raise ValueError(f"missing_module_continuation:{','.join(missing)}")
    module_type = str(prompt.get("module_type") or "").strip()
    frame_id = str(prompt.get("frame_id") or "").strip()
    if module_type in {"ResupplyModule", "SimultaneousPromptBatchModule"} or frame_id.startswith("simul:"):
        if not str(prompt.get("batch_id") or "").strip():
            raise ValueError("missing_batch_id")


def _module_decision_mismatch(prompt: dict, decision: dict) -> str:
    for field, reason in (
        ("resume_token", "token_mismatch"),
        ("frame_id", "module_mismatch"),
        ("module_id", "module_mismatch"),
        ("module_type", "module_mismatch"),
    ):
        expected = str(prompt.get(field) or "").strip()
        actual = str(decision.get(field) or "").strip()
        if expected and actual != expected:
            return reason
    return ""
