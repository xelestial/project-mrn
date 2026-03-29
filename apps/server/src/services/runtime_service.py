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
        self._watchdogs: dict[str, threading.Thread] = {}
        self._status: dict[str, dict] = {}
        self._last_activity_ms: dict[str, int] = {}
        self._watchdog_timeout_ms = 45000

    async def start_runtime(self, session_id: str, seed: int = 42, policy_mode: str = "heuristic_v3_gpt") -> None:
        if session_id in self._threads and self._threads[session_id].is_alive():
            return
        loop = asyncio.get_running_loop()
        now_ms = self._now_ms()
        self._last_activity_ms[session_id] = now_ms
        thread = threading.Thread(
            target=self._run_engine_thread,
            args=(loop, session_id, seed, policy_mode),
            daemon=True,
        )
        self._status[session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": now_ms}
        self._threads[session_id] = thread
        thread.start()
        if session_id not in self._watchdogs or not self._watchdogs[session_id].is_alive():
            watchdog = threading.Thread(
                target=self._watchdog_thread,
                args=(loop, session_id),
                daemon=True,
            )
            self._watchdogs[session_id] = watchdog
            watchdog.start()

    def stop_runtime(self, session_id: str, reason: str) -> None:
        self._status[session_id] = {"status": "stop_requested", "reason": reason}

    def runtime_status(self, session_id: str) -> dict:
        self._refresh_status(session_id)
        if session_id in self._threads and self._threads[session_id].is_alive():
            base = dict(self._status.get(session_id, {"status": "running"}))
            base.setdefault("status", "running")
            base["last_activity_ms"] = self._last_activity_ms.get(session_id)
            return base
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
            vis_stream = _FanoutVisEventStream(loop, self._stream_service, session_id, self._touch_activity)
            engine = GameEngine(
                config=DEFAULT_CONFIG,
                policy=policy,
                rng=random.Random(seed),
                event_stream=vis_stream,
            )
            engine.run()
            self._session_service.finish_session(session_id)
            self._status[session_id] = {"status": "finished"}
            self._touch_activity(session_id)
        except Exception as exc:
            self._status[session_id] = {"status": "failed", "error": str(exc)}
            self._touch_activity(session_id)
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

    def _watchdog_thread(self, loop: asyncio.AbstractEventLoop, session_id: str) -> None:
        warned = False
        while True:
            thread = self._threads.get(session_id)
            status = self._status.get(session_id, {}).get("status")
            if thread is None:
                return
            if status in {"finished", "failed", "idle"}:
                return
            if not thread.is_alive():
                self._refresh_status(session_id)
                return
            last = self._last_activity_ms.get(session_id, self._now_ms())
            idle_ms = self._now_ms() - last
            if idle_ms > self._watchdog_timeout_ms and not warned:
                warned = True
                current = dict(self._status.get(session_id, {"status": "running"}))
                current["watchdog_state"] = "stalled_warning"
                current["last_activity_ms"] = last
                self._status[session_id] = current
                fut = asyncio.run_coroutine_threadsafe(
                    self._stream_service.publish(
                        session_id,
                        "error",
                        {
                            "code": "RUNTIME_STALLED_WARN",
                            "message": f"Runtime inactivity detected for {idle_ms}ms.",
                            "retryable": True,
                        },
                    ),
                    loop,
                )
                try:
                    fut.result()
                except Exception:
                    pass
            if idle_ms <= self._watchdog_timeout_ms:
                warned = False
                current = dict(self._status.get(session_id, {"status": "running"}))
                if current.get("status") == "running":
                    current["watchdog_state"] = "ok"
                    current["last_activity_ms"] = last
                    self._status[session_id] = current
            threading.Event().wait(2.0)

    def _touch_activity(self, session_id: str) -> None:
        self._last_activity_ms[session_id] = self._now_ms()

    def _refresh_status(self, session_id: str) -> None:
        thread = self._threads.get(session_id)
        if not thread:
            return
        current = self._status.get(session_id, {})
        status = current.get("status")
        if status == "running" and not thread.is_alive():
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
