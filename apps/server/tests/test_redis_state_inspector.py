from __future__ import annotations

import unittest

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.realtime_persistence import (
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
)
from apps.server.src.services.redis_state_inspector import RedisStateInspector
from apps.server.tests.test_redis_realtime_services import _FakeRedis


class RedisStateInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_redis = _FakeRedis()
        self.connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-inspect", socket_timeout_ms=250),
            client_factory=lambda: self.fake_redis,
        )
        self.game_state = RedisGameStateStore(self.connection)
        self.prompt_store = RedisPromptStore(self.connection)
        self.runtime_state = RedisRuntimeStateStore(self.connection)
        self.stream_store = RedisStreamStore(self.connection)

    def test_inspector_reports_consistent_active_prompt_state(self) -> None:
        session_id = "s-inspect-ok"
        active_prompt = {
            "request_id": "req-move-1",
            "prompt_instance_id": "prompt-1",
            "request_type": "movement",
            "player_id": 2,
            "view_commit_seq": 5,
            "resume_token": "resume-1",
            "timeout_ms": 30000,
        }
        current_state = {
            "schema_version": 3,
            "round_index": 2,
            "turn_index": 7,
            "current_player_id": 2,
            "runtime_active_prompt": active_prompt,
            "runtime_frame_stack": [
                {
                    "frame_id": "turn:r2:p2",
                    "frame_type": "turn",
                    "status": "running",
                    "player_id": 2,
                    "active_module_id": "module:move",
                    "active_module_type": "MovementModule",
                }
            ],
            "players": [{"player_id": 2, "position": 12, "money": 18, "shards": 3}],
            "board": {"f_value": 6, "weather": "맑음", "tiles": [{}, {}]},
        }
        checkpoint = {
            "schema_version": 3,
            "session_id": session_id,
            "latest_seq": 8,
            "latest_event_type": "prompt_required",
            "latest_commit_seq": 5,
            "latest_source_event_seq": 8,
            "round_index": 2,
            "turn_index": 7,
            "has_view_commit": True,
            "waiting_prompt_request_id": "req-move-1",
            "waiting_prompt_player_id": 2,
            "waiting_prompt_type": "movement",
            "runtime_active_prompt": active_prompt,
        }
        self.game_state.commit_transition(
            session_id,
            current_state=current_state,
            checkpoint=checkpoint,
            view_state={"runtime": {"status": "waiting_input"}, "players": [{"player_id": 2}]},
            view_commits={
                "spectator": {
                    "schema_version": 1,
                    "commit_seq": 5,
                    "source_event_seq": 8,
                    "viewer": {"role": "spectator"},
                    "runtime": {
                        "status": "waiting_input",
                        "round_index": 2,
                        "turn_index": 7,
                        "turn_label": "R2-T7",
                        "current_player_id": 2,
                        "active_prompt": active_prompt,
                    },
                },
                "player:2": {
                    "schema_version": 1,
                    "commit_seq": 5,
                    "source_event_seq": 8,
                    "viewer": {"role": "seat", "player_id": 2},
                    "runtime": {
                        "status": "waiting_input",
                        "round_index": 2,
                        "turn_index": 7,
                        "turn_label": "R2-T7",
                        "current_player_id": 2,
                        "active_prompt": active_prompt,
                    },
                },
            },
            expected_previous_commit_seq=0,
        )
        self.prompt_store.save_pending("req-move-1", {**active_prompt, "session_id": session_id}, session_id=session_id)
        self.prompt_store.save_lifecycle(
            "req-move-1",
            {**active_prompt, "session_id": session_id, "state": "delivered"},
            session_id=session_id,
        )
        self.runtime_state.save_status(
            session_id,
            {
                "status": "waiting_input",
                "round_index": 2,
                "turn_index": 7,
                "turn_label": "R2-T7",
                "current_player_id": 2,
                "active_prompt": active_prompt,
            },
        )
        self.runtime_state.acquire_lease(session_id, "worker-1", ttl_ms=5000)
        self.stream_store.publish(
            session_id,
            "view_commit",
            {
                "commit_seq": 5,
                "source_event_seq": 8,
                "viewer": {"role": "seat", "player_id": 2},
                "runtime": {"status": "waiting_input", "active_prompt": active_prompt},
            },
            server_time_ms=100,
            max_buffer=20,
        )

        report = RedisStateInspector(self.connection).inspect_session(session_id, now_ms=123456)

        self.assertEqual(report["summary"]["diagnostic_status"], "ok")
        self.assertEqual(report["summary"]["turn_label"], "R2-T7")
        self.assertEqual(report["summary"]["current_player_id"], 2)
        self.assertEqual(report["summary"]["waiting_prompt_request_id"], "req-move-1")
        self.assertEqual(report["summary"]["pending_prompt_count"], 1)
        self.assertEqual(report["summary"]["viewer_commit_count"], 2)
        self.assertEqual(report["summary"]["viewer_outbox_count"], 1)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["view_commits"]["latest_commit_seq"], 5)
        self.assertIn("player:2", {viewer["label"] for viewer in report["view_commits"]["viewers"]})

    def test_inspector_detects_failed_runtime_stale_commit_and_missing_prompt(self) -> None:
        session_id = "s-inspect-bad"
        self.game_state.save_view_commit(
            session_id,
            {
                "schema_version": 1,
                "commit_seq": 8,
                "source_event_seq": 10,
                "viewer": {"role": "spectator"},
                "runtime": {
                    "status": "waiting_input",
                    "round_index": 4,
                    "turn_index": 15,
                    "turn_label": "R4-T15",
                    "active_prompt": {
                        "request_id": "req-missing",
                        "request_type": "mark_target",
                        "player_id": 3,
                    },
                },
            },
            viewer="spectator",
        )
        self.game_state.save_checkpoint(
            session_id,
            {
                "schema_version": 3,
                "session_id": session_id,
                "latest_seq": 10,
                "latest_event_type": "prompt_required",
                "latest_commit_seq": 9,
                "latest_source_event_seq": 10,
                "round_index": 4,
                "turn_index": 15,
                "has_view_commit": True,
                "waiting_prompt_request_id": "req-missing",
                "waiting_prompt_player_id": 3,
                "waiting_prompt_type": "mark_target",
            },
        )
        self.game_state.save_current_state(
            session_id,
            {
                "schema_version": 3,
                "runtime_active_prompt": {
                    "request_id": "req-missing",
                    "request_type": "mark_target",
                    "player_id": 3,
                },
            },
        )
        self.runtime_state.save_status(
            session_id,
            {
                "status": "failed",
                "round_index": 4,
                "turn_index": 15,
                "turn_label": "R4-T15",
                "error": "",
                "exception_class": "RuntimeInvariantError",
                "exception_repr": "RuntimeInvariantError('active module missing')",
                "traceback": "Traceback...\nRuntimeInvariantError: active module missing",
                "active_frame_id": "turn:r4:p3",
                "scheduled_actions": [{"action_id": "resolve_mark:3", "type": "resolve_mark"}],
            },
        )

        report = RedisStateInspector(self.connection).inspect_session(session_id, now_ms=123456)
        issue_codes = {issue["code"] for issue in report["issues"]}

        self.assertEqual(report["summary"]["diagnostic_status"], "critical")
        self.assertIn("runtime_failed", issue_codes)
        self.assertIn("checkpoint_commit_seq_mismatch", issue_codes)
        self.assertIn("waiting_prompt_missing_pending", issue_codes)
        self.assertEqual(report["summary"]["latest_commit_seq"], 9)
        runtime_failed = next(issue for issue in report["issues"] if issue["code"] == "runtime_failed")
        self.assertEqual(runtime_failed["evidence"]["exception_class"], "RuntimeInvariantError")
        self.assertIn("active module missing", runtime_failed["evidence"]["exception_repr"])


if __name__ == "__main__":
    unittest.main()
