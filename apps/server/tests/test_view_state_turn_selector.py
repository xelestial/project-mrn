from __future__ import annotations

import unittest

from apps.server.src.domain.view_state.turn_selector import build_turn_stage_view_state


class ViewStateTurnSelectorTests(unittest.TestCase):
    def test_build_turn_stage_projects_current_beat_and_progress_codes(self) -> None:
        view_state = build_turn_stage_view_state(
            [
                {
                    "type": "event",
                    "seq": 200,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "turn_start",
                        "round_index": 3,
                        "turn_index": 8,
                        "acting_player_id": 2,
                        "character": "교리 연구관",
                    },
                },
                {
                    "type": "event",
                    "seq": 201,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "event_type": "dice_roll",
                        "round_index": 3,
                        "turn_index": 8,
                        "acting_player_id": 2,
                        "cards_used": [1, 4],
                        "total_move": 5,
                    },
                },
                {
                    "type": "event",
                    "seq": 202,
                    "session_id": "s1",
                    "server_time_ms": 3,
                    "payload": {
                        "event_type": "player_move",
                        "round_index": 3,
                        "turn_index": 8,
                        "acting_player_id": 2,
                        "from_tile_index": 3,
                        "to_tile_index": 8,
                    },
                },
                {
                    "type": "event",
                    "seq": 203,
                    "session_id": "s1",
                    "server_time_ms": 4,
                    "payload": {
                        "event_type": "landing_resolved",
                        "round_index": 3,
                        "turn_index": 8,
                        "acting_player_id": 2,
                        "position": 8,
                        "result_type": "PURCHASE",
                    },
                },
                {
                    "type": "event",
                    "seq": 204,
                    "session_id": "s1",
                    "server_time_ms": 5,
                    "payload": {
                        "event_type": "tile_purchased",
                        "round_index": 3,
                        "turn_index": 8,
                        "acting_player_id": 2,
                        "tile_index": 8,
                        "cost": 5,
                    },
                },
            ]
        )

        self.assertEqual(view_state["actor_player_id"], 2)
        self.assertEqual(view_state["character"], "교리 연구관")
        self.assertEqual(view_state["current_beat_event_code"], "tile_purchased")
        self.assertEqual(view_state["current_beat_kind"], "economy")
        self.assertEqual(view_state["current_beat_seq"], 204)
        self.assertEqual(view_state["focus_tile_index"], 8)
        self.assertEqual(
            view_state["progress_codes"],
            ["turn_start", "dice_roll", "player_move", "landing_resolved", "tile_purchased"],
        )

    def test_build_turn_stage_projects_prompt_focus_and_external_ai_status(self) -> None:
        view_state = build_turn_stage_view_state(
            [
                {
                    "type": "event",
                    "seq": 300,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "turn_start",
                        "round_index": 4,
                        "turn_index": 11,
                        "acting_player_id": 2,
                        "character": "Scholar",
                    },
                },
                {
                    "type": "event",
                    "seq": 301,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "event_type": "decision_timeout_fallback",
                        "round_index": 4,
                        "turn_index": 11,
                        "player_id": 2,
                        "request_type": "purchase_tile",
                        "public_context": {
                            "tile_index": 9,
                            "external_ai_worker_id": "prod-bot-1",
                            "external_ai_failure_code": "external_ai_timeout",
                            "external_ai_fallback_mode": "local_ai",
                            "external_ai_attempt_count": 3,
                            "external_ai_attempt_limit": 4,
                            "external_ai_ready_state": "not_ready",
                            "external_ai_policy_mode": "heuristic_v3_gpt",
                            "external_ai_worker_adapter": "priority_score_v1",
                            "external_ai_policy_class": "PriorityScoredPolicy",
                            "external_ai_decision_style": "priority_scored_contract",
                        },
                    },
                },
            ]
        )

        self.assertEqual(view_state["current_beat_event_code"], "decision_timeout_fallback")
        self.assertEqual(view_state["current_beat_request_type"], "purchase_tile")
        self.assertEqual(view_state["prompt_request_type"], "purchase_tile")
        self.assertEqual(view_state["focus_tile_index"], 9)
        self.assertEqual(view_state["focus_tile_indices"], [9])
        self.assertEqual(view_state["external_ai_worker_id"], "prod-bot-1")
        self.assertEqual(view_state["external_ai_failure_code"], "external_ai_timeout")
        self.assertEqual(view_state["external_ai_fallback_mode"], "local_ai")
        self.assertEqual(view_state["external_ai_attempt_count"], 3)
        self.assertEqual(view_state["external_ai_attempt_limit"], 4)
        self.assertEqual(view_state["external_ai_ready_state"], "not_ready")
        self.assertEqual(view_state["external_ai_policy_mode"], "heuristic_v3_gpt")
        self.assertEqual(view_state["external_ai_worker_adapter"], "priority_score_v1")
        self.assertEqual(view_state["external_ai_policy_class"], "PriorityScoredPolicy")
        self.assertEqual(view_state["external_ai_decision_style"], "priority_scored_contract")
