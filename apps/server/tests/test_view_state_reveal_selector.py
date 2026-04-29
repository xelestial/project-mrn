from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.view_state.board_selector import build_board_view_state
from apps.server.src.domain.view_state.reveal_selector import build_reveals_view_state
from apps.server.src.services.stream_service import StreamService


class ViewStateRevealSelectorTests(unittest.TestCase):
    def test_build_reveals_view_state_projects_current_turn_in_canonical_order(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 100,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "turn_start",
                    "round_index": 4,
                    "turn_index": 2,
                    "acting_player_id": 2,
                    "character": "산적",
                },
            },
            {
                "type": "event",
                "seq": 101,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "weather_reveal",
                    "round_index": 4,
                    "turn_index": 2,
                    "weather_name": "Cold Front",
                },
            },
            {
                "type": "event",
                "seq": 102,
                "session_id": "s1",
                "server_time_ms": 3,
                "payload": {
                    "event_type": "tile_purchased",
                    "round_index": 4,
                    "turn_index": 2,
                    "player_id": 2,
                    "tile_index": 9,
                    "cost": 3,
                },
            },
            {
                "type": "event",
                "seq": 103,
                "session_id": "s1",
                "server_time_ms": 4,
                "payload": {
                    "event_type": "player_move",
                    "round_index": 4,
                    "turn_index": 2,
                    "acting_player_id": 2,
                    "from_tile_index": 3,
                    "to_tile_index": 9,
                    "path": [4, 5, 6, 7, 8, 9],
                },
            },
            {
                "type": "event",
                "seq": 104,
                "session_id": "s1",
                "server_time_ms": 5,
                "payload": {
                    "event_type": "landing_resolved",
                    "round_index": 4,
                    "turn_index": 2,
                    "acting_player_id": 2,
                    "tile_index": 9,
                    "result": "PURCHASE",
                },
            },
            {
                "type": "event",
                "seq": 105,
                "session_id": "s1",
                "server_time_ms": 6,
                "payload": {
                    "event_type": "fortune_resolved",
                    "round_index": 4,
                    "turn_index": 2,
                    "player_id": 2,
                    "tile_index": 9,
                    "summary": "Gain 2 cash.",
                },
            },
        ]

        view_state = build_reveals_view_state(messages, limit=6)

        self.assertIsNotNone(view_state)
        self.assertEqual(view_state["round_index"], 4)
        self.assertEqual(view_state["turn_index"], 2)
        self.assertEqual(
            [item["event_code"] for item in view_state["items"]],
            ["weather_reveal", "player_move", "landing_resolved", "tile_purchased", "fortune_resolved"],
        )
        self.assertEqual(view_state["items"][1]["focus_tile_index"], 9)
        self.assertEqual(view_state["items"][3]["tone"], "economy")
        self.assertTrue(view_state["items"][0]["is_interrupt"])
        self.assertTrue(view_state["items"][-1]["is_interrupt"])

    def test_build_board_view_state_projects_latest_move(self) -> None:
        view_state = build_board_view_state(
            [
                {
                    "type": "event",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "player_move",
                        "acting_player_id": 3,
                        "from_tile_index": 17,
                        "to_tile_index": 30,
                        "path": [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
                    },
                }
            ]
        )

        self.assertEqual(
            view_state,
            {
                "last_move": {
                    "player_id": 3,
                    "from_tile_index": 17,
                    "to_tile_index": 30,
                    "path_tile_indices": [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
                },
                "tiles": [],
            },
        )

    def test_action_move_updates_board_and_reveal_like_move_event(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "turn_start",
                    "round_index": 1,
                    "turn_index": 1,
                    "acting_player_id": 1,
                },
            },
            {
                "type": "event",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "turn_end_snapshot",
                    "round_index": 1,
                    "turn_index": 1,
                    "snapshot": {
                        "players": [{"player_id": 1, "position": 3, "alive": True}],
                        "board": {"tiles": [{"tile_index": 3}, {"tile_index": 8}]},
                    },
                },
            },
            {
                "type": "event",
                "seq": 3,
                "session_id": "s1",
                "server_time_ms": 3,
                "payload": {
                    "event_type": "action_move",
                    "round_index": 1,
                    "turn_index": 1,
                    "acting_player_id": 1,
                    "from_tile_index": 3,
                    "to_tile_index": 8,
                    "path": [4, 5, 6, 7, 8],
                },
            },
        ]

        board = build_board_view_state(messages)
        reveals = build_reveals_view_state(messages)

        self.assertEqual(board["last_move"]["to_tile_index"], 8)
        self.assertEqual(board["tiles"][1]["pawn_player_ids"], [1])
        self.assertEqual([item["event_code"] for item in reveals["items"]], ["action_move"])
        self.assertEqual(reveals["items"][0]["tone"], "move")
        self.assertEqual(reveals["items"][0]["focus_tile_index"], 8)

    def test_stream_service_publishes_additive_reveals_and_board_projection(self) -> None:
        stream = StreamService()

        async def _publish() -> list[dict]:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 5,
                    "turn_index": 1,
                    "acting_player_id": 1,
                    "character": "산적",
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "dice_roll",
                    "round_index": 5,
                    "turn_index": 1,
                    "acting_player_id": 1,
                    "total_move": 6,
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "player_move",
                    "round_index": 5,
                    "turn_index": 1,
                    "acting_player_id": 1,
                    "from_tile_index": 2,
                    "to_tile_index": 8,
                    "path": [3, 4, 5, 6, 7, 8],
                },
            )
            snapshot = await stream.snapshot("sess_1")
            return [message.to_dict() for message in snapshot]

        events = asyncio.run(_publish())
        latest_payload = events[-1]["payload"]

        self.assertIn("view_state", latest_payload)
        self.assertEqual(
            [item["event_code"] for item in latest_payload["view_state"]["reveals"]["items"]],
            ["dice_roll", "player_move"],
        )
        self.assertEqual(
            latest_payload["view_state"]["board"]["last_move"],
            {
                "player_id": 1,
                "from_tile_index": 2,
                "to_tile_index": 8,
                "path_tile_indices": [3, 4, 5, 6, 7, 8],
            },
        )
