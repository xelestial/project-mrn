from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.view_state.player_selector import (
    build_active_slots_view_state,
    build_mark_target_view_state,
    build_player_view_state,
)
from apps.server.src.services.stream_service import StreamService


class ViewStatePlayerSelectorTests(unittest.TestCase):
    def test_build_player_ordering_view_state_starts_from_marker_owner_and_direction(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "turn_end_snapshot",
                    "snapshot": {
                        "players": [
                            {"player_id": 1},
                            {"player_id": 2},
                            {"player_id": 3},
                            {"player_id": 4},
                        ],
                        "board": {
                            "marker_owner_player_id": 2,
                        },
                    },
                },
            },
            {
                "type": "event",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "marker_transferred",
                    "to_player_id": 2,
                    "draft_direction": "counterclockwise",
                },
            },
        ]

        view_state = build_player_view_state(messages)

        self.assertEqual(view_state["ordered_player_ids"], [2, 1, 4, 3])
        self.assertEqual(view_state["marker_owner_player_id"], 2)
        self.assertEqual(view_state["marker_draft_direction"], "counterclockwise")

    def test_stream_service_publishes_additive_view_state_players_projection(self) -> None:
        stream = StreamService()

        async def _publish() -> list[dict]:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "snapshot": {
                        "players": [
                            {"player_id": 1},
                            {"player_id": 2},
                            {"player_id": 3},
                        ],
                        "board": {
                            "marker_owner_player_id": 2,
                        },
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "round_start",
                    "marker_owner_player_id": 2,
                    "marker_draft_direction": "clockwise",
                },
            )
            snapshot = await stream.snapshot("sess_1")
            return [message.to_dict() for message in snapshot]

        events = asyncio.run(_publish())
        latest_payload = events[-1]["payload"]

        self.assertIn("view_state", latest_payload)
        self.assertEqual(latest_payload["view_state"]["players"]["ordered_player_ids"], [2, 3, 1])
        self.assertEqual(latest_payload["view_state"]["players"]["marker_owner_player_id"], 2)
        self.assertEqual(latest_payload["view_state"]["players"]["marker_draft_direction"], "clockwise")

    def test_builds_active_slots_and_mark_target_from_prompt_rehydration(self) -> None:
        fixture = _load_player_fixture()
        messages = fixture["messages"]

        players = build_player_view_state(messages)
        active_slots = build_active_slots_view_state(messages)
        mark_target = build_mark_target_view_state(messages)

        self.assertEqual(players, fixture["expected"]["players"])
        self.assertEqual(active_slots, fixture["expected"]["active_slots"])
        self.assertEqual(mark_target, fixture["expected"]["mark_target"])


def _project_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[3]


def _load_player_fixture():
    import json

    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.player.mark_target_visibility.json"
    return json.loads(path.read_text(encoding="utf-8"))
