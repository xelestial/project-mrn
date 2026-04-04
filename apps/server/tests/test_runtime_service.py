from __future__ import annotations

import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_service import PromptService


class RuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_service = SessionService()
        self.stream_service = StreamService()
        self.prompt_service = PromptService()
        self.runtime_service = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
        )

    def test_execute_prompt_fallback_records_recent_history(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        result = asyncio.run(
            self.runtime_service.execute_prompt_fallback(
                session_id=session.session_id,
                request_id="req_timeout_1",
                player_id=2,
                fallback_policy="timeout_fallback",
                prompt_payload={"fallback_choice_id": "choice_default"},
            )
        )

        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["choice_id"], "choice_default")
        status = self.runtime_service.runtime_status(session.session_id)
        recent = status.get("recent_fallbacks", [])
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[-1]["request_id"], "req_timeout_1")
        self.assertEqual(recent[-1]["choice_id"], "choice_default")

    def test_start_runtime_uses_async_to_thread_bridge(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        calls: list[tuple[str, int, str | None]] = []
        original = self.runtime_service._run_engine_sync

        def _fake_run_engine_sync(loop, session_id: str, seed: int, policy_mode: str | None) -> None:  # noqa: ANN001
            del loop
            calls.append((session_id, seed, policy_mode))

        self.runtime_service._run_engine_sync = _fake_run_engine_sync  # type: ignore[method-assign]
        try:
            async def _exercise() -> dict:
                await self.runtime_service.start_runtime(session.session_id, seed=99, policy_mode="balanced_v2")
                status_local = self.runtime_service.runtime_status(session.session_id)
                self.assertIn(status_local.get("status"), {"running", "finished"})
                for _ in range(30):
                    status_local = self.runtime_service.runtime_status(session.session_id)
                    if status_local.get("status") == "finished":
                        break
                    await asyncio.sleep(0.01)
                return status_local

            status = asyncio.run(_exercise())
            for _ in range(3):
                status = self.runtime_service.runtime_status(session.session_id)
                if status.get("status") == "finished":
                    break
            self.assertEqual(status.get("status"), "finished")
        finally:
            self.runtime_service._run_engine_sync = original  # type: ignore[method-assign]

        self.assertEqual(calls, [(session.session_id, 99, "balanced_v2")])

    def test_runtime_status_marks_recovery_required_for_in_progress_without_task(self) -> None:
        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        self.session_service.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        self.session_service.start_session(session.session_id, session.host_token)

        restarted_runtime = RuntimeService(
            session_service=self.session_service,
            stream_service=self.stream_service,
            prompt_service=self.prompt_service,
        )
        status = restarted_runtime.runtime_status(session.session_id)
        self.assertEqual(status.get("status"), "recovery_required")
        self.assertEqual(status.get("reason"), "runtime_task_missing_after_restart")

    def test_run_engine_sync_uses_human_policy_bridge_when_human_seat_exists(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        import engine

        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        captured: dict[str, object] = {}

        class _FakeGameEngine:
            def __init__(self, config, policy, rng, event_stream):  # noqa: ANN001
                del config, rng, event_stream
                captured["policy"] = policy

            def run(self) -> None:
                return None

        loop = asyncio.new_event_loop()
        try:
            with patch.object(engine, "GameEngine", _FakeGameEngine):
                self.runtime_service._run_engine_sync(loop, session.session_id, seed=42, policy_mode=None)
        finally:
            loop.close()

        policy_obj = captured.get("policy")
        self.assertIsNotNone(policy_obj)
        self.assertTrue(hasattr(policy_obj, "_inner"))

    def test_run_engine_sync_uses_ai_policy_when_all_seats_are_ai(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        import engine

        session = self.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        captured: dict[str, object] = {}

        class _FakeGameEngine:
            def __init__(self, config, policy, rng, event_stream):  # noqa: ANN001
                del config, rng, event_stream
                captured["policy"] = policy

            def run(self) -> None:
                return None

        loop = asyncio.new_event_loop()
        try:
            with patch.object(engine, "GameEngine", _FakeGameEngine):
                self.runtime_service._run_engine_sync(loop, session.session_id, seed=42, policy_mode=None)
        finally:
            loop.close()

        policy_obj = captured.get("policy")
        self.assertIsNotNone(policy_obj)
        self.assertFalse(hasattr(policy_obj, "_inner"))

    def test_human_bridge_replaces_inner_ask_with_server_prompt_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_test",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_req_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_ready = False
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_ready = "bridge_req_1" in self.prompt_service._pending  # type: ignore[attr-defined]
                if pending_ready:
                    break
                time.sleep(0.01)
            self.assertTrue(pending_ready)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": "bridge_req_1",
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "roll")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_test"),
                loop,
            ).result(timeout=2.0)
            self.assertTrue(any(msg.type == "prompt" and msg.payload.get("request_id") == "bridge_req_1" for msg in published))
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_req_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertEqual(len(resolved_all), 1)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(resolved.payload.get("resolution"), "accepted")
            self.assertEqual(resolved.payload.get("choice_id"), "roll")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_timeout_path_emits_resolved_before_timeout_event(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_timeout",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_timeout_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 50,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "fallback_choice_id": "roll",
                        "public_context": {"round_index": 1, "turn_index": 1},
                    },
                    lambda response: str(response.get("choice_id", "")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()
            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "fallback")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_timeout"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_timeout_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            timeout_event = next(
                (msg for msg in bridge_events if msg.payload.get("event_type") == "decision_timeout_fallback"),
                None,
            )
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertEqual(len(resolved_all), 1)
            self.assertIsNotNone(timeout_event)
            self.assertLess(requested.seq, resolved.seq)
            self.assertLess(resolved.seq, timeout_event.seq)
            self.assertEqual(resolved.payload.get("resolution"), "timeout_fallback")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_parser_error_emits_single_parser_fallback_resolution(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerHumanPolicyBridge(
                session_id="sess_bridge_parser_fallback",
                human_seats=[0],
                ai_fallback=object(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge._inner._ask(  # type: ignore[attr-defined]
                    {
                        "request_id": "bridge_parser_1",
                        "request_type": "movement",
                        "player_id": 1,
                        "timeout_ms": 2000,
                        "legal_choices": [{"choice_id": "roll", "label": "Roll"}],
                        "fallback_policy": "timeout_fallback",
                        "public_context": {"round_index": 1, "turn_index": 2},
                    },
                    lambda _response: (_ for _ in ()).throw(ValueError("parser failure")),
                    lambda: "fallback",
                )

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_ready = False
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_ready = "bridge_parser_1" in self.prompt_service._pending  # type: ignore[attr-defined]
                if pending_ready:
                    break
                time.sleep(0.01)
            self.assertTrue(pending_ready)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": "bridge_parser_1",
                    "player_id": 1,
                    "choice_id": "roll",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")
            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "fallback")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_bridge_parser_fallback"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("request_id") == "bridge_parser_1"
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved_all = [msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"]
            self.assertIsNotNone(requested)
            self.assertEqual(len(resolved_all), 1)
            self.assertEqual(resolved_all[0].payload.get("resolution"), "parser_error_fallback")
            self.assertEqual(resolved_all[0].payload.get("choice_id"), "roll")
            self.assertLess(requested.seq, resolved_all[0].seq)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()


if __name__ == "__main__":
    unittest.main()
