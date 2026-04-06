from __future__ import annotations

import asyncio
import threading
import time
import unittest
from unittest.mock import patch

from apps.server.src.services.decision_gateway import (
    build_decision_invocation,
    build_canonical_decision_request,
    build_public_context,
    decision_request_type_for_method,
    serialize_ai_choice_id,
)
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

    def test_decision_request_type_for_method_uses_canonical_mapping(self) -> None:
        self.assertEqual(decision_request_type_for_method("choose_purchase_tile"), "purchase_tile")
        self.assertEqual(decision_request_type_for_method("choose_mark_target"), "mark_target")
        self.assertEqual(decision_request_type_for_method("choose_pabal_dice_mode"), "pabal_dice_mode")
        self.assertEqual(decision_request_type_for_method("choose_custom_branch"), "custom_branch")

    def test_purchase_tile_method_spec_keeps_request_context_and_choice_in_sync(self) -> None:
        state = type("State", (), {"rounds_completed": 1, "turn_index": 3})()
        player = type("Player", (), {"cash": 15, "position": 8, "shards": 2})()

        self.assertEqual(decision_request_type_for_method("choose_purchase_tile"), "purchase_tile")
        self.assertEqual(serialize_ai_choice_id("choose_purchase_tile", False), "no")
        self.assertEqual(
            build_public_context(
                "choose_purchase_tile",
                (state, player, 9, "T2", 4),
                {"source": "landing"},
            ),
            {
                "round_index": 2,
                "turn_index": 4,
                "player_cash": 15,
                "player_position": 8,
                "player_shards": 2,
                "tile_index": 9,
                "cost": 4,
                "source": "landing",
            },
        )

    def test_specific_reward_and_runaway_specs_keep_specialized_contracts(self) -> None:
        reward = type("Reward", (), {"deck_index": 102, "name": "Lucky Break"})()
        state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
        player = type("Player", (), {"cash": 9, "position": 22, "shards": 5})()

        self.assertEqual(decision_request_type_for_method("choose_specific_trick_reward"), "specific_trick_reward")
        self.assertEqual(serialize_ai_choice_id("choose_specific_trick_reward", reward), "102")
        self.assertEqual(decision_request_type_for_method("choose_runaway_slave_step"), "runaway_step_choice")
        self.assertEqual(serialize_ai_choice_id("choose_runaway_slave_step", True), "yes")
        self.assertEqual(
            build_public_context(
                "choose_runaway_slave_step",
                (state, player, 25, 26, "S"),
                {},
            ),
            {
                "round_index": 6,
                "turn_index": 1,
                "player_cash": 9,
                "player_position": 22,
                "player_shards": 5,
                "one_short_pos": 25,
                "bonus_target_pos": 26,
                "bonus_target_kind": "S",
            },
        )

    def test_decision_provider_router_prefers_human_policy_attributes_and_human_seats(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionProviderRouter

        class _FakeHumanProvider:
            def __init__(self) -> None:
                self.policy = type("HumanPolicy", (), {"human_only_attr": "human"})()

            def call(self, invocation):  # noqa: ANN001
                return ("human", invocation.method_name, invocation.args, invocation.kwargs)

        class _FakeAiPolicy:
            ai_only_attr = "ai"

        class _FakeAiProvider:
            def __init__(self) -> None:
                self.policy = _FakeAiPolicy()

            def call(self, invocation):  # noqa: ANN001
                return ("ai", invocation.method_name, invocation.args, invocation.kwargs)

        router = _ServerDecisionProviderRouter(
            human_seats=[0],
            human_provider=_FakeHumanProvider(),
            ai_provider=_FakeAiProvider(),
        )

        human_player = type("Player", (), {"player_id": 0})()
        ai_player = type("Player", (), {"player_id": 1})()

        self.assertEqual(getattr(router.attribute_target("human_only_attr"), "human_only_attr"), "human")
        self.assertEqual(getattr(router.attribute_target("ai_only_attr"), "ai_only_attr"), "ai")
        human_invocation = build_decision_invocation("choose_pabal_dice_mode", (object(), human_player), {})
        ai_invocation = build_decision_invocation("choose_pabal_dice_mode", (object(), ai_player), {})
        self.assertEqual(router.provider_for_choice(human_invocation).__class__.__name__, "_FakeHumanProvider")
        self.assertEqual(router.provider_for_choice(ai_invocation).__class__.__name__, "_FakeAiProvider")

    def test_build_decision_invocation_captures_method_and_player_identity(self) -> None:
        player = type("Player", (), {"player_id": 2, "cash": 11})()
        state = type("State", (), {"rounds_completed": 1})()

        invocation = build_decision_invocation(
            "choose_purchase_tile",
            (state, player, 9, "T2", 4),
            {"source": "landing"},
        )

        self.assertEqual(invocation.method_name, "choose_purchase_tile")
        self.assertEqual(invocation.player_id, 2)
        self.assertIs(invocation.player, player)
        self.assertEqual(invocation.args[2], 9)
        self.assertEqual(invocation.kwargs["source"], "landing")

    def test_build_canonical_decision_request_aligns_request_metadata(self) -> None:
        player = type("Player", (), {"player_id": 2, "cash": 11, "position": 8, "shards": 3})()
        state = type("State", (), {"rounds_completed": 1, "turn_index": 3})()
        invocation = build_decision_invocation(
            "choose_purchase_tile",
            (state, player, 9, "T2", 4),
            {"source": "landing"},
        )

        request = build_canonical_decision_request(invocation, fallback_policy="ai")

        self.assertEqual(request.decision_name, "choose_purchase_tile")
        self.assertEqual(request.request_type, "purchase_tile")
        self.assertEqual(request.player_id, 2)
        self.assertEqual(request.round_index, 2)
        self.assertEqual(request.turn_index, 4)
        self.assertEqual(request.public_context["tile_index"], 9)
        self.assertEqual(request.public_context["cost"], 4)
        self.assertEqual(request.fallback_policy, "ai")

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
        self.assertTrue(hasattr(policy_obj, "_gateway"))

    def test_ai_bridge_emits_requested_then_resolved_for_ai_choice(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_purchase_tile(self, state, player, pos, cell, cost, *, source="landing"):  # noqa: ANN001
                del state, player, pos, cell, cost, source
                return False

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 0, "turn_index": 0})()
            player = type("Player", (), {"player_id": 1, "cash": 12, "position": 5, "shards": 4})()
            result = bridge.choose_purchase_tile(state, player, 6, "T2", 4, source="landing")
            self.assertFalse(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "purchase_tile")
            self.assertEqual(resolved.payload.get("choice_id"), "no")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_mark_target_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_mark_target(self, state, player, actor_name):  # noqa: ANN001
                del state, player, actor_name
                return 3

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_mark_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 2})()
            player = type("Player", (), {"player_id": 1, "cash": 9, "position": 12, "shards": 5})()
            result = bridge.choose_mark_target(state, player, "Bandit")
            self.assertEqual(result, 3)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_mark_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "mark_target")
            self.assertEqual(resolved.payload.get("choice_id"), "3")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_active_flip_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_active_flip_card(self, state, player, flippable_cards):  # noqa: ANN001
                del state, player, flippable_cards
                return 7

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_flip_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 20, "position": 0, "shards": 4})()
            result = bridge.choose_active_flip_card(state, player, [1, 7, 8])
            self.assertEqual(result, 7)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_flip_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "active_flip")
            self.assertEqual(resolved.payload.get("choice_id"), "7")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_specific_trick_reward_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeReward:
            def __init__(self, deck_index: int, name: str) -> None:
                self.deck_index = deck_index
                self.name = name

        class _FakeAiPolicy:
            def choose_specific_trick_reward(self, state, player, choices):  # noqa: ANN001
                del state, player
                return choices[1]

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_specific_reward_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 1})()
            player = type("Player", (), {"player_id": 2, "cash": 11, "position": 7, "shards": 4})()
            choices = [_FakeReward(101, "Scout Route"), _FakeReward(102, "Lucky Break")]
            result = bridge.choose_specific_trick_reward(state, player, choices)
            self.assertEqual(getattr(result, "deck_index", None), 102)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_specific_reward_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 3
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "specific_trick_reward")
            self.assertEqual(resolved.payload.get("choice_id"), "102")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_doctrine_relief_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeCandidate:
            def __init__(self, player_id: int) -> None:
                self.player_id = player_id

        class _FakeAiPolicy:
            def choose_doctrine_relief_target(self, state, player, candidates):  # noqa: ANN001
                del state, player, candidates
                return 4

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_doctrine_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 3, "turn_index": 1})()
            player = type("Player", (), {"player_id": 1, "cash": 8, "position": 10, "shards": 2})()
            candidates = [_FakeCandidate(2), _FakeCandidate(4)]
            result = bridge.choose_doctrine_relief_target(state, player, candidates)
            self.assertEqual(result, 4)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_doctrine_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "doctrine_relief")
            self.assertEqual(resolved.payload.get("choice_id"), "4")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_burden_exchange_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeCard:
            burden_cost = 4
            name = "Heavy Burden"

        class _FakeAiPolicy:
            def choose_burden_exchange_on_supply(self, state, player, card):  # noqa: ANN001
                del state, player, card
                return True

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_burden_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 4, "turn_index": 0})()
            player = type("Player", (), {"player_id": 2, "cash": 12, "position": 18, "shards": 3})()
            result = bridge.choose_burden_exchange_on_supply(state, player, _FakeCard())
            self.assertTrue(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_burden_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 3
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "burden_exchange")
            self.assertEqual(resolved.payload.get("choice_id"), "yes")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_runaway_step_choice_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_runaway_slave_step(self, state, player, one_short_pos, bonus_target_pos, bonus_target_kind):  # noqa: ANN001
                del state, player, one_short_pos, bonus_target_pos, bonus_target_kind
                return True

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_runaway_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 5, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 9, "position": 22, "shards": 5})()
            result = bridge.choose_runaway_slave_step(state, player, 25, 26, "S")
            self.assertTrue(result)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_runaway_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "runaway_step_choice")
            self.assertEqual(resolved.payload.get("choice_id"), "yes")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_coin_placement_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_coin_placement_tile(self, state, player):  # noqa: ANN001
                del state, player
                return 18

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_coin_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 5, "turn_index": 2})()
            player = type(
                "Player",
                (),
                {
                    "player_id": 1,
                    "cash": 14,
                    "position": 9,
                    "shards": 4,
                    "visited_owned_tile_indices": [6, 18, 27],
                },
            )()
            result = bridge.choose_coin_placement_tile(state, player)
            self.assertEqual(result, 18)

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_coin_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 2
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "coin_placement")
            self.assertEqual(resolved.payload.get("choice_id"), "18")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_geo_bonus_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_geo_bonus(self, state, player, actor_name):  # noqa: ANN001
                del state, player, actor_name
                return "cash"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_geo_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 6, "turn_index": 3})()
            player = type("Player", (), {"player_id": 3, "cash": 10, "position": 30, "shards": 6})()
            result = bridge.choose_geo_bonus(state, player, "Surveyor")
            self.assertEqual(result, "cash")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_geo_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 4
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "geo_bonus")
            self.assertEqual(resolved.payload.get("choice_id"), "cash")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_ai_bridge_keeps_pabal_dice_mode_on_canonical_decision_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                return "minus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_ai_pabal_bridge_test",
                human_seats=[],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 2, "turn_index": 5})()
            player = type("Player", (), {"player_id": 0, "cash": 9, "position": 12, "shards": 8})()
            result = bridge.choose_pabal_dice_mode(state, player)
            self.assertEqual(result, "minus_one")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_ai_pabal_bridge_test"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event" and msg.payload.get("player_id") == 1
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "ai")
            self.assertEqual(resolved.payload.get("provider"), "ai")
            self.assertEqual(requested.payload.get("request_type"), "pabal_dice_mode")
            self.assertEqual(resolved.payload.get("choice_id"), "minus_one")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

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
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_human_bridge_keeps_pabal_dice_mode_on_prompt_flow(self) -> None:
        from apps.server.src.services.runtime_service import _ServerHumanPolicyBridge

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            class _FakeAiPolicy:
                def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                    del state, player
                    return "plus_one"

            bridge = _ServerHumanPolicyBridge(
                session_id="sess_human_pabal_bridge",
                human_seats=[0],
                ai_fallback=_FakeAiPolicy(),
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 4})()
            player = type("Player", (), {"player_id": 0, "cash": 11, "position": 8, "shards": 8})()
            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge.choose_pabal_dice_mode(state, player)

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_prompt = next(iter(self.prompt_service._pending.values()), None)  # type: ignore[attr-defined]
                if pending_prompt:
                    break
                time.sleep(0.01)

            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None
            self.assertEqual(pending_prompt.payload["request_type"], "pabal_dice_mode")
            self.assertEqual(pending_prompt.payload["player_id"], 1)

            decision_state = self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": "minus_one",
                }
            )
            self.assertEqual(decision_state["status"], "accepted")

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "minus_one")

            published = asyncio.run_coroutine_threadsafe(
                self.stream_service.snapshot("sess_human_pabal_bridge"),
                loop,
            ).result(timeout=2.0)
            bridge_events = [
                msg
                for msg in published
                if msg.type == "event"
                and (
                    msg.payload.get("request_type") == "pabal_dice_mode"
                    or msg.payload.get("request_id") == pending_prompt.request_id
                )
            ]
            requested = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_requested"), None)
            resolved = next((msg for msg in bridge_events if msg.payload.get("event_type") == "decision_resolved"), None)
            self.assertIsNotNone(requested)
            self.assertIsNotNone(resolved)
            self.assertLess(requested.seq, resolved.seq)
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
            self.assertEqual(requested.payload.get("request_type"), "pabal_dice_mode")
            self.assertEqual(resolved.payload.get("choice_id"), "minus_one")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_mixed_bridge_routes_human_seat_choice_through_human_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls = 0

            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                self.calls += 1
                return "plus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_mixed_human_provider",
                human_seats=[0],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 0})()
            player = type("Player", (), {"player_id": 0, "cash": 10, "position": 3, "shards": 4})()
            result: dict[str, str] = {}

            def _run_wait() -> None:
                result["choice"] = bridge.choose_pabal_dice_mode(state, player)

            wait_thread = threading.Thread(target=_run_wait, daemon=True)
            wait_thread.start()

            pending_prompt = None
            for _ in range(100):
                with self.prompt_service._lock:  # type: ignore[attr-defined]
                    pending_prompt = next(iter(self.prompt_service._pending.values()), None)  # type: ignore[attr-defined]
                if pending_prompt is not None:
                    break
                time.sleep(0.01)

            self.assertIsNotNone(pending_prompt)
            assert pending_prompt is not None
            self.prompt_service.submit_decision(
                {
                    "request_id": pending_prompt.request_id,
                    "player_id": 1,
                    "choice_id": "minus_one",
                }
            )

            wait_thread.join(timeout=2.0)
            self.assertEqual(result.get("choice"), "minus_one")
            self.assertEqual(ai_policy.calls, 0)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=1.0)
            loop.close()

    def test_mixed_bridge_routes_non_human_seat_choice_through_ai_provider(self) -> None:
        from apps.server.src.services.runtime_service import _ServerDecisionPolicyBridge

        class _FakeAiPolicy:
            def __init__(self) -> None:
                self.calls = 0

            def choose_pabal_dice_mode(self, state, player):  # noqa: ANN001
                del state, player
                self.calls += 1
                return "minus_one"

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            ai_policy = _FakeAiPolicy()
            bridge = _ServerDecisionPolicyBridge(
                session_id="sess_mixed_ai_provider",
                human_seats=[0],
                ai_fallback=ai_policy,
                prompt_service=self.prompt_service,
                stream_service=self.stream_service,
                loop=loop,
                touch_activity=lambda _session_id: None,
                fallback_executor=self.runtime_service.execute_prompt_fallback,
            )

            state = type("State", (), {"rounds_completed": 1, "turn_index": 1})()
            ai_player = type("Player", (), {"player_id": 1, "cash": 9, "position": 6, "shards": 5})()
            choice = bridge.choose_pabal_dice_mode(state, ai_player)

            self.assertEqual(choice, "minus_one")
            self.assertEqual(ai_policy.calls, 1)
            with self.prompt_service._lock:  # type: ignore[attr-defined]
                self.assertEqual(len(self.prompt_service._pending), 0)  # type: ignore[attr-defined]
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
            self.assertEqual(requested.payload.get("provider"), "human")
            self.assertEqual(resolved.payload.get("provider"), "human")
            self.assertEqual(timeout_event.payload.get("provider"), "human")
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
