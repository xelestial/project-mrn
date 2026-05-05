from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.domain.view_state.scene_selector import build_scene_view_state
from apps.server.src.services.stream_service import StreamService
from apps.server.tests.prompt_payloads import module_prompt


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_scene_fixture() -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.scene.turn_resolution.json"
    return json.loads(path.read_text(encoding="utf-8"))


class ViewStateSceneSelectorTests(unittest.TestCase):
    def test_build_scene_view_state_matches_shared_fixture_contract(self) -> None:
        fixture = _load_scene_fixture()
        view_state = build_scene_view_state(fixture["messages"])

        self.assertEqual(view_state, fixture["expected"]["scene"])

    def test_stream_service_publishes_additive_scene_projection(self) -> None:
        stream = StreamService()

        async def _publish() -> list[dict]:
            await stream.publish(
                "sess_scene_1",
                "event",
                {
                    "event_type": "player_move",
                    "round_index": 5,
                    "turn_index": 9,
                    "acting_player_id": 2,
                    "from_tile_index": 5,
                    "to_tile_index": 11,
                },
            )
            snapshot = await stream.snapshot("sess_scene_1")
            return [message.to_dict() for message in snapshot]

        events = asyncio.run(_publish())
        latest_payload = events[-1]["payload"]

        self.assertIn("view_state", latest_payload)
        self.assertIn("scene", latest_payload["view_state"])
        self.assertEqual(latest_payload["view_state"]["scene"]["core_action_feed"][0]["event_code"], "player_move")

    def test_action_move_is_projected_as_move_scene_event(self) -> None:
        view_state = build_scene_view_state(
            [
                {
                    "type": "event",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "action_move",
                        "round_index": 1,
                        "turn_index": 1,
                        "acting_player_id": 1,
                        "from_tile_index": 3,
                        "to_tile_index": 8,
                    },
                }
            ]
        )

        self.assertEqual(view_state["core_action_feed"][0]["event_code"], "action_move")
        self.assertEqual(view_state["theater_feed"][0]["event_code"], "action_move")
        self.assertEqual(view_state["theater_feed"][0]["tone"], "move")

    def test_stream_service_publishes_scene_weather_from_prompt_public_context(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_scene_weather",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 2,
                    "turn_index": 3,
                    "acting_player_id": 1,
                    "character": "만신",
                },
            )
            await stream.publish(
                "sess_scene_weather",
                "prompt",
                module_prompt({
                    "request_id": "req_hidden_live",
                    "request_type": "hidden_trick_card",
                    "player_id": 1,
                    "public_context": {
                        "round_index": 2,
                        "turn_index": 3,
                        "actor_name": "만신",
                        "weather_name": "긴급 피난",
                        "weather_effect": "모든 짐 제거 비용이 2배가 됩니다.",
                    },
                }),
            )
            projected = await stream.latest_view_commit_message_for_viewer(
                "sess_scene_weather",
                ViewerContext(role="seat", session_id="sess_scene_weather", player_id=1),
            )
            return projected["payload"]["view_state"]["scene"]["situation"]

        situation = asyncio.run(_publish())

        self.assertEqual(situation["weather_name"], "긴급 피난")
        self.assertEqual(situation["weather_effect"], "모든 짐 제거 비용이 2배가 됩니다.")
