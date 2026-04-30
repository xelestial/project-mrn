from __future__ import annotations

import unittest

from apps.server.src.domain.visibility import (
    ViewerContext,
    can_view,
    project_stream_message_for_viewer,
)


class VisibilityProjectionTests(unittest.TestCase):
    def test_can_view_visibility_scopes(self) -> None:
        seat1 = ViewerContext(role="seat", player_id=1)
        seat2 = ViewerContext(role="seat", player_id=2)
        spectator = ViewerContext(role="spectator")
        admin = ViewerContext(role="admin")
        backend = ViewerContext(role="backend")

        self.assertTrue(can_view({"scope": "public"}, spectator))
        self.assertTrue(can_view({"scope": "spectator_safe"}, seat1))
        self.assertTrue(can_view({"scope": "spectator_safe"}, spectator))
        self.assertTrue(can_view({"scope": "player", "player_id": 1}, seat1))
        self.assertFalse(can_view({"scope": "player", "player_id": 1}, seat2))
        self.assertTrue(can_view({"scope": "players", "player_ids": [1, 3]}, seat1))
        self.assertFalse(can_view({"scope": "players", "player_ids": [1, 3]}, seat2))
        self.assertFalse(can_view({"scope": "admin"}, seat1))
        self.assertTrue(can_view({"scope": "admin"}, admin))
        self.assertFalse(can_view({"scope": "backend_only"}, admin))
        self.assertTrue(can_view({"scope": "backend_only"}, backend))

    def test_prompt_is_only_delivered_to_target_player(self) -> None:
        prompt = {
            "type": "prompt",
            "payload": {
                "request_id": "req_hidden",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "legal_choices": [{"choice_id": "card-11"}],
                "public_context": {
                    "full_hand": [{"deck_index": 11, "name": "재뿌리기"}],
                    "hidden_trick_deck_index": 11,
                },
            },
        }

        target = project_stream_message_for_viewer(prompt, ViewerContext(role="seat", player_id=1))
        other = project_stream_message_for_viewer(prompt, ViewerContext(role="seat", player_id=2))
        spectator = project_stream_message_for_viewer(prompt, ViewerContext(role="spectator"))

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["legal_choices"][0]["choice_id"], "card-11")
        self.assertIsNone(other)
        self.assertIsNone(spectator)

    def test_private_decision_event_is_only_delivered_to_target_player(self) -> None:
        event = {
            "type": "event",
            "payload": {
                "event_type": "decision_requested",
                "request_id": "req_trick",
                "request_type": "hidden_trick_card",
                "player_id": 1,
                "public_context": {
                    "full_hand": [{"deck_index": 11, "name": "재뿌리기"}],
                    "hidden_trick_deck_index": 11,
                },
            },
        }

        target = project_stream_message_for_viewer(event, ViewerContext(role="seat", player_id=1))
        other = project_stream_message_for_viewer(event, ViewerContext(role="seat", player_id=2))

        self.assertIsNotNone(target)
        self.assertIsNone(other)

    def test_non_target_viewer_gets_redacted_draft_pick(self) -> None:
        event = {
            "type": "event",
            "payload": {
                "event_type": "draft_pick",
                "player_id": 1,
                "picked_card": 7,
                "choice_id": "7",
                "public_context": {"offered_names": ["객주", "박수"]},
            },
        }

        projected = project_stream_message_for_viewer(event, ViewerContext(role="seat", player_id=2))

        self.assertIsNotNone(projected)
        self.assertNotIn("picked_card", projected["payload"])
        self.assertNotIn("choice_id", projected["payload"])
        self.assertNotIn("offered_names", projected["payload"]["public_context"])

    def test_non_target_viewer_gets_redacted_embedded_view_state(self) -> None:
        event = {
            "type": "event",
            "payload": {
                "event_type": "turn_start",
                "player_id": 1,
                "view_state": {
                    "hand_tray": {
                        "cards": [{"deck_index": 11, "name": "재뿌리기"}],
                    },
                    "prompt": {
                        "active": {
                            "request_id": "req_trick",
                            "request_type": "trick_to_use",
                            "player_id": 1,
                            "choices": [{"choice_id": "card-11"}],
                            "public_context": {"full_hand": [{"deck_index": 11, "name": "재뿌리기"}]},
                        }
                    },
                    "players": {"items": []},
                },
            },
        }

        projected = project_stream_message_for_viewer(event, ViewerContext(role="seat", player_id=2))

        self.assertIsNotNone(projected)
        view_state = projected["payload"]["view_state"]
        self.assertNotIn("hand_tray", view_state)
        self.assertNotIn("prompt", view_state)
        self.assertEqual(view_state["players"], {"items": []})


if __name__ == "__main__":
    unittest.main()
