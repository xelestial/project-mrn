from __future__ import annotations

import asyncio
import threading
import unittest
import unittest.mock

from apps.server.src.domain.view_state.projector import project_view_state
from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.realtime_persistence import (
    RedisCommandStore,
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
)
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService
from apps.server.src.services.prompt_timeout_worker import PromptTimeoutWorker


class RedisRealtimeServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_redis = _FakeRedis()
        self.connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-rt", socket_timeout_ms=250),
            client_factory=lambda: self.fake_redis,
        )

    def test_stream_service_uses_redis_backend_for_replay_and_drop_counts(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            game_state_store=game_state,
            command_store=command_store,
            queue_size=2,
            max_buffer=2,
        )

        async def _run() -> None:
            queue = await service.subscribe("s1", "c1")
            await service.publish("s1", "event", {"n": 1})
            await service.publish("s1", "event", {"n": 2})
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "round_index": 1,
                    "turn_index": 3,
                    "snapshot": {"players": [{"player_id": 1}], "board": {"f_value": 7}},
                },
            )
            first = await queue.get()
            second = await queue.get()
            self.assertEqual([first["seq"], second["seq"]], [2, 3])
            snapshot = await service.snapshot("s1")
            self.assertEqual([item.seq for item in snapshot], [2, 3])
            replay = await service.replay_from("s1", 2)
            self.assertEqual([item.seq for item in replay], [3])
            stats = await service.backpressure_stats("s1")
            self.assertGreaterEqual(stats["drop_count"], 1)
            checkpoint = game_state.load_checkpoint("s1")
            self.assertIsNotNone(checkpoint)
            self.assertEqual(checkpoint["latest_seq"], 3)
            self.assertEqual(checkpoint["round_index"], 1)
            self.assertEqual(game_state.load_current_state("s1")["board"]["f_value"], 7)
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "decision_resolved",
                    "request_id": "req_ai_1",
                    "request_type": "movement",
                    "resolution": "accepted",
                    "choice_id": "roll",
                    "provider": "ai",
                    "player_id": 1,
                },
            )
            commands = command_store.list_commands("s1")
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0]["payload"]["request_id"], "req_ai_1")

        asyncio.run(_run())

    def test_game_state_store_commits_transition_state_checkpoint_event_and_offset_together(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)

        game_state.commit_transition(
            "s-commit",
            current_state={
                "schema_version": 1,
                "turn_index": 3,
                "pending_actions": [{"action_id": "a1", "type": "apply_move"}],
                "scheduled_actions": [{"action_id": "s1", "type": "resolve_mark"}],
                "pending_turn_completion": {"player_id": 1},
            },
            checkpoint={
                "schema_version": 1,
                "session_id": "s-commit",
                "latest_event_type": "engine_transition",
                "turn_index": 3,
                "has_snapshot": True,
                "pending_action_count": 1,
                "scheduled_action_count": 1,
                "has_pending_actions": True,
                "has_scheduled_actions": True,
                "has_pending_turn_completion": True,
            },
            view_state={"board": {"turn": 3}},
            command_consumer_name="runtime_wakeup",
            command_seq=9,
            runtime_event_payload={
                "event_type": "engine_transition",
                "status": "idle",
                "turn_index": 3,
            },
            runtime_event_server_time_ms=1234,
        )

        self.assertEqual(game_state.load_current_state("s-commit")["turn_index"], 3)
        self.assertEqual(game_state.load_current_state("s-commit")["pending_actions"][0]["action_id"], "a1")
        self.assertEqual(game_state.load_current_state("s-commit")["scheduled_actions"][0]["action_id"], "s1")
        self.assertEqual(game_state.load_checkpoint("s-commit")["latest_event_type"], "engine_transition")
        self.assertEqual(game_state.load_checkpoint("s-commit")["latest_seq"], 1)
        self.assertTrue(game_state.load_checkpoint("s-commit")["has_pending_actions"])
        self.assertTrue(game_state.load_checkpoint("s-commit")["has_scheduled_actions"])
        self.assertTrue(game_state.load_checkpoint("s-commit")["has_pending_turn_completion"])
        self.assertEqual(game_state.load_view_state("s-commit")["board"]["turn"], 3)
        self.assertEqual(game_state.load_projected_view_state("s-commit", "public")["board"]["turn"], 3)
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", "s-commit"), 9)
        runtime_events = RedisStreamStore(self.connection).snapshot("s-commit")
        self.assertEqual(len(runtime_events), 1)
        self.assertEqual(runtime_events[0]["seq"], 1)
        self.assertEqual(runtime_events[0]["payload"]["event_type"], "engine_transition")
        self.assertIn(
            ["set", "set", "set", "set", "hset", "hset", "xadd"],
            self.fake_redis.pipeline_executions,
        )

    def test_game_state_store_commits_module_prompt_resume_snapshot_atomically(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        active_prompt = {
            "request_id": "s1:r1:t2:p1:trick:4",
            "prompt_instance_id": 4,
            "resume_token": "resume_trick",
            "frame_id": "seq:trick:1:p0",
            "module_id": "mod:trick_sequence:1:p0:choice",
            "module_type": "TrickChoiceModule",
            "module_cursor": "await_trick_prompt",
            "player_id": 0,
            "request_type": "trick",
            "legal_choices": [{"choice_id": "defer"}, {"choice_id": "use_trick"}],
        }

        game_state.commit_transition(
            "s-module-resume",
            current_state={
                "schema_version": 3,
                "runtime_runner_kind": "module",
                "runtime_active_prompt": active_prompt,
                "runtime_frame_stack": [
                    {
                        "frame_id": "seq:trick:1:p0",
                        "frame_type": "sequence",
                        "active_module_id": "mod:trick_sequence:1:p0:choice",
                    }
                ],
            },
            checkpoint={
                "schema_version": 3,
                "session_id": "s-module-resume",
                "latest_event_type": "prompt_required",
                "waiting_prompt_request_id": "s1:r1:t2:p1:trick:4",
                "runtime_active_prompt": active_prompt,
                "runner_kind": "module",
                "frame_id": "seq:trick:1:p0",
                "module_id": "mod:trick_sequence:1:p0:choice",
                "module_type": "TrickChoiceModule",
                "module_cursor": "await_trick_prompt",
            },
            view_state={"runtime": {"active_module_cursor": "await_trick_prompt"}},
            command_consumer_name="runtime_wakeup",
            command_seq=11,
            runtime_event_payload={
                "event_type": "prompt_required",
                "request_id": "s1:r1:t2:p1:trick:4",
                "module_id": "mod:trick_sequence:1:p0:choice",
            },
            runtime_event_server_time_ms=2345,
        )

        saved_state = game_state.load_current_state("s-module-resume")
        saved_checkpoint = game_state.load_checkpoint("s-module-resume")
        self.assertEqual(saved_state["runtime_active_prompt"]["resume_token"], "resume_trick")
        self.assertEqual(saved_state["runtime_active_prompt"]["module_cursor"], "await_trick_prompt")
        self.assertEqual(saved_checkpoint["runtime_active_prompt"]["resume_token"], "resume_trick")
        self.assertEqual(saved_checkpoint["module_cursor"], "await_trick_prompt")
        self.assertEqual(saved_checkpoint["latest_seq"], 1)
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", "s-module-resume"), 11)
        runtime_events = RedisStreamStore(self.connection).snapshot("s-module-resume")
        self.assertEqual(runtime_events[-1]["payload"]["request_id"], "s1:r1:t2:p1:trick:4")
        self.assertIn(
            ["set", "set", "set", "set", "hset", "hset", "xadd"],
            self.fake_redis.pipeline_executions,
        )

    def test_game_state_store_saves_view_state_projection_variants(self) -> None:
        game_state = RedisGameStateStore(self.connection)

        game_state.save_view_state("s-view", {"board": {"turn": 1}})
        game_state.save_projected_view_state("s-view", "spectator", {"board": {"turn": 2}})
        game_state.save_projected_view_state("s-view", "player", {"prompt": {"active": {"request_id": "r1"}}}, player_id=1)
        game_state.save_projected_view_state("s-view", "admin", {"debug": {"hands": 4}})
        game_state.save_projection_checkpoint(
            "s-view",
            {
                "schema_version": 1,
                "latest_seq": 12,
                "projection_schema_version": 1,
                "projected_viewers": ["public", "spectator", "player:1", "admin"],
            },
        )

        self.assertEqual(game_state.load_view_state("s-view"), {"board": {"turn": 1}})
        self.assertEqual(game_state.load_projected_view_state("s-view", "public"), {"board": {"turn": 1}})
        self.assertEqual(game_state.load_projected_view_state("s-view", "spectator"), {"board": {"turn": 2}})
        self.assertEqual(game_state.load_projected_view_state("s-view", "player", player_id=1)["prompt"]["active"]["request_id"], "r1")
        self.assertEqual(game_state.load_projected_view_state("s-view", "admin"), {"debug": {"hands": 4}})
        self.assertEqual(game_state.load_projection_checkpoint("s-view")["latest_seq"], 12)

        game_state.delete_session_data("s-view")

        self.assertIsNone(game_state.load_view_state("s-view"))
        self.assertIsNone(game_state.load_projected_view_state("s-view", "public"))
        self.assertIsNone(game_state.load_projected_view_state("s-view", "spectator"))
        self.assertIsNone(game_state.load_projected_view_state("s-view", "player", player_id=1))
        self.assertIsNone(game_state.load_projected_view_state("s-view", "admin"))
        self.assertIsNone(game_state.load_projection_checkpoint("s-view"))

    def test_game_state_store_preserves_positions_and_trick_state_in_state_and_projection(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        payload = {
            "event_type": "turn_end_snapshot",
            "round_index": 2,
            "turn_index": 3,
            "engine_checkpoint": {
                "schema_version": 1,
                "rounds_completed": 1,
                "turn_index": 3,
                "players": [
                    {
                        "player_id": 1,
                        "position": 7,
                        "trick_hand": [101, 202],
                        "hidden_trick_deck_index": 202,
                        "trick_obstacle_this_round": True,
                        "trick_reroll_budget_this_turn": 1,
                    }
                ],
            },
            "snapshot": {
                "players": [
                    {
                        "player_id": 1,
                        "display_name": "P1",
                        "alive": True,
                        "position": 7,
                        "public_tricks": ["땅도둑"],
                        "hidden_trick_count": 1,
                        "trick_count": 2,
                    }
                ],
                "board": {
                    "f_value": 9,
                    "marker_owner_player_id": 1,
                    "marker_draft_direction": "clockwise",
                    "tiles": [
                        {"tile_index": 0, "score_coin_count": 0, "owner_player_id": None, "pawn_player_ids": []},
                        {"tile_index": 7, "score_coin_count": 1, "owner_player_id": 1, "pawn_player_ids": [1]},
                    ],
                },
            },
        }
        message = {
            "seq": 12,
            "type": "event",
            "session_id": "s-state-projection",
            "server_time_ms": 12345,
            "payload": {**payload, "view_state": project_view_state([{"seq": 12, "type": "event", "payload": payload}])},
        }

        game_state.apply_stream_message(message)

        current_state = game_state.load_current_state("s-state-projection")
        view_state = game_state.load_projected_view_state("s-state-projection", "public")
        self.assertIsNotNone(current_state)
        self.assertEqual(current_state["players"][0]["position"], 7)
        self.assertEqual(current_state["players"][0]["trick_hand"], [101, 202])
        self.assertEqual(current_state["players"][0]["hidden_trick_deck_index"], 202)
        self.assertTrue(current_state["players"][0]["trick_obstacle_this_round"])
        self.assertEqual(current_state["players"][0]["trick_reroll_budget_this_turn"], 1)
        self.assertIsNotNone(view_state)
        self.assertEqual(view_state["players"]["items"][0]["public_tricks"], ["땅도둑"])
        self.assertEqual(view_state["players"]["items"][0]["hidden_trick_count"], 1)
        self.assertEqual(view_state["players"]["items"][0]["trick_count"], 2)
        self.assertEqual(view_state["board"]["tiles"][1]["pawn_player_ids"], [1])
        self.assertEqual(view_state["board"]["tiles"][1]["owner_player_id"], 1)

    def test_prompt_service_uses_redis_store_for_decision_flow(self) -> None:
        command_store = RedisCommandStore(self.connection)
        service = PromptService(prompt_store=RedisPromptStore(self.connection), command_store=command_store)
        service.create_prompt(
            "s1",
            {
                "request_id": "r1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )

        def _submit() -> None:
            service.submit_decision({"request_id": "r1", "player_id": 1, "choice_id": "roll"})

        thread = threading.Thread(target=_submit, daemon=True)
        thread.start()
        decision = service.wait_for_decision("r1", timeout_ms=1000)
        thread.join(timeout=1.0)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["choice_id"], "roll")
        replayed = service.wait_for_decision("r1", timeout_ms=1)
        self.assertIsNotNone(replayed)
        self.assertEqual(replayed["choice_id"], "roll")
        self.assertFalse(service.has_pending_for_session("s1"))
        commands = command_store.list_commands("s1")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["type"], "decision_submitted")
        self.assertEqual(commands[0]["payload"]["choice_id"], "roll")

    def test_prompt_service_accepts_decision_with_single_redis_transaction(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        service = PromptService(prompt_store=prompt_store, command_store=command_store)
        service.create_prompt(
            "s-atomic",
            {
                "request_id": "r-atomic",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )

        result = service.submit_decision({"request_id": "r-atomic", "player_id": 1, "choice_id": "roll"})

        self.assertEqual(result["status"], "accepted")
        self.assertIsNone(prompt_store.get_pending("r-atomic"))
        self.assertEqual(prompt_store.get_resolved("r-atomic")["reason"], "accepted")
        self.assertEqual(prompt_store.pop_decision("r-atomic")["choice_id"], "roll")
        commands = command_store.list_commands("s-atomic")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["payload"]["request_id"], "r-atomic")
        self.assertIn(
            [
                "hdel",
                "hset",
                "hset",
                "xadd",
            ],
            self.fake_redis.pipeline_executions,
        )

    def test_prompt_service_supersedes_older_redis_pending_prompt_for_same_player(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        service = PromptService(prompt_store=prompt_store)
        service.create_prompt(
            "s-supersede",
            {
                "request_id": "r-old-p1",
                "request_type": "trick_to_use",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )
        service.create_prompt(
            "s-supersede",
            {
                "request_id": "r-keep-p2",
                "request_type": "movement",
                "player_id": 2,
                "timeout_ms": 30000,
            },
        )

        service.create_prompt(
            "s-supersede",
            {
                "request_id": "r-new-p1",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "timeout_ms": 30000,
            },
        )

        self.assertIsNone(prompt_store.get_pending("r-old-p1"))
        self.assertEqual(prompt_store.get_resolved("r-old-p1")["reason"], "superseded")
        self.assertIsNotNone(prompt_store.get_pending("r-new-p1"))
        self.assertIsNotNone(prompt_store.get_pending("r-keep-p2"))
        pending_ids = {item["request_id"] for item in prompt_store.list_pending()}
        self.assertEqual(pending_ids, {"r-new-p1", "r-keep-p2"})
        self.assertTrue(service.has_pending_for_session("s-supersede"))

    def test_prompt_timeout_worker_emits_timeout_once(self) -> None:
        command_store = RedisCommandStore(self.connection)
        stream_service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            command_store=command_store,
        )
        prompt_store = RedisPromptStore(self.connection)
        prompt_service = PromptService(prompt_store=prompt_store, command_store=command_store)
        sessions = SessionService()
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=prompt_service,
            runtime_state_store=RedisRuntimeStateStore(self.connection),
        )
        worker = PromptTimeoutWorker(
            prompt_service=prompt_service,
            runtime_service=runtime,
            stream_service=stream_service,
        )
        prompt_service.create_prompt(
            "s-timeout",
            {
                "request_id": "req_timeout_1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 1,
                "legal_choices": [
                    {"choice_id": "dice", "title": "Roll dice"},
                    {"choice_id": "card_1", "title": "Use card 1"},
                ],
                "public_context": {"round_index": 1, "turn_index": 1},
            },
        )

        async def _run() -> None:
            first = await worker.run_once(now_ms=10**15, session_id="s-timeout")
            second = await worker.run_once(now_ms=10**15 + 1, session_id="s-timeout")
            snapshot = await stream_service.snapshot("s-timeout")
            event_types = [msg.payload.get("event_type") for msg in snapshot if msg.type == "event"]
            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
            self.assertIn("decision_resolved", event_types)
            self.assertIn("decision_timeout_fallback", event_types)
            commands = command_store.list_commands("s-timeout")
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0]["type"], "decision_submitted")
            self.assertEqual(commands[0]["payload"]["request_id"], "req_timeout_1")
            self.assertEqual(commands[0]["payload"]["choice_id"], "dice")
            decision = prompt_store.get_decision("req_timeout_1")
            self.assertIsNotNone(decision)
            self.assertEqual(decision["choice_id"], "dice")
            self.assertEqual(decision["provider"], "timeout_fallback")

        asyncio.run(_run())

    def test_runtime_service_persists_status_and_fallbacks_to_redis_store(self) -> None:
        sessions = SessionService()
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection))
        prompt_service = PromptService(prompt_store=RedisPromptStore(self.connection))
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=prompt_service,
            runtime_state_store=RedisRuntimeStateStore(self.connection),
        )
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        asyncio.run(
            runtime.execute_prompt_fallback(
                session_id=session.session_id,
                request_id="req_timeout_rt",
                player_id=2,
                fallback_policy="timeout_fallback",
                prompt_payload={"fallback_choice_id": "choice_default"},
            )
        )
        status = runtime.runtime_status(session.session_id)
        self.assertEqual(status["recent_fallbacks"][-1]["request_id"], "req_timeout_rt")

        runtime._status[session.session_id] = {"status": "running", "watchdog_state": "ok", "started_at_ms": 123}
        runtime._touch_activity(session.session_id)
        persisted = runtime.runtime_status(session.session_id)
        self.assertEqual(persisted["status"], "running")
        self.assertEqual(persisted.get("worker_id", "").startswith("runtime_"), True)
        self.assertGreater(int(persisted.get("lease_expires_at_ms", 0)), int(persisted.get("last_activity_ms", 0)))

    def test_runtime_lease_prevents_duplicate_runtime_start(self) -> None:
        sessions = SessionService()
        store = RedisRuntimeStateStore(self.connection)
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection))
        prompt_service = PromptService(prompt_store=RedisPromptStore(self.connection))
        first = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=prompt_service,
            runtime_state_store=store,
        )
        second = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=prompt_service,
            runtime_state_store=store,
        )
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        self.assertTrue(first._acquire_runtime_lease(session.session_id))
        self.assertFalse(second._acquire_runtime_lease(session.session_id))
        status = second.runtime_status(session.session_id)
        self.assertNotEqual(store.lease_owner(session.session_id), second._worker_id)
        self.assertTrue(first._release_runtime_lease(session.session_id))

    def test_runtime_recovery_checkpoint_survives_service_reconstruction(self) -> None:
        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        stream_service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            game_state_store=game_state,
        )
        prompt_service = PromptService(prompt_store=RedisPromptStore(self.connection))
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)

        async def _seed_checkpoint() -> None:
            await stream_service.publish(
                session.session_id,
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "round_index": 2,
                    "turn_index": 5,
                    "snapshot": {"schema_version": 1, "turn": 5, "players": [{"player_id": 1}]},
                },
            )

        asyncio.run(_seed_checkpoint())
        restored_runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=prompt_service,
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )

        recovery = restored_runtime.recovery_checkpoint(session.session_id)
        status = restored_runtime.runtime_status(session.session_id)

        self.assertTrue(recovery["available"])
        self.assertEqual(recovery["checkpoint"]["turn_index"], 5)
        self.assertEqual(recovery["current_state"]["turn"], 5)
        self.assertEqual(status["status"], "recovery_required")
        self.assertTrue(status["recovery_checkpoint"]["available"])

    def test_runtime_recovery_transition_persists_hydrated_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from state import GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        state.f_value = 15.0
        state.current_round_order = []
        state.turn_index = 7
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 11,
                "latest_event_type": "turn_end_snapshot",
                "round_index": 2,
                "turn_index": 7,
                "has_snapshot": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["status"], "finished")
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["f_value"], 15.0)
        self.assertEqual(saved_state["turn_index"], 7)
        self.assertEqual(saved_checkpoint["latest_event_type"], "engine_transition")
        self.assertEqual(saved_checkpoint["turn_index"], 7)
        self.assertTrue(saved_checkpoint["has_snapshot"])

    def test_runtime_recovery_drains_pending_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = 1
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_move_1",
                type="apply_move",
                actor_player_id=0,
                source="recovery_test",
                payload={
                    "target_pos": 5,
                    "lap_credit": False,
                    "schedule_arrival": False,
                    "emit_move_event": True,
                    "move_event_type": "action_move",
                    "trigger": "recovery_test",
                },
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "apply_move")
        self.assertEqual(saved_state["players"][0]["position"], 5)
        self.assertEqual(saved_state["pending_actions"], [])
        self.assertFalse(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 0)

    def test_runtime_recovery_queues_purchase_actions_after_unowned_arrival_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_arrival_purchase_split",
                type="resolve_arrival",
                actor_player_id=0,
                source="recovery_unowned_arrival",
                payload={"trigger": "recovery_unowned_arrival"},
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_arrival")
        self.assertEqual(saved_state["tiles"][tile_index]["owner_id"], None)
        self.assertEqual([action["type"] for action in saved_state["pending_actions"]], ["request_purchase_tile", "resolve_unowned_post_purchase"])
        self.assertTrue(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 2)
        self.assertEqual(saved_checkpoint["pending_action_types"], ["request_purchase_tile", "resolve_unowned_post_purchase"])
        self.assertEqual(saved_checkpoint["next_action_type"], "request_purchase_tile")

    def test_runtime_recovery_keeps_purchase_action_queued_when_prompt_waits(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        prompt_store = RedisPromptStore(self.connection)
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=PromptService(prompt_store=prompt_store),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_purchase_prompt",
                type="request_purchase_tile",
                actor_player_id=0,
                source="landing_purchase",
                payload={
                    "tile_index": tile_index,
                    "purchase_source": "landing_purchase",
                    "record_landing_result": True,
                },
            ),
            ActionEnvelope(
                action_id="resume_purchase_post",
                type="resolve_unowned_post_purchase",
                actor_player_id=0,
                source="landing_post_purchase",
                payload={"tile_index": tile_index},
            ),
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 2,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        async def _run() -> dict:
            return await asyncio.to_thread(
                runtime._run_engine_transition_once_sync,
                asyncio.get_running_loop(),
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

        step = asyncio.run(_run())
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)
        pending_prompts = [item for item in prompt_store.list_pending() if item.get("session_id") == session.session_id]

        self.assertEqual(step["status"], "waiting_input")
        self.assertEqual([action["type"] for action in saved_state["pending_actions"]], ["request_purchase_tile", "resolve_unowned_post_purchase"])
        self.assertEqual(saved_state["tiles"][tile_index]["owner_id"], None)
        self.assertEqual(len(pending_prompts), 1)
        self.assertEqual(pending_prompts[0]["payload"]["request_type"], "purchase_tile")
        self.assertEqual(saved_checkpoint["latest_event_type"], "prompt_required")
        self.assertTrue(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 2)

    def test_runtime_recovery_drains_post_purchase_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[0].tiles_owned = 1
        state.tiles[tile_index].owner_id = 0
        state.pending_action_log = {
            "kind": "turn",
            "actor_player_id": 0,
            "segments": [{"start_pos": tile_index, "end_pos": tile_index, "landing": None}],
            "pending_landing_purchase_result": {"type": "PURCHASE", "tile_kind": "T2", "cost": 2},
        }
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_purchase_post_only",
                type="resolve_unowned_post_purchase",
                actor_player_id=0,
                source="landing_post_purchase",
                payload={"tile_index": tile_index},
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_unowned_post_purchase")
        self.assertEqual(saved_state["pending_actions"], [])
        self.assertNotIn("pending_landing_purchase_result", saved_state["pending_action_log"])
        self.assertEqual(saved_state["tiles"][tile_index]["owner_id"], 0)
        self.assertFalse(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 0)
        self.assertEqual(saved_checkpoint["pending_action_types"], [])
        self.assertEqual(saved_checkpoint["next_action_type"], "")

    def test_runtime_recovery_drains_score_token_placement_before_post_purchase(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[0].tiles_owned = 1
        state.players[0].hand_coins = 2
        state.tiles[tile_index].owner_id = 0
        state.pending_action_log = {
            "kind": "turn",
            "actor_player_id": 0,
            "segments": [{"start_pos": tile_index, "end_pos": tile_index, "landing": None}],
            "pending_landing_purchase_result": {"type": "PURCHASE", "tile_kind": "T2", "cost": 2, "placed": None},
        }
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_purchase_score_token",
                type="resolve_score_token_placement",
                actor_player_id=0,
                source="purchase",
                payload={
                    "target": tile_index,
                    "max_place": 1,
                    "source": "purchase",
                    "update_pending_purchase_result": True,
                },
            ),
            ActionEnvelope(
                action_id="resume_purchase_post_after_token",
                type="resolve_unowned_post_purchase",
                actor_player_id=0,
                source="landing_post_purchase",
                payload={"tile_index": tile_index},
            ),
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 2,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_score_token_placement")
        self.assertEqual(saved_state["tiles"][tile_index]["score_coins"], 1)
        self.assertEqual(saved_state["players"][0]["hand_coins"], 1)
        self.assertEqual(saved_state["pending_action_log"]["pending_landing_purchase_result"]["placed"]["amount"], 1)
        self.assertEqual([action["type"] for action in saved_state["pending_actions"]], ["resolve_unowned_post_purchase"])
        self.assertTrue(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 1)
        self.assertEqual(saved_checkpoint["pending_action_types"], ["resolve_unowned_post_purchase"])
        self.assertEqual(saved_checkpoint["next_action_type"], "resolve_unowned_post_purchase")

    def test_runtime_recovery_keeps_score_token_request_queued_when_prompt_waits(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        prompt_store = RedisPromptStore(self.connection)
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=PromptService(prompt_store=prompt_store),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[0].tiles_owned = 1
        state.players[0].hand_coins = 2
        state.players[0].visited_owned_tile_indices.add(tile_index)
        state.tiles[tile_index].owner_id = 0
        state.pending_action_log = {
            "kind": "turn",
            "actor_player_id": 0,
            "segments": [{"start_pos": tile_index, "end_pos": tile_index, "landing": None}],
        }
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_score_token_prompt",
                type="request_score_token_placement",
                actor_player_id=0,
                source="own_tile_visit",
                payload={
                    "base_event": {"type": "OWN_TILE", "tile_kind": "T2", "coin_gain": 2, "placed": None},
                    "source": "own_tile_visit",
                    "record_arrival_result": True,
                },
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        async def _run() -> dict:
            return await asyncio.to_thread(
                runtime._run_engine_transition_once_sync,
                asyncio.get_running_loop(),
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

        step = asyncio.run(_run())
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)
        pending_prompts = [item for item in prompt_store.list_pending() if item.get("session_id") == session.session_id]

        self.assertEqual(step["status"], "waiting_input")
        self.assertEqual([action["type"] for action in saved_state["pending_actions"]], ["request_score_token_placement"])
        self.assertEqual(saved_state["tiles"][tile_index]["score_coins"], 0)
        self.assertEqual(len(pending_prompts), 1)
        self.assertEqual(pending_prompts[0]["payload"]["request_type"], "coin_placement")
        self.assertEqual(saved_checkpoint["latest_event_type"], "prompt_required")
        self.assertTrue(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 1)
        self.assertEqual(saved_checkpoint["pending_action_types"], ["request_score_token_placement"])
        self.assertEqual(saved_checkpoint["next_action_type"], "request_score_token_placement")

    def test_runtime_recovery_drains_trick_tile_rent_modifier_from_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[0].tiles_owned = 1
        state.tile_owner[tile_index] = 0
        state.tiles[tile_index].owner_id = 0
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_trick_rent_double",
                type="resolve_trick_tile_rent_modifier",
                actor_player_id=0,
                source="trick_tile_rent_modifier",
                payload={
                    "card_name": "긴장감 조성",
                    "target_scope": "owned",
                    "selection_mode": "owned_highest",
                    "modifier_kind": "rent_double",
                },
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_trick_tile_rent_modifier")
        self.assertEqual(saved_state["tile_rent_modifiers_this_turn"][str(tile_index)], 2)
        self.assertEqual(saved_state["pending_actions"], [])
        self.assertFalse(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 0)

    def test_runtime_recovery_keeps_trick_tile_rent_modifier_queued_when_prompt_waits(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        prompt_store = RedisPromptStore(self.connection)
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=PromptService(prompt_store=prompt_store),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[0].tiles_owned = 1
        state.tile_owner[tile_index] = 0
        state.tiles[tile_index].owner_id = 0
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_trick_rent_prompt",
                type="resolve_trick_tile_rent_modifier",
                actor_player_id=0,
                source="trick_tile_rent_modifier",
                payload={
                    "card_name": "긴장감 조성",
                    "target_scope": "owned",
                    "selection_mode": "owned_highest",
                    "modifier_kind": "rent_double",
                },
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        async def _run() -> dict:
            return await asyncio.to_thread(
                runtime._run_engine_transition_once_sync,
                asyncio.get_running_loop(),
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

        step = asyncio.run(_run())
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)
        pending_prompts = [item for item in prompt_store.list_pending() if item.get("session_id") == session.session_id]

        self.assertEqual(step["status"], "waiting_input")
        self.assertEqual([action["type"] for action in saved_state["pending_actions"]], ["resolve_trick_tile_rent_modifier"])
        self.assertEqual(saved_state["tile_rent_modifiers_this_turn"], {})
        self.assertEqual(len(pending_prompts), 1)
        self.assertEqual(pending_prompts[0]["payload"]["request_type"], "trick_tile_target")
        self.assertEqual(saved_checkpoint["latest_event_type"], "prompt_required")
        self.assertTrue(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 1)
        self.assertEqual(saved_checkpoint["pending_action_types"], ["resolve_trick_tile_rent_modifier"])
        self.assertEqual(saved_checkpoint["next_action_type"], "resolve_trick_tile_rent_modifier")

    def test_runtime_recovery_drains_rent_post_landing_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.players[1].position = tile_index
        state.players[0].cash = 10
        state.players[0].trick_same_tile_cash2_this_turn = True
        state.tiles[tile_index].owner_id = 1
        state.players[1].tiles_owned = 1
        state.pending_action_log = {
            "kind": "turn",
            "actor_player_id": 0,
            "segments": [{"start_pos": tile_index, "end_pos": tile_index, "landing": None}],
        }
        state.pending_actions = [
            ActionEnvelope(
                action_id="resume_rent_post_only",
                type="resolve_landing_post_effects",
                actor_player_id=0,
                source="rent_post_landing",
                payload={
                    "tile_index": tile_index,
                    "base_event": {"type": "RENT", "tile_kind": "T2", "owner": 2, "rent": 2, "paid": True, "amount": 2},
                    "require_paid_for_adjacent": True,
                },
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "pending_action_count": 1,
                "has_pending_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_landing_post_effects")
        self.assertEqual(saved_state["pending_actions"], [])
        self.assertEqual(saved_state["players"][0]["cash"], 12)
        self.assertFalse(saved_checkpoint["has_pending_actions"])
        self.assertEqual(saved_checkpoint["pending_action_count"], 0)

    def test_runtime_recovery_materializes_scheduled_turn_start_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        state.current_round_order = [1, 0]
        state.turn_index = 0
        state.players[0].shards = 4
        state.players[1].cash = 12
        mark = {"type": "bandit_tax", "source_pid": 0}
        state.players[1].pending_marks.append(mark)
        state.scheduled_actions = [
            ActionEnvelope(
                action_id="scheduled_mark_1",
                type="resolve_mark",
                actor_player_id=0,
                source="mark:bandit_tax",
                target_player_id=1,
                phase="turn_start",
                priority=10,
                payload={"mark": dict(mark), "target_player_id": 1},
            )
        ]
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "engine_transition",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "scheduled_action_count": 1,
                "has_scheduled_actions": True,
                "updated_at_ms": 1000,
            },
        )

        step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)
        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["action_type"], "resolve_mark")
        self.assertEqual(saved_state["players"][1]["cash"], 8)
        self.assertEqual(saved_state["players"][1]["pending_marks"], [])
        self.assertEqual(saved_state["scheduled_actions"], [])
        self.assertEqual(saved_checkpoint["scheduled_action_count"], 0)
        self.assertFalse(saved_checkpoint["has_scheduled_actions"])
        self.assertEqual(saved_checkpoint["scheduled_action_types"], [])
        self.assertEqual(saved_checkpoint["next_scheduled_action_type"], "")

    def test_runtime_process_command_once_commits_state_and_command_offset(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from state import GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        stream_service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            game_state_store=game_state,
            command_store=command_store,
        )
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection), command_store=command_store),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
            command_store=command_store,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        state.f_value = 15.0
        state.current_round_order = []
        state.turn_index = 5
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "turn_end_snapshot",
                "round_index": 1,
                "turn_index": 5,
                "has_snapshot": True,
                "updated_at_ms": 1000,
            },
        )

        result = asyncio.run(
            runtime.process_command_once(
                session_id=session.session_id,
                command_seq=4,
                consumer_name="runtime_wakeup",
                seed=42,
            )
        )

        saved_checkpoint = game_state.load_checkpoint(session.session_id)
        runtime_events = RedisStreamStore(self.connection).snapshot(session.session_id)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(saved_checkpoint["processed_command_seq"], 4)
        self.assertEqual(
            saved_checkpoint["command_commit_envelope"],
            {
                "version": 1,
                "atomic_commit": "redis_transition_state_checkpoint_event_offset",
                "consumer": "runtime_wakeup",
                "seq": 4,
                "state": True,
                "checkpoint": True,
                "view_state": False,
                "runtime_event": True,
                "consumer_offset": True,
            },
        )
        self.assertEqual(runtime_events[-1]["seq"], saved_checkpoint["latest_seq"])
        self.assertEqual(runtime_events[-1]["payload"]["event_type"], "engine_transition")
        self.assertEqual(runtime_events[-1]["payload"]["processed_command_seq"], 4)
        self.assertEqual(runtime_events[-1]["payload"]["command_commit_envelope"], saved_checkpoint["command_commit_envelope"])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), 4)

    def test_human_prompt_reentry_consumes_decision_without_duplicate_prompt(self) -> None:
        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        prompt_store = RedisPromptStore(self.connection)
        stream_service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            game_state_store=game_state,
            command_store=command_store,
        )
        prompt_service = PromptService(prompt_store=prompt_store, command_store=command_store)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=prompt_service,
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
            command_store=command_store,
        )

        async def _first_prompt() -> dict:
            return await asyncio.to_thread(
                runtime._run_engine_sync,
                asyncio.get_running_loop(),
                session.session_id,
                42,
                None,
            )

        first = asyncio.run(_first_prompt())
        pending = [item for item in prompt_store.list_pending() if item.get("session_id") == session.session_id]
        self.assertEqual(first["status"], "waiting_input")
        self.assertEqual(len(pending), 1)
        request_id = str(pending[0]["request_id"])
        choices = pending[0]["payload"]["legal_choices"]
        choice_id = str(choices[0]["choice_id"])

        accepted = prompt_service.submit_decision(
            {
                "request_id": request_id,
                "player_id": int(pending[0]["player_id"]),
                "choice_id": choice_id,
            }
        )
        self.assertEqual(accepted["status"], "accepted")
        command = command_store.list_commands(session.session_id)[0]

        second = asyncio.run(
            runtime.process_command_once(
                session_id=session.session_id,
                command_seq=int(command["seq"]),
                consumer_name="runtime_wakeup",
                seed=42,
            )
        )
        messages = asyncio.run(stream_service.snapshot(session.session_id))
        prompt_messages = [msg for msg in messages if msg.type == "prompt" and msg.payload.get("request_id") == request_id]

        self.assertIn(second["status"], {"committed", "waiting_input", "finished"})
        self.assertEqual(prompt_store.get_pending(request_id), None)
        self.assertEqual(len(prompt_messages), 1)
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), int(command["seq"]))

    def test_runtime_recovery_transition_persists_pending_prompt_metadata(self) -> None:
        RuntimeService._ensure_gpt_import_path()
        from state import GameState
        from apps.server.src.services.decision_gateway import PromptRequired

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=StreamService(stream_backend=RedisStreamStore(self.connection), game_state_store=game_state),
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )
        config = runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        state.prompt_sequence = 3
        game_state.save_current_state(session.session_id, state.to_checkpoint_payload())
        game_state.save_checkpoint(
            session.session_id,
            {
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 12,
                "latest_event_type": "turn_end_snapshot",
                "round_index": 1,
                "turn_index": 0,
                "has_snapshot": True,
                "updated_at_ms": 1000,
            },
        )

        def _raise_prompt(_engine, _state):  # noqa: ANN001
            raise PromptRequired(
                {
                    "request_id": "req_prompt_checkpoint",
                    "request_type": "movement",
                    "player_id": 2,
                    "prompt_instance_id": 4,
                }
            )

        with unittest.mock.patch("engine.GameEngine.run_next_transition", _raise_prompt):
            step = runtime._run_engine_transition_once_for_recovery(session.session_id, seed=42)

        saved_state = game_state.load_current_state(session.session_id)
        saved_checkpoint = game_state.load_checkpoint(session.session_id)

        self.assertEqual(step["status"], "waiting_input")
        self.assertEqual(saved_state["prompt_sequence"], 4)
        self.assertEqual(saved_state["pending_prompt_request_id"], "req_prompt_checkpoint")
        self.assertEqual(saved_state["pending_prompt_type"], "movement")
        self.assertEqual(saved_state["pending_prompt_player_id"], 2)
        self.assertEqual(saved_state["pending_prompt_instance_id"], 4)
        self.assertEqual(saved_checkpoint["waiting_prompt_request_id"], "req_prompt_checkpoint")
        self.assertEqual(saved_checkpoint["prompt_sequence"], 4)

    def test_runtime_sync_uses_transition_loop_when_redis_state_store_exists(self) -> None:
        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        stream_service = StreamService(
            stream_backend=RedisStreamStore(self.connection),
            game_state_store=game_state,
        )
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        runtime = RuntimeService(
            session_service=sessions,
            stream_service=stream_service,
            prompt_service=PromptService(prompt_store=RedisPromptStore(self.connection)),
            runtime_state_store=RedisRuntimeStateStore(self.connection),
            game_state_store=game_state,
        )

        with unittest.mock.patch.object(
            runtime,
            "_run_engine_transition_loop_sync",
            return_value={"status": "finished", "transitions": 1},
        ) as transition_loop:
            result = runtime._run_engine_sync(
                unittest.mock.Mock(),
                session.session_id,
                42,
                None,
            )

        self.assertEqual(result, {"status": "finished", "transitions": 1})
        transition_loop.assert_called_once_with(
            unittest.mock.ANY,
            session.session_id,
            42,
            None,
        )


