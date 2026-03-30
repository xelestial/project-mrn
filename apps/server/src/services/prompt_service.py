from __future__ import annotations

import time
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
        self._resolved_ttl_ms = 5 * 60 * 1000

    def create_prompt(self, session_id: str, prompt: dict) -> PendingPrompt:
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
        return item

    def submit_decision(self, payload: dict) -> dict:
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
            return {"status": "stale", "reason": "prompt_timeout"}

        player_id = int(payload.get("player_id", 0))
        if player_id != pending.player_id:
            return {"status": "rejected", "reason": "player_mismatch"}

        self._pending.pop(request_id, None)
        self._record_resolved(request_id=request_id, reason="accepted")
        return {"status": "accepted", "reason": None}

    def timeout_pending(self, now_ms: int | None = None, session_id: str | None = None) -> list[PendingPrompt]:
        now = now_ms if now_ms is not None else self._now_ms()
        timed_out: list[PendingPrompt] = []
        for request_id, pending in list(self._pending.items()):
            if session_id is not None and pending.session_id != session_id:
                continue
            if now > (pending.created_at_ms + pending.timeout_ms):
                timed_out.append(pending)
                self._pending.pop(request_id, None)
                self._record_resolved(request_id=request_id, reason="prompt_timeout", now_ms=now)
        return timed_out

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
