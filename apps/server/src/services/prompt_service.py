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

    def create_prompt(self, session_id: str, prompt: dict) -> PendingPrompt:
        request_id = str(prompt.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("missing_request_id")
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
        request_id = str(payload.get("request_id", "")).strip()
        if not request_id:
            return {"status": "rejected", "reason": "missing_request_id"}

        pending = self._pending.get(request_id)
        if pending is None:
            return {"status": "stale", "reason": "request_not_pending"}

        now = self._now_ms()
        if now > (pending.created_at_ms + pending.timeout_ms):
            self._pending.pop(request_id, None)
            return {"status": "stale", "reason": "prompt_timeout"}

        player_id = int(payload.get("player_id", 0))
        if player_id != pending.player_id:
            return {"status": "rejected", "reason": "player_mismatch"}

        self._pending.pop(request_id, None)
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
        return timed_out

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
