from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.visibility import ViewerContext
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

    def test_active_slots_persist_round_faces_across_turn_start(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "round_order",
                    "active_by_card": {
                        "2": "산적",
                        "5": "교리 감독관",
                        "6": "박수",
                    },
                },
            },
            {
                "type": "event",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "turn_end_snapshot",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {"player_id": 1, "display_name": "Player 1", "character": "자객"},
                            {"player_id": 2, "display_name": "Player 2", "character": "교리 연구관"},
                            {"player_id": 3, "display_name": "Player 3", "character": "만신"},
                        ],
                        "board": {
                            "marker_owner_player_id": 1,
                        },
                    },
                },
            },
            {
                "type": "event",
                "seq": 3,
                "session_id": "s1",
                "server_time_ms": 3,
                "payload": {
                    "event_type": "turn_start",
                    "acting_player_id": 1,
                    "character": "산적",
                },
            },
        ]

        active_slots = build_active_slots_view_state(messages)

        self.assertIsNotNone(active_slots)
        self.assertEqual(active_slots["items"][1]["character"], "산적")
        self.assertEqual(active_slots["items"][4]["character"], "교리 감독관")
        self.assertEqual(active_slots["items"][5]["character"], "박수")

    def test_active_slots_can_be_built_from_manifest_active_faces_before_snapshot_exists(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "parameter_manifest",
                    "manifest_hash": "hash_a",
                    "active_by_card": {
                        "1": "어사",
                        "2": "산적",
                        "3": "탈출 노비",
                        "4": "아전",
                        "5": "교리 감독관",
                        "6": "만신",
                        "7": "중매꾼",
                        "8": "사기꾼",
                    },
                },
            }
        ]

        active_slots = build_active_slots_view_state(messages)

        self.assertIsNotNone(active_slots)
        self.assertEqual([item["character"] for item in active_slots["items"]], ["어사", "산적", "탈출 노비", "아전", "교리 감독관", "만신", "중매꾼", "사기꾼"])

    def test_stream_service_keeps_mark_target_candidates_visible_after_turn_start(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "round_order",
                    "active_by_card": {
                        "2": "산적",
                        "3": "탈출 노비",
                        "4": "아전",
                        "5": "교리 감독관",
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {"player_id": 1, "display_name": "Player 1", "character": "자객"},
                        ],
                        "board": {
                            "marker_owner_player_id": 1,
                        },
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_start",
                    "acting_player_id": 1,
                    "character": "산적",
                },
            )
            prompt = await stream.publish(
                "sess_1",
                "prompt",
                {
                    "request_id": "req_mark_live",
                    "request_type": "mark_target",
                    "player_id": 1,
                    "legal_choices": [
                        {"choice_id": "탈출 노비", "title": "탈출 노비", "value": {"target_character": "탈출 노비", "target_card_no": 3}},
                        {"choice_id": "아전", "title": "아전", "value": {"target_character": "아전", "target_card_no": 4}},
                        {"choice_id": "교리 감독관", "title": "교리 감독관", "value": {"target_character": "교리 감독관", "target_card_no": 5}},
                        {"choice_id": "none", "title": "지목 안 함"},
                    ],
                    "public_context": {
                        "actor_name": "산적",
                    },
                },
            )
            projected = await stream.project_message_for_viewer(
                prompt.to_dict(),
                ViewerContext(role="seat", session_id="sess_1", player_id=1),
            )
            return projected["payload"]["view_state"]

        view_state = asyncio.run(_publish())

        self.assertEqual(
            view_state["mark_target"]["candidates"],
            [
                {"slot": 3, "player_id": None, "label": None, "character": "탈출 노비"},
                {"slot": 4, "player_id": None, "label": None, "character": "아전"},
                {"slot": 5, "player_id": None, "label": None, "character": "교리 감독관"},
            ],
        )

    def test_stream_service_projects_full_active_slots_from_prompt_public_context_active_faces(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {"player_id": 1, "display_name": "Player 1", "character": "만신"},
                            {"player_id": 2, "display_name": "Player 2", "character": "객주"},
                            {"player_id": 3, "display_name": "Player 3", "character": "사기꾼"},
                        ],
                        "board": {
                            "marker_owner_player_id": 1,
                        },
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_start",
                    "acting_player_id": 1,
                    "character": "만신",
                },
            )
            prompt = await stream.publish(
                "sess_1",
                "prompt",
                {
                    "request_id": "req_hidden_live",
                    "request_type": "hidden_trick_card",
                    "player_id": 1,
                    "legal_choices": [],
                    "public_context": {
                        "actor_name": "만신",
                        "active_by_card": {
                            1: "탐관오리",
                            2: "산적",
                            3: "추노꾼",
                            4: "파발꾼",
                            5: "교리 감독관",
                            6: "만신",
                            7: "중매꾼",
                            8: "사기꾼",
                        },
                    },
                },
            )
            projected = await stream.project_message_for_viewer(
                prompt.to_dict(),
                ViewerContext(role="seat", session_id="sess_1", player_id=1),
            )
            return projected["payload"]["view_state"]

        view_state = asyncio.run(_publish())

        self.assertEqual(
            [item["character"] for item in view_state["active_slots"]["items"]],
            ["탐관오리", "산적", "추노꾼", "파발꾼", "교리 감독관", "만신", "중매꾼", "사기꾼"],
        )

    def test_stream_service_keeps_round_active_faces_visible_immediately_after_round_start(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {"player_id": 1, "display_name": "Player 1", "character": "만신"},
                            {"player_id": 2, "display_name": "Player 2", "character": "객주"},
                            {"player_id": 3, "display_name": "Player 3", "character": "사기꾼"},
                            {"player_id": 4, "display_name": "Player 4", "character": "자객"},
                        ],
                        "board": {
                            "marker_owner_player_id": 1,
                        },
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "round_start",
                    "marker_owner_player_id": 1,
                    "marker_draft_direction": "clockwise",
                    "active_by_card": {
                        1: "탐관오리",
                        2: "산적",
                        3: "탈출 노비",
                        4: "아전",
                        5: "교리 감독관",
                        6: "만신",
                        7: "중매꾼",
                        8: "사기꾼",
                    },
                },
            )
            await stream.publish(
                "sess_1",
                "prompt",
                {
                    "request_id": "req_draft_live",
                    "request_type": "draft_card",
                    "player_id": 1,
                    "legal_choices": [],
                    "public_context": {
                        "actor_name": "만신",
                    },
                },
            )
            snapshot = await stream.snapshot("sess_1")
            return snapshot[-1].to_dict()["payload"]["view_state"]

        view_state = asyncio.run(_publish())

        self.assertEqual(
            [item["character"] for item in view_state["active_slots"]["items"]],
            ["탐관오리", "산적", "탈출 노비", "아전", "교리 감독관", "만신", "중매꾼", "사기꾼"],
        )

    def test_stream_service_preserves_active_faces_when_round_order_omits_active_by_card(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "round_start",
                    "marker_owner_player_id": 1,
                    "marker_draft_direction": "clockwise",
                    "active_by_card": {
                        1: "탐관오리",
                        2: "산적",
                        3: "탈출 노비",
                        4: "아전",
                        5: "교리 감독관",
                        6: "만신",
                        7: "중매꾼",
                        8: "사기꾼",
                    },
                    "players": [
                        {"player_id": 1, "display_name": "Player 1", "character": "자객"},
                        {"player_id": 2, "display_name": "Player 2", "character": "교리 연구관"},
                        {"player_id": 3, "display_name": "Player 3", "character": "만신"},
                        {"player_id": 4, "display_name": "Player 4", "character": "탐관오리"},
                    ],
                },
            )
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "round_order",
                    "order": [3, 2, 4, 1],
                },
            )
            await stream.publish(
                "sess_1",
                "prompt",
                {
                    "request_id": "req_draft_live",
                    "request_type": "draft_card",
                    "player_id": 3,
                    "public_context": {
                        "actor_name": "만신",
                    },
                },
            )
            snapshot = await stream.snapshot("sess_1")
            return snapshot[-1].to_dict()["payload"]["view_state"]

        view_state = asyncio.run(_publish())

        self.assertEqual(
            [item["character"] for item in view_state["active_slots"]["items"]],
            ["탐관오리", "산적", "탈출 노비", "아전", "교리 감독관", "만신", "중매꾼", "사기꾼"],
        )

    def test_stream_service_projects_active_faces_immediately_after_session_start(self) -> None:
        stream = StreamService()

        async def _publish() -> dict:
            await stream.publish(
                "sess_1",
                "event",
                {
                    "event_type": "session_start",
                    "player_count": 4,
                    "active_by_card": {
                        1: "어사",
                        2: "자객",
                        3: "추노꾼",
                        4: "아전",
                        5: "교리 감독관",
                        6: "박수",
                        7: "객주",
                        8: "건설업자",
                    },
                    "players": [
                        {"player_id": 1, "display_name": "Player 1", "character": "자객"},
                        {"player_id": 2, "display_name": "Player 2", "character": "교리 연구관"},
                        {"player_id": 3, "display_name": "Player 3", "character": "만신"},
                        {"player_id": 4, "display_name": "Player 4", "character": "탐관오리"},
                    ],
                },
            )
            snapshot = await stream.snapshot("sess_1")
            return snapshot[-1].to_dict()["payload"]["view_state"]

        view_state = asyncio.run(_publish())

        self.assertEqual(
            [item["character"] for item in view_state["active_slots"]["items"]],
            ["어사", "자객", "추노꾼", "아전", "교리 감독관", "박수", "객주", "건설업자"],
        )

    def test_player_view_state_keeps_character_hidden_until_turn_start(self) -> None:
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
                            {"player_id": 1, "display_name": "P1"},
                            {"player_id": 2, "display_name": "P2"},
                        ],
                        "board": {"marker_owner_player_id": 1},
                    },
                },
            },
            {
                "type": "event",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "decision_requested",
                    "player_id": 1,
                    "request_type": "final_character",
                    "public_context": {"actor_name": "객주"},
                },
            },
            {
                "type": "prompt",
                "seq": 3,
                "session_id": "s1",
                "server_time_ms": 3,
                "payload": {
                    "player_id": 1,
                    "request_type": "final_character",
                    "public_context": {"actor_name": "객주"},
                },
            },
        ]

        hidden_view = build_player_view_state(messages)
        self.assertEqual([item["current_character_face"] for item in hidden_view["items"]], ["-", "-"])

        messages.append(
            {
                "type": "event",
                "seq": 4,
                "session_id": "s1",
                "server_time_ms": 4,
                "payload": {
                    "event_type": "turn_start",
                    "acting_player_id": 1,
                    "character": "객주",
                },
            }
        )

        revealed_view = build_player_view_state(messages)
        self.assertEqual(revealed_view["items"][0]["current_character_face"], "객주")

    def test_player_view_state_overlays_latest_prompt_resource_and_hand_context(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "turn_start",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {
                                "player_id": 1,
                                "display_name": "Player 1",
                                "cash": 20,
                                "shards": 4,
                                "trick_count": 6,
                                "hidden_trick_count": 1,
                                "public_tricks": ["거대한 산불", "무거운 짐", "무역의 선물"],
                            }
                        ],
                        "board": {"marker_owner_player_id": 1},
                    },
                },
            },
            {
                "type": "prompt",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "request_id": "req_hide",
                    "request_type": "hidden_trick_card",
                    "player_id": 1,
                    "public_context": {
                        "player_cash": 20,
                        "player_shards": 6,
                        "hand_count": 5,
                        "hidden_trick_count": 0,
                        "full_hand": [
                            {"name": "무거운 짐", "deck_index": 8, "is_hidden": False},
                            {"name": "극심한 분리불안", "deck_index": 19, "is_hidden": False},
                            {"name": "느슨함 혐오자", "deck_index": 31, "is_hidden": False},
                            {"name": "가벼운 짐", "deck_index": 10, "is_hidden": False},
                            {"name": "무역의 선물", "deck_index": 33, "is_hidden": False},
                        ],
                    },
                },
            },
        ]

        view_state = build_player_view_state(messages)
        player = view_state["items"][0]

        self.assertEqual(player["shards"], 6)
        self.assertEqual(player["trick_count"], 5)
        self.assertEqual(player["hidden_trick_count"], 0)
        self.assertNotIn("거대한 산불", player["public_tricks"])

    def test_player_view_state_overlays_direct_trick_visibility_events(self) -> None:
        messages = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 1,
                "payload": {
                    "event_type": "trick_used",
                    "acting_player_id": 1,
                    "snapshot": {
                        "players": [
                            {
                                "player_id": 1,
                                "display_name": "Player 1",
                                "cash": 20,
                                "shards": 5,
                                "trick_count": 3,
                                "hidden_trick_count": 0,
                                "public_tricks": ["이럇!", "마당발", "극도의 느슨함 혐오자"],
                            }
                        ],
                        "board": {"marker_owner_player_id": 1},
                    },
                },
            },
            {
                "type": "event",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 2,
                "payload": {
                    "event_type": "trick_window_closed",
                    "acting_player_id": 1,
                    "hand_count": 3,
                    "hidden_trick_count": 1,
                    "public_tricks": ["마당발", "극도의 느슨함 혐오자"],
                },
            },
        ]

        view_state = build_player_view_state(messages)
        player = view_state["items"][0]

        self.assertEqual(player["trick_count"], 3)
        self.assertEqual(player["hidden_trick_count"], 1)
        self.assertEqual(player["public_tricks"], ["마당발", "극도의 느슨함 혐오자"])


def _project_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[3]


def _load_player_fixture():
    import json

    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.player.mark_target_visibility.json"
    return json.loads(path.read_text(encoding="utf-8"))
