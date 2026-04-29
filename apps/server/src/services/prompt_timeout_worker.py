from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from apps.server.src.services.decision_gateway import (
    build_decision_ack_payload,
    build_decision_resolved_payload,
    build_decision_timeout_fallback_payload,
)


class PromptTimeoutWorker:
    def __init__(self, *, prompt_service, runtime_service, stream_service) -> None:
        self._prompt_service = prompt_service
        self._runtime_service = runtime_service
        self._stream_service = stream_service

    async def run_once(self, *, now_ms: int | None = None, session_id: str | None = None) -> list[dict]:
        timed_out = self._prompt_service.timeout_pending(now_ms=now_ms, session_id=session_id)
        results: list[dict] = []
        for pending in timed_out:
            prompt_payload = dict(pending.payload)
            public_context = prompt_payload.get("public_context", {})
            public_context = public_context if isinstance(public_context, dict) else {}
            fallback_policy = str(prompt_payload.get("fallback_policy", "timeout_fallback"))
            fallback_result = await self._runtime_service.execute_prompt_fallback(
                session_id=pending.session_id,
                request_id=pending.request_id,
                player_id=pending.player_id,
                fallback_policy=fallback_policy,
                prompt_payload=prompt_payload,
            )
            await self._stream_service.publish(
                pending.session_id,
                "decision_ack",
                build_decision_ack_payload(
                    request_id=pending.request_id,
                    status="stale",
                    player_id=pending.player_id,
                    reason="prompt_timeout",
                    provider="human",
                ),
            )
            await self._stream_service.publish(
                pending.session_id,
                "event",
                build_decision_resolved_payload(
                    request_id=pending.request_id,
                    player_id=pending.player_id,
                    request_type=str(prompt_payload.get("request_type") or ""),
                    resolution="timeout_fallback",
                    choice_id=fallback_result.get("choice_id"),
                    provider="human",
                    round_index=public_context.get("round_index"),
                    turn_index=public_context.get("turn_index"),
                ),
            )
            await self._stream_service.publish(
                pending.session_id,
                "event",
                build_decision_timeout_fallback_payload(
                    request_id=pending.request_id,
                    player_id=pending.player_id,
                    request_type=str(prompt_payload.get("request_type") or ""),
                    fallback_policy=fallback_policy,
                    fallback_execution=fallback_result.get("status"),
                    fallback_choice_id=fallback_result.get("choice_id"),
                    provider="human",
                    round_index=public_context.get("round_index"),
                    turn_index=public_context.get("turn_index"),
                ),
            )
            results.append(
                {
                    "session_id": pending.session_id,
                    "request_id": pending.request_id,
                    "player_id": pending.player_id,
                    "fallback_choice_id": fallback_result.get("choice_id"),
                }
            )
        return results


class PromptTimeoutWorkerLoop:
    def __init__(
        self,
        *,
        worker: PromptTimeoutWorker,
        poll_interval_ms: int = 250,
        session_id: str | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._worker = worker
        self._poll_interval_ms = max(50, int(poll_interval_ms))
        self._session_id = session_id
        self._sleeper = sleeper

    async def run_once(self) -> list[dict]:
        return await self._worker.run_once(session_id=self._session_id)

    async def run(
        self,
        *,
        max_iterations: int | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> dict[str, int]:
        iterations = 0
        timeout_count = 0
        while stop_event is None or not stop_event.is_set():
            results = await self.run_once()
            iterations += 1
            timeout_count += len(results)
            if max_iterations is not None and iterations >= max(0, int(max_iterations)):
                break
            await self._sleeper(self._poll_interval_ms / 1000.0)
        return {"iterations": iterations, "timeout_count": timeout_count}
