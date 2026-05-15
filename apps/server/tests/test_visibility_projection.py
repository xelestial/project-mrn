from __future__ import annotations

import unittest

from apps.server.src.domain.visibility import (
    ViewerContext,
    can_view,
    project_stream_message_for_viewer,
    viewer_from_auth_context,
)


class VisibilityProjectionTests(unittest.TestCase):
    def test_viewer_from_auth_context_preserves_protocol_identity(self) -> None:
        viewer = viewer_from_auth_context(
            {
                "role": "seat",
                "seat": 2,
                "player_id": 2,
                "legacy_player_id": 2,
                "public_player_id": "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "seat_id": "seat_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "viewer_id": "view_cccccccc-cccc-cccc-cccc-cccccccccccc",
                "seat_index": 2,
                "turn_order_index": 2,
                "player_label": "P2",
            },
            session_id="sess_identity",
        )

        self.assertEqual(viewer.session_id, "sess_identity")
        self.assertEqual(viewer.player_id, 2)
        self.assertEqual(viewer.public_player_id, "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(viewer.seat_id, "seat_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        self.assertEqual(viewer.viewer_id, "view_cccccccc-cccc-cccc-cccc-cccccccccccc")
        self.assertEqual(viewer.player_label, "P2")

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

    def test_public_identity_decision_ack_uses_legacy_bridge_for_target_delivery(self) -> None:
        ack = {
            "type": "decision_ack",
            "payload": {
                "request_id": "req_public_ack",
                "status": "accepted",
                "player_id": "ply_public_1",
                "primary_player_id": "ply_public_1",
                "primary_player_id_source": "public",
                "legacy_player_id": 1,
                "public_player_id": "ply_public_1",
                "seat_id": "seat_public_1",
                "viewer_id": "view_public_1",
            },
        }

        target = project_stream_message_for_viewer(ack, ViewerContext(role="seat", player_id=1))
        other = project_stream_message_for_viewer(ack, ViewerContext(role="seat", player_id=2))
        spectator = project_stream_message_for_viewer(ack, ViewerContext(role="spectator"))

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["request_id"], "req_public_ack")
        self.assertIsNone(other)
        self.assertIsNone(spectator)

    def test_public_identity_decision_ack_targets_viewer_without_numeric_bridge(self) -> None:
        ack = {
            "type": "decision_ack",
            "payload": {
                "request_id": "req_public_only_ack",
                "status": "accepted",
                "player_id": "ply_public_1",
                "primary_player_id": "ply_public_1",
                "primary_player_id_source": "public",
                "public_player_id": "ply_public_1",
                "seat_id": "seat_public_1",
                "viewer_id": "view_public_1",
            },
        }

        target = project_stream_message_for_viewer(
            ack,
            ViewerContext(
                role="seat",
                public_player_id="ply_public_1",
                seat_id="seat_public_1",
                viewer_id="view_public_1",
            ),
        )
        other = project_stream_message_for_viewer(
            ack,
            ViewerContext(
                role="seat",
                public_player_id="ply_public_2",
                seat_id="seat_public_2",
                viewer_id="view_public_2",
            ),
        )
        spectator = project_stream_message_for_viewer(ack, ViewerContext(role="spectator"))

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["request_id"], "req_public_only_ack")
        self.assertIsNone(other)
        self.assertIsNone(spectator)

    def test_public_identity_prompt_uses_legacy_bridge_for_target_delivery(self) -> None:
        prompt = {
            "type": "prompt",
            "payload": {
                "request_id": "req_public_prompt",
                "request_type": "movement",
                "player_id": "ply_public_1",
                "primary_player_id": "ply_public_1",
                "primary_player_id_source": "public",
                "legacy_player_id": 1,
                "public_player_id": "ply_public_1",
                "seat_id": "seat_public_1",
                "viewer_id": "view_public_1",
                "legal_choices": [{"choice_id": "roll"}],
                "public_context": {},
            },
        }

        target = project_stream_message_for_viewer(prompt, ViewerContext(role="seat", player_id=1))
        other = project_stream_message_for_viewer(prompt, ViewerContext(role="seat", player_id=2))
        spectator = project_stream_message_for_viewer(prompt, ViewerContext(role="spectator"))

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["request_id"], "req_public_prompt")
        self.assertIsNone(other)
        self.assertIsNone(spectator)

    def test_public_identity_prompt_targets_viewer_without_numeric_bridge(self) -> None:
        prompt = {
            "type": "prompt",
            "payload": {
                "request_id": "req_public_only_prompt",
                "request_type": "movement",
                "player_id": "ply_public_1",
                "primary_player_id": "ply_public_1",
                "primary_player_id_source": "public",
                "public_player_id": "ply_public_1",
                "seat_id": "seat_public_1",
                "viewer_id": "view_public_1",
                "legal_choices": [{"choice_id": "roll"}],
                "public_context": {},
            },
        }

        target = project_stream_message_for_viewer(
            prompt,
            ViewerContext(
                role="seat",
                public_player_id="ply_public_1",
                seat_id="seat_public_1",
                viewer_id="view_public_1",
            ),
        )
        other = project_stream_message_for_viewer(
            prompt,
            ViewerContext(
                role="seat",
                public_player_id="ply_public_2",
                seat_id="seat_public_2",
                viewer_id="view_public_2",
            ),
        )
        spectator = project_stream_message_for_viewer(prompt, ViewerContext(role="spectator"))

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["request_id"], "req_public_only_prompt")
        self.assertIsNone(other)
        self.assertIsNone(spectator)

    def test_public_identity_decision_event_targets_viewer_without_numeric_bridge(self) -> None:
        event = {
            "type": "event",
            "payload": {
                "event_type": "decision_requested",
                "request_id": "req_public_only_trick",
                "request_type": "hidden_trick_card",
                "player_id": "ply_public_1",
                "primary_player_id": "ply_public_1",
                "primary_player_id_source": "public",
                "public_player_id": "ply_public_1",
                "seat_id": "seat_public_1",
                "viewer_id": "view_public_1",
                "public_context": {
                    "full_hand": [{"deck_index": 11, "name": "재뿌리기"}],
                    "hidden_trick_deck_index": 11,
                },
            },
        }

        target = project_stream_message_for_viewer(
            event,
            ViewerContext(role="seat", public_player_id="ply_public_1", seat_id="seat_public_1"),
        )
        other = project_stream_message_for_viewer(
            event,
            ViewerContext(role="seat", public_player_id="ply_public_2", seat_id="seat_public_2"),
        )

        self.assertIsNotNone(target)
        self.assertEqual(target["payload"]["request_id"], "req_public_only_trick")
        self.assertIsNone(other)

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

    def test_target_viewer_keeps_public_identity_embedded_view_state_prompt(self) -> None:
        event = {
            "type": "event",
            "payload": {
                "event_type": "turn_start",
                "view_state": {
                    "hand_tray": {
                        "cards": [{"deck_index": 11, "name": "재뿌리기"}],
                    },
                    "prompt": {
                        "active": {
                            "request_id": "req_public_trick",
                            "request_type": "trick_to_use",
                            "player_id": "ply_public_1",
                            "primary_player_id": "ply_public_1",
                            "primary_player_id_source": "public",
                            "public_player_id": "ply_public_1",
                            "seat_id": "seat_public_1",
                            "choices": [{"choice_id": "card-11"}],
                            "public_context": {"full_hand": [{"deck_index": 11, "name": "재뿌리기"}]},
                        }
                    },
                    "players": {"items": []},
                },
            },
        }

        projected = project_stream_message_for_viewer(
            event,
            ViewerContext(role="seat", public_player_id="ply_public_1", seat_id="seat_public_1"),
        )

        self.assertIsNotNone(projected)
        view_state = projected["payload"]["view_state"]
        self.assertEqual(view_state["prompt"]["active"]["request_id"], "req_public_trick")
        self.assertNotIn("hand_tray", view_state)
        self.assertEqual(view_state["players"], {"items": []})


if __name__ == "__main__":
    unittest.main()
