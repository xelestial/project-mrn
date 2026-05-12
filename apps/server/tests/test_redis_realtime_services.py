from __future__ import annotations

import asyncio
import threading
import unittest
import unittest.mock
from types import SimpleNamespace

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.view_state.projector import project_replay_view_state
from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.command_wakeup_worker import CommandStreamWakeupWorker
from apps.server.src.services.realtime_persistence import (
    RedisCommandStore,
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
    ViewCommitSequenceConflict,
)
from apps.server.src.services.runtime_service import RuntimeDecisionResume, RuntimeService, _runtime_prompt_sequence_seed
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

    def test_runtime_prompt_sequence_seed_prefers_current_pending_prompt_over_prior_resume_debug(self) -> None:
        state = SimpleNamespace(
            prompt_sequence=19,
            pending_prompt_instance_id=19,
            pending_prompt_request_id="sess_1:r3:t9:p1:trick_tile_target:19",
        )
        checkpoint = {
            "decision_resume_request_id": "sess_1:r3:t9:p1:trick_tile_target:18",
            "decision_resume_request_type": "trick_tile_target",
            "decision_resume_player_id": 1,
            "decision_resume_frame_id": "turn:r3:p1",
            "decision_resume_module_id": "mod:trick",
            "decision_resume_module_type": "TrickWindowModule",
            "decision_resume_module_cursor": "await_trick_prompt",
        }
        resume = RuntimeDecisionResume(
            request_id="sess_1:r3:t9:p1:trick_tile_target:19",
            player_id=1,
            request_type="trick_tile_target",
            choice_id="4",
            choice_payload={},
            resume_token="resume_19",
            frame_id="turn:r3:p1",
            module_id="mod:trick",
            module_type="TrickWindowModule",
            module_cursor="await_trick_prompt",
        )

        self.assertEqual(_runtime_prompt_sequence_seed(state, checkpoint, resume), 18)

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
            self.assertEqual([first["type"], second["type"]], ["event", "event"])
            snapshot = await service.snapshot("s1")
            self.assertEqual([item.seq for item in snapshot], [2, 3])
            replay = await service.replay_from("s1", 2)
            self.assertEqual([item.seq for item in replay], [3])
            stats = await service.backpressure_stats("s1")
            self.assertGreaterEqual(stats["drop_count"], 1)
            self.assertIsNone(game_state.load_checkpoint("s1"))
            self.assertIsNone(game_state.load_current_state("s1"))
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

    def test_command_store_lists_recent_commands_and_falls_back_after_gap(self) -> None:
        command_store = RedisCommandStore(self.connection)
        for seq in range(1, 7):
            command_store.append_command(
                "s-command-tail",
                "decision_submitted",
                {"request_id": f"req_{seq}", "choice_id": "roll"},
                request_id=f"req_{seq}",
            )

        recent = command_store.list_recent_commands("s-command-tail", limit=2)
        after_tail = command_store.list_commands_after("s-command-tail", 4, limit=2)
        after_gap = command_store.list_commands_after("s-command-tail", 2, limit=2)

        self.assertEqual([command["seq"] for command in recent], [5, 6])
        self.assertEqual([command["seq"] for command in after_tail], [5, 6])
        self.assertEqual([command["seq"] for command in after_gap], [3, 4, 5, 6])

    def test_stream_event_index_maps_event_id_to_source_sequence(self) -> None:
        stream_store = RedisStreamStore(self.connection)
        service = StreamService(stream_backend=stream_store)

        async def _run() -> None:
            event = await service.publish(
                "s-event-index",
                "event",
                {"event_type": "decision_requested", "request_id": "req_1", "player_id": 2},
            )
            indexed = stream_store.load_event_index("s-event-index", event.payload["event_id"])

            self.assertIsNotNone(indexed)
            self.assertEqual(indexed["event_id"], event.payload["event_id"])
            self.assertEqual(indexed["stream_seq"], event.seq)
            self.assertEqual(indexed["message_type"], "event")
            self.assertEqual(indexed["event_type"], "decision_requested")
            self.assertEqual(indexed["request_id"], "req_1")
            self.assertEqual(indexed["player_id"], 2)

        asyncio.run(_run())
        self.assertEqual(self.fake_redis._expires_at_ms[stream_store._event_index_key("s-event-index")], 3600)

    def test_stream_publish_pipelines_stream_indexes_in_one_round_trip(self) -> None:
        stream_store = RedisStreamStore(self.connection)

        ack = stream_store.publish(
            "s-ack-pipeline",
            "decision_ack",
            {
                "event_id": "evt_ack_1",
                "request_id": "req_ack_1",
                "player_id": 2,
                "status": "accepted",
            },
            server_time_ms=100,
            max_buffer=20,
        )

        self.assertEqual(ack["seq"], 1)
        self.assertEqual(
            self.fake_redis.pipeline_executions,
            [["xadd", "xadd", "hset", "expire", "hset", "expire"]],
        )
        self.assertIsNotNone(stream_store.load_event_index("s-ack-pipeline", "evt_ack_1"))
        self.assertEqual(
            [
                (row["stream_seq"], row["viewer_scope"], row["message_type"])
                for row in stream_store.load_viewer_outbox_index("s-ack-pipeline")
            ],
            [(1, "player:2", "decision_ack")],
        )

    def test_stream_snapshot_replay_and_window_are_sorted_by_sequence(self) -> None:
        stream_store = RedisStreamStore(self.connection)
        stream_key = stream_store._stream_key("s-out-of-order")
        source_key = stream_store._source_stream_key("s-out-of-order")
        later = {
            "seq": "2",
            "type": "decision_ack",
            "session_id": "s-out-of-order",
            "server_time_ms": "100",
            "payload": '{"request_id":"req_2"}',
        }
        earlier = {
            "seq": "1",
            "type": "event",
            "session_id": "s-out-of-order",
            "server_time_ms": "101",
            "payload": '{"event_type":"decision_requested","request_id":"req_1"}',
        }
        self.fake_redis.xadd(stream_key, later)
        self.fake_redis.xadd(stream_key, earlier)
        self.fake_redis.xadd(source_key, later)
        self.fake_redis.xadd(source_key, earlier)

        self.assertEqual([item["seq"] for item in stream_store.snapshot("s-out-of-order")], [1, 2])
        self.assertEqual([item["seq"] for item in stream_store.source_snapshot("s-out-of-order")], [1, 2])
        self.assertEqual([item["seq"] for item in stream_store.replay_from("s-out-of-order", 1)], [2])
        self.assertEqual(stream_store.replay_window("s-out-of-order"), (1, 2))

    def test_stream_viewer_outbox_records_projected_delivery_scope(self) -> None:
        stream_store = RedisStreamStore(self.connection)

        prompt = stream_store.publish(
            "s-outbox",
            "prompt",
            {"request_id": "req_prompt_1", "player_id": 2},
            server_time_ms=100,
            max_buffer=20,
        )
        public = stream_store.publish(
            "s-outbox",
            "event",
            {"event_type": "weather_changed"},
            server_time_ms=101,
            max_buffer=20,
        )
        commit = stream_store.publish(
            "s-outbox",
            "view_commit",
            {
                "commit_seq": 3,
                "viewer": {"role": "seat", "player_id": 4},
                "runtime": {"status": "waiting_input"},
            },
            server_time_ms=102,
            max_buffer=20,
        )

        rows = stream_store.load_viewer_outbox_index("s-outbox")
        self.assertEqual(
            [(row["stream_seq"], row["viewer_scope"], row["message_type"]) for row in rows],
            [
                (prompt["seq"], "player:2", "prompt"),
                (public["seq"], "public", "event"),
                (commit["seq"], "player:4", "view_commit"),
            ],
        )
        self.assertEqual(rows[0]["request_id"], "req_prompt_1")
        self.assertEqual(rows[2]["commit_seq"], 3)
        self.assertEqual(self.fake_redis._expires_at_ms[stream_store._viewer_outbox_index_key("s-outbox")], 3600)

    def test_stream_view_commit_source_records_all_cached_viewer_outbox_scopes(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        stream_store = RedisStreamStore(self.connection)
        service = StreamService(stream_backend=stream_store, game_state_store=game_state)
        base_payload = {
            "schema_version": 1,
            "commit_seq": 4,
            "source_event_seq": 11,
            "runtime": {"status": "running", "round_index": 2, "turn_index": 7},
            "view_state": {"board": {"turn": 7}},
        }

        game_state.save_view_commit(
            "s-outbox-commit",
            {**base_payload, "viewer": {"role": "spectator"}},
            viewer="spectator",
        )
        game_state.save_view_commit(
            "s-outbox-commit",
            {**base_payload, "viewer": {"role": "admin"}},
            viewer="admin",
        )
        game_state.save_view_commit(
            "s-outbox-commit",
            {**base_payload, "viewer": {"role": "seat", "player_id": 1}},
            viewer="player",
            player_id=1,
        )
        game_state.save_view_commit(
            "s-outbox-commit",
            {**base_payload, "viewer": {"role": "seat", "player_id": 2}},
            viewer="player",
            player_id=2,
        )

        async def _run() -> None:
            item = await service.emit_latest_view_commit("s-outbox-commit")
            self.assertIsNotNone(item)

        asyncio.run(_run())

        rows = stream_store.load_viewer_outbox_index("s-outbox-commit")
        self.assertEqual(
            sorted((row["message_type"], row["viewer_scope"], row["commit_seq"]) for row in rows),
            [
                ("view_commit", "admin", 4),
                ("view_commit", "player:1", 4),
                ("view_commit", "player:2", 4),
                ("view_commit", "spectator", 4),
            ],
        )

    def test_stream_store_persists_compact_view_commit_pointer_only(self) -> None:
        stream_store = RedisStreamStore(self.connection)
        full_payload = {
            "commit_seq": 7,
            "source_event_seq": 42,
            "viewer": {"role": "seat", "player_id": 3, "viewer_id": "viewer_3"},
            "runtime": {
                "status": "waiting_input",
                "round_index": 2,
                "turn_index": 5,
                "turn_label": "R2-T5",
                "active_module_id": "module_1",
                "active_prompt": {
                    "request_id": "req_1",
                    "prompt_instance_id": "prompt_1",
                    "player_id": 3,
                    "request_type": "movement",
                    "view_commit_seq": 7,
                    "legal_choices": [{"choice_id": "roll"}],
                },
            },
            "view_state": {"large": "x" * 1024},
        }

        returned = stream_store.publish(
            "s-compact-view-commit",
            "view_commit",
            full_payload,
            server_time_ms=123,
            max_buffer=20,
        )
        persisted = stream_store.snapshot("s-compact-view-commit")

        self.assertEqual(returned["payload"]["view_state"], full_payload["view_state"])
        self.assertEqual(persisted[0]["payload"]["commit_seq"], 7)
        self.assertEqual(persisted[0]["payload"]["source_event_seq"], 42)
        self.assertEqual(persisted[0]["payload"]["viewer"]["player_id"], 3)
        self.assertEqual(persisted[0]["payload"]["runtime"]["active_prompt"]["request_id"], "req_1")
        self.assertTrue(persisted[0]["payload"]["compact"])
        self.assertNotIn("view_state", persisted[0]["payload"])
        self.assertNotIn("legal_choices", persisted[0]["payload"]["runtime"]["active_prompt"])

    def test_game_state_debug_snapshot_uses_one_hour_ttl(self) -> None:
        game_state = RedisGameStateStore(self.connection)

        game_state.save_debug_snapshot("s-debug-ttl", {"schema_version": 1})

        self.assertEqual(self.fake_redis._expires_at_ms[game_state._debug_snapshot_key("s-debug-ttl")], 3600000)

    def test_game_state_debug_snapshot_includes_stream_index_summary(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        stream_store = RedisStreamStore(self.connection)
        stream_service = StreamService(stream_backend=stream_store)

        async def _run() -> None:
            decision_event = await stream_service.publish(
                "s-debug-stream",
                "event",
                {
                    "event_type": "decision_requested",
                    "request_id": "req_debug_1",
                    "player_id": 2,
                    "target_player_id": 3,
                },
            )
            prompt_event = await stream_service.publish(
                "s-debug-stream",
                "prompt",
                {
                    "request_id": "req_prompt_1",
                    "player_id": 2,
                    "resume_token": "resume_debug_1",
                    "frame_id": "turn:1:2",
                    "module_id": "module_debug_1",
                    "module_type": "DebugPromptModule",
                    "module_cursor": "await_debug_choice",
                },
            )
            game_state.save_checkpoint(
                "s-debug-stream",
                {
                    "schema_version": 1,
                    "session_id": "s-debug-stream",
                    "latest_seq": prompt_event.seq,
                    "latest_source_event_seq": decision_event.seq,
                    "latest_event_type": "prompt",
                },
            )

        asyncio.run(_run())

        debug_snapshot = game_state.load_debug_snapshot("s-debug-stream")
        self.assertIsNotNone(debug_snapshot)
        stream = debug_snapshot["stream"]
        self.assertEqual(stream["stream_seq"], 2)
        self.assertEqual(stream["event_index_count"], 2)
        self.assertEqual(stream["viewer_outbox_count"], 2)
        self.assertEqual(stream["event_index_ttl_seconds"], 3600)
        self.assertEqual(stream["viewer_outbox_ttl_seconds"], 3600)
        self.assertEqual(
            [(item["message_type"], item.get("event_type"), item.get("request_id")) for item in stream["latest_event_index"]],
            [
                ("event", "decision_requested", "req_debug_1"),
                ("prompt", "", "req_prompt_1"),
            ],
        )
        self.assertEqual(
            [(item["message_type"], item["viewer_scope"], item.get("request_id")) for item in stream["latest_viewer_outbox"]],
            [
                ("event", "public", "req_debug_1"),
                ("prompt", "player:2", "req_prompt_1"),
            ],
        )

    def test_prompt_lifecycle_store_is_session_scoped_and_cleaned(self) -> None:
        prompt_store = RedisPromptStore(self.connection)

        prompt_store.save_lifecycle(
            "req_lifecycle_1",
            {"request_id": "req_lifecycle_1", "session_id": "s-lifecycle", "state": "created"},
        )
        prompt_store.save_lifecycle(
            "req_lifecycle_2",
            {"request_id": "req_lifecycle_2", "session_id": "other", "state": "created"},
        )

        self.assertEqual(prompt_store.get_lifecycle("req_lifecycle_1")["state"], "created")
        self.assertEqual(
            [item["request_id"] for item in prompt_store.list_lifecycle("s-lifecycle")],
            ["req_lifecycle_1"],
        )

        prompt_store.delete_session_data("s-lifecycle")

        self.assertIsNone(prompt_store.get_lifecycle("req_lifecycle_1"))
        self.assertIsNotNone(prompt_store.get_lifecycle("req_lifecycle_2"))

    def test_prompt_debug_index_tracks_session_prompt_state_with_one_hour_ttl(self) -> None:
        prompt_store = RedisPromptStore(self.connection)

        prompt_store.save_pending(
            "req_debug_prompt_1",
            {
                "request_id": "req_debug_prompt_1",
                "session_id": "s-prompt-debug",
                "player_id": 2,
                "request_type": "trick_choice",
                "resume_token": "resume_prompt_debug",
                "legal_choices": [{"choice_id": "a"}, {"choice_id": "b"}],
                "created_at_ms": 100,
            },
        )
        prompt_store.save_lifecycle(
            "req_debug_prompt_1",
            {
                "request_id": "req_debug_prompt_1",
                "session_id": "s-prompt-debug",
                "state": "delivered",
                "updated_at_ms": 110,
            },
        )

        debug_index = prompt_store.load_debug_index("s-prompt-debug")

        self.assertIsNotNone(debug_index)
        self.assertEqual(debug_index["counts"]["pending"], 1)
        self.assertEqual(debug_index["counts"]["lifecycle"], 1)
        self.assertEqual(debug_index["active_prompt"]["request_id"], "req_debug_prompt_1")
        self.assertEqual(debug_index["active_prompt"]["legal_choice_count"], 2)
        self.assertTrue(debug_index["active_prompt"]["resume_token_present"])
        self.assertEqual(
            self.fake_redis._expires_at_ms[prompt_store._debug_index_key("s-prompt-debug")],
            3600000,
        )
        self.assertNotIn(prompt_store._pending_key(), self.fake_redis._expires_at_ms)

        prompt_store.delete_pending("req_debug_prompt_1", session_id="s-prompt-debug")

        debug_index = prompt_store.load_debug_index("s-prompt-debug")
        self.assertEqual(debug_index["counts"]["pending"], 0)
        self.assertEqual(debug_index["counts"]["lifecycle"], 1)

    def test_prompt_debug_index_refresh_uses_session_buckets(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        prompt_store.save_pending(
            "req_debug_bucket_1",
            {
                "request_id": "req_debug_bucket_1",
                "session_id": "s-prompt-bucket",
                "player_id": 1,
                "request_type": "movement",
                "created_at_ms": 100,
            },
        )

        self.fake_redis.hgetall_calls.clear()
        prompt_store.save_lifecycle(
            "req_debug_bucket_1",
            {
                "request_id": "req_debug_bucket_1",
                "session_id": "s-prompt-bucket",
                "state": "delivered",
                "updated_at_ms": 110,
            },
        )

        self.assertNotIn(prompt_store._pending_key(), self.fake_redis.hgetall_calls)
        self.assertNotIn(prompt_store._resolved_key(), self.fake_redis.hgetall_calls)
        self.assertNotIn(prompt_store._decisions_key(), self.fake_redis.hgetall_calls)
        self.assertNotIn(prompt_store._lifecycle_key(), self.fake_redis.hgetall_calls)
        debug_index = prompt_store.load_debug_index("s-prompt-bucket")
        self.assertEqual(debug_index["counts"]["pending"], 1)
        self.assertEqual(debug_index["counts"]["lifecycle"], 1)

    def test_session_scoped_prompt_lookup_does_not_scan_global_hash(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        prompt_store.save_decision(
            "req_scoped_lookup",
            {
                "request_id": "req_scoped_lookup",
                "session_id": "s-scoped-lookup",
                "choice_id": "roll",
            },
        )

        self.fake_redis.hgetall_calls.clear()

        self.assertEqual(
            prompt_store.get_decision("req_scoped_lookup", session_id="s-scoped-lookup")["choice_id"],
            "roll",
        )
        self.assertIsNone(prompt_store.get_decision("missing", session_id="s-scoped-lookup"))
        self.assertEqual(self.fake_redis.hgetall_calls, [])

        self.assertEqual(prompt_store.get_decision("req_scoped_lookup")["choice_id"], "roll")
        self.assertIn(prompt_store._decisions_key(), self.fake_redis.hgetall_calls)

    def test_prompt_pending_records_three_hour_orphan_expiry_without_redis_ttl(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        service = PromptService(prompt_store=prompt_store)
        created_at_ms = 1_000
        orphan_retention_ms = 3 * 60 * 60 * 1000

        with unittest.mock.patch.object(service, "_now_ms", return_value=created_at_ms):
            pending = service.create_prompt(
                "s-prompt-retention",
                {
                    "request_id": "req_prompt_retention",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": 30_000,
                    "legal_choices": [{"choice_id": "dice"}],
                },
            )

        stored = prompt_store.get_pending("req_prompt_retention", session_id="s-prompt-retention")

        self.assertIsNotNone(stored)
        self.assertEqual(pending.created_at_ms, created_at_ms)
        self.assertEqual(pending.payload["created_at_ms"], created_at_ms)
        self.assertEqual(pending.payload["expires_at_ms"], created_at_ms + orphan_retention_ms)
        self.assertEqual(stored["payload"]["created_at_ms"], created_at_ms)
        self.assertEqual(stored["payload"]["expires_at_ms"], created_at_ms + orphan_retention_ms)
        self.assertNotIn(prompt_store._pending_key(), self.fake_redis._expires_at_ms)

    def test_game_debug_snapshot_includes_prompt_and_command_reconstruction_summaries(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        game_state = RedisGameStateStore(self.connection)

        prompt_store.save_pending(
            "req_debug_reconstruct",
            {
                "request_id": "req_debug_reconstruct",
                "session_id": "s-reconstruct",
                "player_id": 3,
                "request_type": "buy_tile",
                "created_at_ms": 1000,
            },
        )
        command_store.append_command(
            "s-reconstruct",
            "decision",
            {
                "request_id": "req_debug_reconstruct",
                "player_id": 3,
                "choice_id": "buy",
                "view_commit_seq_seen": 9,
            },
            request_id="req_debug_reconstruct",
            server_time_ms=1200,
        )
        command_store.save_consumer_offset("runtime_wakeup", "s-reconstruct", 1)

        game_state.save_checkpoint(
            "s-reconstruct",
            {
                "schema_version": 1,
                "session_id": "s-reconstruct",
                "latest_seq": 4,
                "latest_event_type": "checkpoint",
                "round_index": 2,
                "turn_index": 7,
            },
        )

        debug_snapshot = game_state.load_debug_snapshot("s-reconstruct")

        self.assertIsNotNone(debug_snapshot)
        self.assertEqual(debug_snapshot["prompts"]["counts"]["pending"], 1)
        self.assertEqual(debug_snapshot["prompts"]["active_prompt"]["request_id"], "req_debug_reconstruct")
        self.assertEqual(debug_snapshot["commands"]["command_seq"], 1)
        self.assertEqual(debug_snapshot["commands"]["command_count"], 1)
        self.assertEqual(debug_snapshot["commands"]["seen_count"], 1)
        self.assertEqual(debug_snapshot["commands"]["latest_commands"][0]["choice_id"], "buy")
        self.assertEqual(debug_snapshot["commands"]["latest_commands"][0]["view_commit_seq_seen"], 9)
        self.assertEqual(debug_snapshot["commands"]["consumer_offsets"][0]["consumer"], "runtime_wakeup")
        self.assertEqual(debug_snapshot["commands"]["consumer_offsets"][0]["seq"], 1)

    def test_stream_service_broadcasts_cached_view_commit_after_direct_runtime_transition(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        stream_backend = RedisStreamStore(self.connection)
        service = StreamService(
            stream_backend=stream_backend,
            game_state_store=game_state,
            queue_size=4,
            max_buffer=20,
        )

        async def _run() -> None:
            await service.publish(
                "s-direct-terminal",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 7,
                    "turn_index": 14,
                    "acting_player_id": 1,
                    "character": "산적",
                    "snapshot": {
                        "players": [{"player_id": 1, "position": 3, "alive": True}],
                        "board": {"f_value": 30, "tiles": [{"tile_index": 3}]},
                    },
                },
            )
            game_state.commit_transition(
                "s-direct-terminal",
                current_state={"players": [{"player_id": 1}], "board": {"f_value": 30}},
                checkpoint={
                    "schema_version": 3,
                    "session_id": "s-direct-terminal",
                    "latest_seq": stream_backend.latest_seq("s-direct-terminal"),
                    "latest_commit_seq": 2,
                    "latest_source_event_seq": 1,
                    "latest_event_type": "engine_transition",
                    "round_index": 7,
                    "turn_index": 14,
                    "has_snapshot": True,
                    "has_view_commit": True,
                },
                view_state={"turn_stage": {"current_beat_event_code": "game_end"}},
                view_commits={
                    "spectator": {
                        "schema_version": 1,
                        "commit_seq": 1,
                        "source_event_seq": 1,
                        "viewer": {"role": "spectator"},
                        "runtime": {
                            "status": "completed",
                            "round_index": 7,
                            "turn_index": 14,
                            "active_frame_id": "",
                            "active_module_id": "",
                            "active_module_type": "",
                            "module_path": [],
                        },
                        "view_state": {"turn_stage": {"current_beat_event_code": "game_end"}},
                    },
                },
                runtime_event_payload={
                    "event_type": "engine_transition",
                    "status": "completed",
                    "reason": "end_rule",
                },
                runtime_event_server_time_ms=1234,
            )

            emitted = await service.emit_latest_view_commit("s-direct-terminal")
            latest = await service.latest_view_commit_message_for_viewer(
                "s-direct-terminal",
                viewer=ViewerContext(
                    role="spectator",
                    session_id="s-direct-terminal",
                ),
            )

            self.assertIsNotNone(emitted)
            self.assertEqual(emitted.payload["source_event_seq"], 1)
            self.assertEqual(emitted.payload["runtime"]["status"], "completed")
            self.assertEqual(latest["payload"]["source_event_seq"], 1)
            self.assertEqual(latest["payload"]["runtime"]["status"], "completed")
            self.assertEqual(game_state.load_view_commit("s-direct-terminal", "spectator")["source_event_seq"], 1)

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
            view_commits={
                "spectator": {
                    "schema_version": 1,
                    "commit_seq": 1,
                    "source_event_seq": 1,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running", "round_index": 1, "turn_index": 3},
                    "view_state": {"board": {"turn": 3}},
                },
                "admin": {
                    "schema_version": 1,
                    "commit_seq": 1,
                    "source_event_seq": 1,
                    "viewer": {"role": "admin"},
                    "runtime": {"status": "running", "round_index": 1, "turn_index": 3},
                    "view_state": {"debug": True, "board": {"turn": 3}},
                },
                "player:1": {
                    "schema_version": 1,
                    "commit_seq": 1,
                    "source_event_seq": 1,
                    "viewer": {"role": "seat", "player_id": 1},
                    "runtime": {"status": "running", "round_index": 1, "turn_index": 3},
                    "view_state": {"prompt": {"active": {"request_id": "req_p1"}}},
                },
            },
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
        self.assertEqual(game_state.load_cached_view_state("s-commit", "public")["board"]["turn"], 3)
        self.assertEqual(game_state.load_view_commit("s-commit", "spectator")["commit_seq"], 1)
        self.assertEqual(game_state.load_view_commit("s-commit", "admin")["view_state"]["debug"], True)
        self.assertEqual(game_state.load_view_commit("s-commit", "player", player_id=1)["view_state"]["prompt"]["active"]["request_id"], "req_p1")
        self.assertIn("player:1", game_state.load_view_commit_index("s-commit")["view_commit_viewers"])
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", "s-commit"), 9)
        runtime_events = RedisStreamStore(self.connection).snapshot("s-commit")
        self.assertEqual(len(runtime_events), 1)
        self.assertEqual(runtime_events[0]["seq"], 1)
        self.assertEqual(runtime_events[0]["payload"]["event_type"], "engine_transition")
        debug_snapshot = game_state.load_debug_snapshot("s-commit")
        self.assertIsNotNone(debug_snapshot)
        self.assertEqual(debug_snapshot["summary"]["turn_index"], 3)
        self.assertEqual(debug_snapshot["summary"]["latest_seq"], 1)
        self.assertEqual(debug_snapshot["summary"]["latest_commit_seq"], 1)
        self.assertEqual(debug_snapshot["pending"]["pending_action_count"], 1)
        self.assertEqual(debug_snapshot["pending"]["scheduled_action_count"], 1)
        self.assertEqual(debug_snapshot["pending"]["pending_actions"][0]["action_id"], "a1")
        self.assertEqual(debug_snapshot["pending"]["scheduled_actions"][0]["action_id"], "s1")
        self.assertEqual(debug_snapshot["redis_keys"]["current_state"], "mrn-rt:game:s-commit:current_state")
        self.assertIn("spectator", debug_snapshot["view_commits"]["viewers"])
        self.assertIn(
            ["set", "set", "set", "set", "set", "set", "set", "set", "hset", "hset", "xadd"],
            self.fake_redis.pipeline_executions,
        )

    def test_command_store_consumer_offset_is_monotonic(self) -> None:
        command_store = RedisCommandStore(self.connection)

        command_store.save_consumer_offset("runtime_wakeup", "s-offset", 5)
        command_store.save_consumer_offset("runtime_wakeup", "s-offset", 3)
        command_store.save_consumer_offset("runtime_wakeup", "s-offset", 7)

        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", "s-offset"), 7)

    def test_game_state_commit_does_not_rewind_command_offset(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        command_store.save_consumer_offset("runtime_wakeup", "s-offset-commit", 9)

        game_state.commit_transition(
            "s-offset-commit",
            current_state={"turn_index": 1},
            checkpoint={"schema_version": 1, "session_id": "s-offset-commit", "turn_index": 1},
            command_consumer_name="runtime_wakeup",
            command_seq=4,
        )

        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", "s-offset-commit"), 9)

    def test_game_state_store_rejects_non_monotonic_authoritative_view_commit(self) -> None:
        game_state = RedisGameStateStore(self.connection)

        game_state.commit_transition(
            "s-conflict",
            current_state={"turn_index": 1},
            checkpoint={"schema_version": 1, "session_id": "s-conflict", "turn_index": 1},
            view_state={"board": {"turn": 1}},
            view_commits={
                "spectator": {
                    "schema_version": 1,
                    "commit_seq": 1,
                    "source_event_seq": 0,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running", "round_index": 1, "turn_index": 1},
                    "view_state": {"board": {"turn": 1}},
                },
            },
        )

        with self.assertRaises(ViewCommitSequenceConflict):
            game_state.commit_transition(
                "s-conflict",
                current_state={"turn_index": 3},
                checkpoint={"schema_version": 1, "session_id": "s-conflict", "turn_index": 3},
                view_state={"board": {"turn": 3}},
                view_commits={
                    "spectator": {
                        "schema_version": 1,
                        "commit_seq": 3,
                        "source_event_seq": 0,
                        "viewer": {"role": "spectator"},
                        "runtime": {"status": "running", "round_index": 1, "turn_index": 3},
                        "view_state": {"board": {"turn": 3}},
                    },
                },
            )

        self.assertEqual(game_state.load_checkpoint("s-conflict")["latest_commit_seq"], 1)
        self.assertEqual(game_state.load_current_state("s-conflict")["turn_index"], 1)
        self.assertEqual(game_state.load_view_commit("s-conflict", "spectator")["commit_seq"], 1)

    def test_game_state_store_rejects_stale_expected_previous_commit_seq(self) -> None:
        game_state = RedisGameStateStore(self.connection)

        game_state.commit_transition(
            "s-stale-base",
            current_state={"turn_index": 1},
            checkpoint={"schema_version": 1, "session_id": "s-stale-base", "turn_index": 1},
            view_state={"board": {"turn": 1}},
            view_commits={
                "spectator": {
                    "schema_version": 1,
                    "commit_seq": 1,
                    "source_event_seq": 0,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running", "round_index": 1, "turn_index": 1},
                    "view_state": {"board": {"turn": 1}},
                },
            },
            expected_previous_commit_seq=0,
        )

        with self.assertRaises(ViewCommitSequenceConflict):
            game_state.commit_transition(
                "s-stale-base",
                current_state={"turn_index": 2},
                checkpoint={"schema_version": 1, "session_id": "s-stale-base", "turn_index": 2},
                view_state={"board": {"turn": 2}},
                view_commits={
                    "spectator": {
                        "schema_version": 1,
                        "commit_seq": 2,
                        "source_event_seq": 0,
                        "viewer": {"role": "spectator"},
                        "runtime": {"status": "running", "round_index": 1, "turn_index": 2},
                        "view_state": {"board": {"turn": 2}},
                    },
                },
                expected_previous_commit_seq=0,
            )

        self.assertEqual(game_state.load_checkpoint("s-stale-base")["latest_commit_seq"], 1)
        self.assertEqual(game_state.load_current_state("s-stale-base")["turn_index"], 1)

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
        game_state.save_cached_view_state("s-view", "spectator", {"board": {"turn": 2}})
        game_state.save_cached_view_state("s-view", "player", {"prompt": {"active": {"request_id": "r1"}}}, player_id=1)
        game_state.save_cached_view_state("s-view", "admin", {"debug": {"hands": 4}})
        game_state.save_view_commit_index(
            "s-view",
            {
                "schema_version": 1,
                "latest_seq": 12,
                "projection_schema_version": 1,
                "cached_viewers": ["public", "spectator", "player:1", "admin"],
            },
        )

        self.assertEqual(game_state.load_view_state("s-view"), {"board": {"turn": 1}})
        self.assertEqual(game_state.load_cached_view_state("s-view", "public"), {"board": {"turn": 1}})
        self.assertEqual(game_state.load_cached_view_state("s-view", "spectator"), {"board": {"turn": 2}})
        self.assertEqual(game_state.load_cached_view_state("s-view", "player", player_id=1)["prompt"]["active"]["request_id"], "r1")
        self.assertEqual(game_state.load_cached_view_state("s-view", "admin"), {"debug": {"hands": 4}})
        self.assertEqual(game_state.load_view_commit_index("s-view")["latest_seq"], 12)

        game_state.delete_session_data("s-view")

        self.assertIsNone(game_state.load_view_state("s-view"))
        self.assertIsNone(game_state.load_cached_view_state("s-view", "public"))
        self.assertIsNone(game_state.load_cached_view_state("s-view", "spectator"))
        self.assertIsNone(game_state.load_cached_view_state("s-view", "player", player_id=1))
        self.assertIsNone(game_state.load_cached_view_state("s-view", "admin"))
        self.assertIsNone(game_state.load_view_commit_index("s-view"))
        self.assertIsNone(game_state.load_debug_snapshot("s-view"))

    def test_game_state_store_persists_authoritative_view_commit_variants(self) -> None:
        game_state = RedisGameStateStore(self.connection)

        game_state.apply_stream_message(
            {
                "seq": 12,
                "type": "view_commit",
                "session_id": "s-view-commit",
                "server_time_ms": 12345,
                "payload": {
                    "schema_version": 1,
                    "commit_seq": 12,
                    "source_event_seq": 11,
                    "viewer": {"role": "spectator"},
                    "runtime": {"round_index": 2, "turn_index": 3},
                    "view_state": {"board": {"turn": 3}},
                },
            }
        )
        game_state.save_view_commit(
            "s-view-commit",
            {
                "schema_version": 1,
                "commit_seq": 12,
                "source_event_seq": 11,
                "viewer": {"role": "seat", "player_id": 1, "seat": 1},
                "runtime": {"round_index": 2, "turn_index": 3},
                "view_state": {"prompt": {"active": {"request_id": "req_p1"}}},
            },
            viewer="player",
            player_id=1,
        )

        checkpoint = game_state.load_checkpoint("s-view-commit")
        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint["latest_event_type"], "view_commit")
        self.assertEqual(checkpoint["latest_commit_seq"], 12)
        self.assertEqual(checkpoint["latest_source_event_seq"], 11)
        self.assertTrue(checkpoint["has_view_commit"])
        self.assertEqual(game_state.load_view_commit("s-view-commit", "spectator")["commit_seq"], 12)
        self.assertEqual(game_state.load_view_state("s-view-commit")["board"]["turn"], 3)
        self.assertEqual(
            game_state.load_view_commit("s-view-commit", "player", player_id=1)["view_state"]["prompt"]["active"][
                "request_id"
            ],
            "req_p1",
        )

        game_state.delete_session_data("s-view-commit")

        self.assertIsNone(game_state.load_view_commit("s-view-commit", "spectator"))
        self.assertIsNone(game_state.load_view_commit("s-view-commit", "player", player_id=1))
        self.assertIsNone(game_state.load_checkpoint("s-view-commit"))

    def test_game_state_store_rejects_stale_view_commit_overwrite(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        game_state.save_view_commit(
            "s-stale-commit",
            {
                "schema_version": 1,
                "commit_seq": 5,
                "source_event_seq": 22,
                "viewer": {"role": "spectator"},
                "runtime": {"round_index": 1, "turn_index": 2},
                "view_state": {"runtime": {"commit_seq": 5}},
            },
            viewer="spectator",
        )

        with self.assertRaises(ViewCommitSequenceConflict):
            game_state.save_view_commit(
                "s-stale-commit",
                {
                    "schema_version": 1,
                    "commit_seq": 4,
                    "source_event_seq": 23,
                    "viewer": {"role": "spectator"},
                    "runtime": {"round_index": 1, "turn_index": 1},
                    "view_state": {"runtime": {"commit_seq": 4}},
                },
                viewer="spectator",
            )

        self.assertEqual(game_state.load_view_commit("s-stale-commit", "spectator")["commit_seq"], 5)
        self.assertEqual(game_state.load_view_commit_index("s-stale-commit")["latest_commit_seq"], 5)

    def test_game_state_store_preserves_view_commit_sequence_when_applying_debug_event(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        game_state.apply_stream_message(
            {
                "seq": 12,
                "type": "view_commit",
                "session_id": "s-preserve-commit",
                "server_time_ms": 12345,
                "payload": {
                    "schema_version": 1,
                    "commit_seq": 8,
                    "source_event_seq": 11,
                    "viewer": {"role": "spectator"},
                    "runtime": {"round_index": 2, "turn_index": 3},
                    "view_state": {"board": {"turn": 3}},
                },
            }
        )
        game_state.apply_stream_message(
            {
                "seq": 13,
                "type": "event",
                "session_id": "s-preserve-commit",
                "server_time_ms": 12346,
                "payload": {"event_type": "debug_event", "round_index": 2, "turn_index": 4},
            }
        )

        checkpoint = game_state.load_checkpoint("s-preserve-commit")
        self.assertEqual(checkpoint["latest_seq"], 13)
        self.assertEqual(checkpoint["latest_event_type"], "debug_event")
        self.assertEqual(checkpoint["latest_commit_seq"], 8)
        self.assertEqual(checkpoint["latest_source_event_seq"], 11)
        self.assertTrue(checkpoint["has_view_commit"])

    def test_runtime_service_next_view_commit_seq_uses_cached_commit_index(self) -> None:
        game_state = RedisGameStateStore(self.connection)
        game_state.save_view_commit(
            "s-next-commit",
            {
                "schema_version": 1,
                "commit_seq": 14,
                "source_event_seq": 55,
                "viewer": {"role": "spectator"},
                "runtime": {"round_index": 3, "turn_index": 2},
                "view_state": {"runtime": {"commit_seq": 14}},
            },
            viewer="spectator",
        )
        game_state.save_checkpoint(
            "s-next-commit",
            {
                "schema_version": 1,
                "session_id": "s-next-commit",
                "latest_seq": 56,
                "latest_event_type": "debug_event",
                "round_index": 3,
                "turn_index": 2,
            },
        )
        runtime = RuntimeService(None, None, game_state_store=game_state)

        self.assertEqual(runtime._next_view_commit_seq("s-next-commit"), 15)

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
            "payload": {**payload, "view_state": project_replay_view_state([{"seq": 12, "type": "event", "payload": payload}])},
        }

        game_state.apply_stream_message(message)

        current_state = game_state.load_current_state("s-state-projection")
        view_state = game_state.load_cached_view_state("s-state-projection", "public")
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
        self.assertEqual(result["session_id"], "s-atomic")
        self.assertEqual(result["command_seq"], int(commands[0]["seq"]))
        self.assertIn(
            [
                "hdel",
                "hset",
                "hset",
                "xadd",
            ],
            self.fake_redis.pipeline_executions,
        )

    def test_prompt_service_scopes_resolved_request_ids_by_session(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        service = PromptService(prompt_store=prompt_store, command_store=command_store)
        payload = {
            "request_id": "shared-redis-batch:p0",
            "request_type": "burden_exchange",
            "player_id": 1,
            "timeout_ms": 30000,
            "legal_choices": [{"choice_id": "yes"}],
        }
        service.create_prompt("s-redis-a", payload)
        first = service.submit_decision(
            {
                "session_id": "s-redis-a",
                "request_id": "shared-redis-batch:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )
        self.assertEqual(first["status"], "accepted")
        self.assertEqual(prompt_store.get_resolved("shared-redis-batch:p0", session_id="s-redis-a")["session_id"], "s-redis-a")

        recreated = service.create_prompt("s-redis-b", payload)
        self.assertEqual(recreated.session_id, "s-redis-b")
        second = service.submit_decision(
            {
                "session_id": "s-redis-b",
                "request_id": "shared-redis-batch:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(prompt_store.get_resolved("shared-redis-batch:p0", session_id="s-redis-b")["session_id"], "s-redis-b")

    def test_prompt_service_scopes_pending_request_ids_by_session(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        service = PromptService(prompt_store=prompt_store, command_store=command_store)
        payload = {
            "request_id": "shared-redis-pending:p0",
            "request_type": "burden_exchange",
            "player_id": 1,
            "timeout_ms": 30000,
            "legal_choices": [{"choice_id": "yes"}],
        }

        first = service.create_prompt("s-redis-a", payload)
        second = service.create_prompt("s-redis-b", payload)

        self.assertEqual(first.session_id, "s-redis-a")
        self.assertEqual(second.session_id, "s-redis-b")
        self.assertEqual(
            sorted(item["session_id"] for item in prompt_store.list_pending() if item["request_id"] == "shared-redis-pending:p0"),
            ["s-redis-a", "s-redis-b"],
        )

        accepted = service.submit_decision(
            {
                "session_id": "s-redis-a",
                "request_id": "shared-redis-pending:p0",
                "player_id": 1,
                "choice_id": "yes",
            }
        )

        self.assertEqual(accepted["status"], "accepted")
        self.assertFalse(service.has_pending_for_session("s-redis-a"))
        self.assertTrue(service.has_pending_for_session("s-redis-b"))
        self.assertIsNone(prompt_store.get_pending("shared-redis-pending:p0", session_id="s-redis-a"))
        self.assertIsNotNone(prompt_store.get_pending("shared-redis-pending:p0", session_id="s-redis-b"))

    def test_command_store_recovers_seq_after_seq_key_eviction(self) -> None:
        command_store = RedisCommandStore(self.connection)

        first = command_store.append_command(
            "s-command-seq-recover",
            "decision_submitted",
            {"request_id": "r-seq-1", "choice_id": "roll"},
            request_id="r-seq-1",
            server_time_ms=100,
        )
        self.fake_redis.delete(command_store._seq_key("s-command-seq-recover"))
        second = command_store.append_command(
            "s-command-seq-recover",
            "decision_submitted",
            {"request_id": "r-seq-2", "choice_id": "roll"},
            request_id="r-seq-2",
            server_time_ms=200,
        )

        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertEqual(
            [command["seq"] for command in command_store.list_commands("s-command-seq-recover")],
            [1, 2],
        )

    def test_prompt_service_recovers_command_seq_after_seq_key_eviction(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        service = PromptService(prompt_store=prompt_store, command_store=command_store)
        service.create_prompt(
            "s-prompt-seq-recover",
            {
                "request_id": "r-prompt-seq-1",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )
        first = service.submit_decision({"request_id": "r-prompt-seq-1", "player_id": 1, "choice_id": "roll"})

        self.fake_redis.delete(command_store._seq_key("s-prompt-seq-recover"))
        service.create_prompt(
            "s-prompt-seq-recover",
            {
                "request_id": "r-prompt-seq-2",
                "request_type": "movement",
                "player_id": 1,
                "timeout_ms": 30000,
                "legal_choices": [{"choice_id": "roll"}],
            },
        )
        second = service.submit_decision({"request_id": "r-prompt-seq-2", "player_id": 1, "choice_id": "roll"})

        self.assertEqual(first["command_seq"], 1)
        self.assertEqual(second["command_seq"], 2)
        self.assertEqual(
            [command["seq"] for command in command_store.list_commands("s-prompt-seq-recover")],
            [1, 2],
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

    def test_prompt_timeout_worker_cleans_only_expired_orphan_pending_prompts(self) -> None:
        prompt_store = RedisPromptStore(self.connection)
        prompt_service = PromptService(prompt_store=prompt_store)
        runtime_state_store = RedisRuntimeStateStore(self.connection)
        stream_service = StreamService(stream_backend=RedisStreamStore(self.connection))
        orphan_retention_ms = 3 * 60 * 60 * 1000
        created_at_ms = 2_000
        cleanup_now_ms = created_at_ms + orphan_retention_ms + 1

        class _NoopRuntime:
            def __init__(self, store) -> None:
                self._runtime_state_store = store

            async def execute_prompt_fallback(self, **kwargs):
                raise AssertionError("orphan cleanup must not execute timeout fallback")

        with unittest.mock.patch.object(prompt_service, "_now_ms", return_value=created_at_ms):
            prompt_service.create_prompt(
                "s-active-pending",
                {
                    "request_id": "req_active_pending",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": orphan_retention_ms + 60_000,
                    "legal_choices": [{"choice_id": "dice"}],
                },
            )
            prompt_service.create_prompt(
                "s-orphan-pending",
                {
                    "request_id": "req_orphan_pending",
                    "request_type": "movement",
                    "player_id": 1,
                    "timeout_ms": orphan_retention_ms + 60_000,
                    "legal_choices": [{"choice_id": "dice"}],
                },
            )

        runtime_state_store.save_status(
            "s-active-pending",
            {
                "status": "running",
                "last_activity_ms": cleanup_now_ms,
                "lease_expires_at_ms": cleanup_now_ms + 60_000,
            },
        )
        runtime_state_store.acquire_lease("s-active-pending", "runtime_worker", 60_000)
        worker = PromptTimeoutWorker(
            prompt_service=prompt_service,
            runtime_service=_NoopRuntime(runtime_state_store),
            stream_service=stream_service,
        )

        async def _run() -> None:
            results = await worker.run_once(now_ms=cleanup_now_ms)

            self.assertEqual(results, [])
            self.assertIsNotNone(prompt_store.get_pending("req_active_pending", session_id="s-active-pending"))
            self.assertIsNone(prompt_store.get_pending("req_orphan_pending", session_id="s-orphan-pending"))
            resolved = prompt_store.get_resolved("req_orphan_pending", session_id="s-orphan-pending")
            lifecycle = prompt_store.get_lifecycle("req_orphan_pending", session_id="s-orphan-pending")
            self.assertEqual(resolved["reason"], "orphan_pending_cleanup")
            self.assertEqual(lifecycle["state"], "expired")
            self.assertEqual(lifecycle["reason"], "orphan_pending_cleanup")

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
                prompt_payload={
                    "fallback_choice_id": "choice_default",
                    "legal_choices": [{"choice_id": "choice_default", "title": "Default"}],
                },
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
        prompt_service = PromptService(prompt_store=RedisPromptStore(self.connection))
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.start_session(session.session_id, session.host_token)
        game_state.commit_transition(
            session.session_id,
            current_state={"schema_version": 1, "turn": 5, "players": [{"player_id": 1}]},
            checkpoint={
                "schema_version": 1,
                "session_id": session.session_id,
                "latest_seq": 1,
                "latest_event_type": "turn_end_snapshot",
                "round_index": 2,
                "turn_index": 5,
                "has_snapshot": True,
            },
        )
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
        RuntimeService._ensure_engine_import_path()
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

        self.assertEqual(step["status"], "completed")
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["f_value"], 15.0)
        self.assertEqual(saved_state["turn_index"], 7)
        self.assertEqual(saved_checkpoint["latest_event_type"], "engine_transition")
        self.assertEqual(saved_checkpoint["turn_index"], 7)
        self.assertTrue(saved_checkpoint["has_snapshot"])

    def test_runtime_recovery_drains_pending_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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

    def test_command_wakeup_restart_resumes_queued_purchase_prompt_from_redis(self) -> None:
        RuntimeService._ensure_engine_import_path()
        from config import CellKind
        from state import ActionEnvelope, GameState

        sessions = SessionService()
        game_state = RedisGameStateStore(self.connection)
        command_store = RedisCommandStore(self.connection)
        prompt_store = RedisPromptStore(self.connection)
        stream_store = RedisStreamStore(self.connection)
        runtime_state_store = RedisRuntimeStateStore(self.connection)
        first_prompt_service = PromptService(prompt_store=prompt_store, command_store=command_store)
        first_stream_service = StreamService(
            stream_backend=stream_store,
            game_state_store=game_state,
            command_store=command_store,
        )
        session = sessions.create_session(
            seats=[
                {"seat": 1, "seat_type": "human"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )
        sessions.join_session(session.session_id, 1, session.join_tokens[1], "P1")
        sessions.start_session(session.session_id, session.host_token)
        first_runtime = RuntimeService(
            session_service=sessions,
            stream_service=first_stream_service,
            prompt_service=first_prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state,
            command_store=command_store,
        )
        config = first_runtime._config_factory.create(session.resolved_parameters)
        state = GameState.create(config)
        tile_index = state.first_tile_position(kinds=[CellKind.T2])
        state.current_round_order = [0, 1]
        state.turn_index = 0
        state.players[0].position = tile_index
        state.pending_actions = [
            ActionEnvelope(
                action_id="restart_purchase_prompt",
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
                action_id="restart_purchase_post",
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

        async def _first_prompt() -> dict:
            return await asyncio.to_thread(
                first_runtime._run_engine_transition_once_sync,
                asyncio.get_running_loop(),
                session.session_id,
                42,
                None,
                True,
                None,
                None,
            )

        first_step = asyncio.run(_first_prompt())
        pending_prompts = [item for item in prompt_store.list_pending() if item.get("session_id") == session.session_id]
        self.assertEqual(first_step["status"], "waiting_input")
        self.assertEqual(len(pending_prompts), 1)
        request_id = str(pending_prompts[0]["request_id"])
        saved_before_restart = game_state.load_current_state(session.session_id)
        self.assertEqual(
            [action["type"] for action in saved_before_restart["pending_actions"]],
            ["request_purchase_tile", "resolve_unowned_post_purchase"],
        )

        accepted = first_prompt_service.submit_decision(
            {
                "request_id": request_id,
                "player_id": int(pending_prompts[0]["player_id"]),
                "choice_id": "yes",
            }
        )
        self.assertEqual(accepted["status"], "accepted")
        command = command_store.list_commands(session.session_id)[0]

        restarted_prompt_service = PromptService(prompt_store=prompt_store, command_store=command_store)
        restarted_stream_service = StreamService(
            stream_backend=stream_store,
            game_state_store=game_state,
            command_store=command_store,
        )
        restarted_runtime = RuntimeService(
            session_service=sessions,
            stream_service=restarted_stream_service,
            prompt_service=restarted_prompt_service,
            runtime_state_store=runtime_state_store,
            game_state_store=game_state,
            command_store=command_store,
        )
        worker = CommandStreamWakeupWorker(
            command_store=command_store,
            session_service=sessions,
            runtime_service=restarted_runtime,
            consumer_name="runtime_wakeup",
        )

        wakeups = asyncio.run(worker.run_once(session_id=session.session_id))
        saved_after_restart = game_state.load_current_state(session.session_id)
        checkpoint_after_restart = game_state.load_checkpoint(session.session_id)
        prompt_messages = [
            message
            for message in stream_store.snapshot(session.session_id)
            if message["type"] == "prompt" and message["payload"].get("request_id") == request_id
        ]

        self.assertEqual(len(wakeups), 1)
        self.assertEqual(wakeups[0]["command_seq"], int(command["seq"]))
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), int(command["seq"]))
        self.assertEqual(prompt_store.get_pending(request_id), None)
        self.assertEqual(len(prompt_messages), 1)
        self.assertEqual(saved_after_restart["tiles"][tile_index]["owner_id"], 0)
        self.assertNotIn("request_purchase_tile", [action["type"] for action in saved_after_restart["pending_actions"]])
        self.assertEqual(checkpoint_after_restart["processed_command_seq"], int(command["seq"]))

    def test_runtime_recovery_drains_post_purchase_action_from_checkpoint(self) -> None:
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        RuntimeService._ensure_engine_import_path()
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
        self.assertEqual(result["status"], "completed")
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
                "view_state": True,
                "view_commit": True,
                "runtime_event": True,
                "consumer_offset": True,
                "offset_consumer": "runtime_wakeup",
                "offset_seq": 4,
            },
        )
        self.assertEqual(saved_checkpoint["latest_commit_seq"], 1)
        self.assertEqual(game_state.load_view_commit(session.session_id, "spectator")["commit_seq"], 1)
        source_events = [event for event in runtime_events if event.get("type") != "view_commit"]
        view_commits = [event for event in runtime_events if event.get("type") == "view_commit"]
        self.assertEqual(source_events[-1]["seq"], saved_checkpoint["latest_seq"])
        self.assertEqual(source_events[-1]["payload"]["event_type"], "engine_transition")
        self.assertEqual(source_events[-1]["payload"]["processed_command_seq"], 4)
        self.assertEqual(source_events[-1]["payload"]["command_commit_envelope"], saved_checkpoint["command_commit_envelope"])
        self.assertEqual(view_commits[-1]["payload"]["commit_seq"], saved_checkpoint["latest_commit_seq"])
        self.assertEqual(view_commits[-1]["payload"]["source_event_seq"], saved_checkpoint["latest_source_event_seq"])
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

        self.assertIn(second["status"], {"committed", "waiting_input", "completed"})
        self.assertEqual(prompt_store.get_pending(request_id), None)
        self.assertEqual(len(prompt_messages), 1)
        self.assertEqual(command_store.load_consumer_offset("runtime_wakeup", session.session_id), int(command["seq"]))

    def test_runtime_recovery_transition_persists_pending_prompt_metadata(self) -> None:
        RuntimeService._ensure_engine_import_path()
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
            return_value={"status": "completed", "transitions": 1},
        ) as transition_loop:
            result = runtime._run_engine_sync(
                unittest.mock.Mock(),
                session.session_id,
                42,
                None,
            )

        self.assertEqual(result, {"status": "completed", "transitions": 1})
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

    def expire(self, name: str, seconds: int) -> "_FakeRedisPipeline":
        self._ops.append(("expire", (name, seconds), {}))
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
        self.hgetall_calls: list[str] = []

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
        self.hgetall_calls.append(name)
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

    def expire(self, name: str, seconds: int) -> bool:
        self._expires_at_ms[name] = int(seconds)
        return True

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

    def xlen(self, name: str) -> int:
        return len(self._streams.get(name, []))

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
