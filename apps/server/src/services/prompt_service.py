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

    def __init__(self) -> None:
        self._pending: dict[str, PendingPrompt] = {}
        self._resolved: dict[str, tuple[int, str]] = {}
        self._decisions: dict[str, dict] = {}
        self._waiters: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._resolved_ttl_ms = 5 * 60 * 1000

    def create_prompt(self, session_id: str, prompt: dict) -> PendingPrompt:
        with self._lock:
            self._prune_resolved()
            request_id = str(prompt.get("request_id", "")).strip()
            if not request_id:
                raise ValueError("missing_request_id")
            if request_id in self._pending:
                raise ValueError("duplicate_pending_request_id")
            if request_id in self._resolved:
                raise ValueError("duplicate_recent_request_id")
            player_id = int(prompt.get("player_id", 0))
            timeout_ms = int(prompt.get("timeout_ms", 30000))
            item = PendingPrompt(
                session_id=session_id,
                request_id=request_id,
                player_id=player_id,
                timeout_ms=timeout_ms,
                created_at_ms=self._now_ms(),
                payload=prompt,
            )
            self._pending[request_id] = item
            self._waiters[request_id] = threading.Event()
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

            pending = self._pending.get(request_id)
            if pending is None:
                if request_id in self._resolved:
                    return {"status": "stale", "reason": "already_resolved"}
                return {"status": "stale", "reason": "request_not_pending"}

            now = self._now_ms()
            if now > (pending.created_at_ms + pending.timeout_ms):
                self._pending.pop(request_id, None)
                self._record_resolved(request_id=request_id, reason="prompt_timeout")
                waiter = self._waiters.pop(request_id, None)
                self._decisions.pop(request_id, None)
                result = {"status": "stale", "reason": "prompt_timeout"}
            else:
                player_id = int(payload.get("player_id", 0))
                if player_id != pending.player_id:
                    return {"status": "rejected", "reason": "player_mismatch"}

                self._pending.pop(request_id, None)
                self._decisions[request_id] = dict(payload)
                self._record_resolved(request_id=request_id, reason="accepted")
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
            for request_id, pending in list(self._pending.items()):
                if session_id is not None and pending.session_id != session_id:
                    continue
                if now > (pending.created_at_ms + pending.timeout_ms):
                    timed_out.append(pending)
                    self._pending.pop(request_id, None)
                    self._record_resolved(request_id=request_id, reason="prompt_timeout", now_ms=now)
                    waiter = self._waiters.pop(request_id, None)
                    self._decisions.pop(request_id, None)
                    if waiter is not None:
                        to_notify.append(waiter)
        for waiter in to_notify:
            waiter.set()
        return timed_out

    def wait_for_decision(self, request_id: str, timeout_ms: int) -> dict | None:
        if timeout_ms <= 0:
            timeout_ms = 1
        with self._lock:
            self._prune_resolved()
            if request_id in self._decisions:
                return self._decisions.pop(request_id)
            waiter = self._waiters.get(request_id)
            if waiter is None:
                return None
        waiter.wait(timeout_ms / 1000.0)
        with self._lock:
            decision = self._decisions.pop(request_id, None)
            self._waiters.pop(request_id, None)
            return decision

    def expire_prompt(self, request_id: str, reason: str = "prompt_timeout") -> PendingPrompt | None:
        waiter: threading.Event | None = None
        with self._lock:
            pending = self._pending.pop(request_id, None)
            if pending is None:
                return None
            self._record_resolved(request_id=request_id, reason=reason)
            self._decisions.pop(request_id, None)
            waiter = self._waiters.pop(request_id, None)
        if waiter is not None:
            waiter.set()
        return pending

    def has_pending_for_session(self, session_id: str) -> bool:
        with self._lock:
            for pending in self._pending.values():
                if pending.session_id == session_id:
                    return True
        return False

    def _record_resolved(self, request_id: str, reason: str, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        self._resolved[request_id] = (now, reason)
        self._prune_resolved(now)

    def _prune_resolved(self, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        cutoff = now - self._resolved_ttl_ms
        for request_id, (resolved_at, _) in list(self._resolved.items()):
            if resolved_at < cutoff:
                self._resolved.pop(request_id, None)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