class _FakeRedisPipeline:
    def __init__(self, client: "_FakeRedis") -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def delete(self, *keys: str) -> "_FakeRedisPipeline":
        self._ops.append(("delete", keys, {}))
        return self

    def hset(self, name: str, key=None, value=None, mapping=None) -> "_FakeRedisPipeline":
        self._ops.append(("hset", (name,), {"key": key, "value": value, "mapping": mapping}))
        return self

    def hdel(self, name: str, *keys: str) -> "_FakeRedisPipeline":
        self._ops.append(("hdel", (name, *keys), {}))
        return self

    def set(self, name: str, value: str) -> "_FakeRedisPipeline":
        self._ops.append(("set", (name, value), {}))
        return self

    def xadd(self, name: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = False) -> "_FakeRedisPipeline":
        self._ops.append(("xadd", (name, fields), {"maxlen": maxlen, "approximate": approximate}))
        return self

    def execute(self) -> list[object]:
        results = []
        self._client.pipeline_executions.append([name for name, _, _ in self._ops])
        for name, args, kwargs in self._ops:
            results.append(getattr(self._client, name)(*args, **kwargs))
        self._ops.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._expires_at_ms: dict[str, int] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._lists: dict[str, list[str]] = {}
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.pipeline_executions: list[list[str]] = []

    def ping(self) -> bool:
        return True

    def info(self, section: str | None = None) -> dict[str, object]:
        return {"redis_version": "7.4.8"}

    def close(self) -> None:
        return None

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            self._expires_at_ms.pop(key, None)
            removed += int(self._strings.pop(key, None) is not None)
            removed += int(self._hashes.pop(key, None) is not None)
            removed += int(self._lists.pop(key, None) is not None)
            removed += int(self._streams.pop(key, None) is not None)
        return removed

    def incr(self, key: str) -> int:
        current = int(self._strings.get(key, "0"))
        current += 1
        self._strings[key] = str(current)
        return current

    def hset(self, name: str, key=None, value=None, mapping=None) -> int:
        bucket = self._hashes.setdefault(name, {})
        written = 0
        if mapping is not None:
            for item_key, item_value in mapping.items():
                bucket[str(item_key)] = str(item_value)
                written += 1
            return written
        if key is not None:
            bucket[str(key)] = str(value)
            written += 1
        return written

    def hsetnx(self, name: str, key: str, value: str) -> int:
        bucket = self._hashes.setdefault(name, {})
        if str(key) in bucket:
            return 0
        bucket[str(key)] = str(value)
        return 1

    def hgetall(self, name: str) -> dict[str, str]:
        return dict(self._hashes.get(name, {}))

    def hget(self, name: str, key: str) -> str | None:
        return self._hashes.get(name, {}).get(str(key))

    def hdel(self, name: str, *keys: str) -> int:
        bucket = self._hashes.get(name, {})
        removed = 0
        for key in keys:
            if str(key) in bucket:
                del bucket[str(key)]
                removed += 1
        return removed

    def hincrby(self, name: str, key: str, amount: int) -> int:
        bucket = self._hashes.setdefault(name, {})
        value = int(bucket.get(str(key), "0")) + int(amount)
        bucket[str(key)] = str(value)
        return value

    def set(self, name: str, value: str, nx: bool = False, px: int | None = None) -> bool:
        if nx and name in self._strings:
            return False
        self._strings[name] = str(value)
        if px is not None:
            self._expires_at_ms[name] = int(px)
        return True

    def get(self, name: str) -> str | None:
        return self._strings.get(name)

    def xadd(self, name: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = False) -> str:
        bucket = self._streams.setdefault(name, [])
        entry_id = f"{fields.get('server_time_ms', '0')}-{fields.get('seq', '0')}"
        bucket.append((entry_id, dict(fields)))
        if maxlen is not None and len(bucket) > maxlen:
            del bucket[: len(bucket) - maxlen]
        return entry_id

    def xrange(self, name: str, min: str = "-", max: str = "+", count: int | None = None):
        bucket = list(self._streams.get(name, []))
        if count is not None:
            bucket = bucket[:count]
        return bucket

    def xrevrange(self, name: str, max: str = "+", min: str = "-", count: int | None = None):
        bucket = list(reversed(self._streams.get(name, [])))
        if count is not None:
            bucket = bucket[:count]
        return bucket

    def rpush(self, name: str, *values: str) -> int:
        bucket = self._lists.setdefault(name, [])
        for value in values:
            bucket.append(str(value))
        return len(bucket)

    def ltrim(self, name: str, start: int, stop: int) -> bool:
        bucket = self._lists.setdefault(name, [])
        length = len(bucket)
        if start < 0:
            start = max(0, length + start)
        if stop < 0:
            stop = length + stop
        bucket[:] = bucket[start : stop + 1]
        return True

    def lrange(self, name: str, start: int, stop: int) -> list[str]:
        bucket = self._lists.get(name, [])
        length = len(bucket)
        if start < 0:
            start = max(0, length + start)
        if stop < 0:
            stop = length + stop
        return list(bucket[start : stop + 1])


if __name__ == "__main__":
    unittest.main()
