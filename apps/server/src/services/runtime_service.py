from __future__ import annotations

import asyncio
import random
import sys
import threading
from pathlib import Path

class RuntimeService:
    """Background runtime orchestration for all-AI baseline sessions."""

    def __init__(self, session_service, stream_service) -> None:
        self._session_service = session_service
        self._stream_service = stream_service
        self._threads: dict[str, threading.Thread] = {}
        self._status: dict[str, dict] = {}

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str = "heuristic_v3_gpt") -> None:
        if session_id in self._threads and self._threads[session_id].is_alive():
            return
        loop = asyncio.get_running_loop()
        thread = threading.Thread(
            target=self._run_engine_thread,
            args=(loop, session_id, seed, policy_mode),
            daemon=True,
        )
        self._status[session_id] = {"status": "running"}
        self._threads[session_id] = thread
        thread.start()

    def stop_runtime(self, session_id: str, reason: str) -> None:
        self._status[session_id] = {"status": "stop_requested", "reason": reason}

    def runtime_status(self, session_id: str) -> dict:
        if session_id in self._threads and self._threads[session_id].is_alive():
            return {"status": "running"}
        return self._status.get(session_id, {"status": "idle"})

    def _run_engine_thread(self, loop: asyncio.AbstractEventLoop, session_id: str, seed: int, policy_mode: str) -> None:
        try:
            self._ensure_gpt_import_path()
            from config import DEFAULT_CONFIG
            from engine import GameEngine
            from policy.factory import PolicyFactory

            policy = PolicyFactory.create_runtime_policy(
                policy_mode=policy_mode,
                lap_policy_mode=policy_mode,
            )
            vis_stream = _FanoutVisEventStream(loop, self._stream_service, session_id)
            engine = GameEngine(
                config=DEFAULT_CONFIG,
                policy=policy,
                rng=random.Random(seed),
                event_stream=vis_stream,
            )
            engine.run()
            self._session_service.finish_session(session_id)
            self._status[session_id] = {"status": "finished"}
        except Exception as exc:
            self._status[session_id] = {"status": "failed", "error": str(exc)}
            fut = asyncio.run_coroutine_threadsafe(
                self._stream_service.publish(
                    session_id,
                    "error",
                    {
                        "code": "RUNTIME_EXECUTION_FAILED",
                        "message": str(exc),
                        "retryable": False,
                    },
                ),
                loop,
            )
            fut.result()

    @staticmethod
    def _ensure_gpt_import_path() -> None:
        root = Path(__file__).resolve().parents[4]
        gpt_dir = root / "GPT"
        gpt_text = str(gpt_dir)
        if gpt_text not in sys.path:
            sys.path.insert(0, gpt_text)


class _FanoutVisEventStream:
    """Engine event stream bridge that forwards events to StreamService immediately."""

    def __init__(self, loop: asyncio.AbstractEventLoop, stream_service, session_id: str) -> None:
        self._loop = loop
        self._stream_service = stream_service
        self._session_id = session_id
        self._events: list = []

    def append(self, event) -> None:
        self._events.append(event)
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
