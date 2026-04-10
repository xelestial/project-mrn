from __future__ import annotations

import unittest

from apps.server.src.domain.view_state.hand_selector import build_hand_tray_view_state


class ViewStateHandSelectorTests(unittest.TestCase):
    def test_build_hand_tray_view_state_projects_active_full_hand(self) -> None:
        view_state = build_hand_tray_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_trick_1",
                        "request_type": "trick_to_use",
                        "player_id": 1,
                        "public_context": {
                            "full_hand": [
                                {
                                    "deck_index": 11,
                                    "name": "건강 검진",
                                    "card_description": "통행료를 절반으로 낮춥니다.",
                                    "is_hidden": False,
                                },
                                {
                                    "deck_index": 12,
                                    "name": "뒷거래",
                                    "card_description": "현금을 얻습니다.",
                                    "is_hidden": True,
                                    "is_current_target": True,
                                },
                            ]
                        },
                    },
                }
            ]
        )

        self.assertEqual(
            view_state,
            {
                "cards": [
                    {
                        "key": "11-0-건강 검진",
                        "name": "건강 검진",
                        "description": "통행료를 절반으로 낮춥니다.",
                        "deck_index": 11,
                        "is_hidden": False,
                        "is_current_target": False,
                    },
                    {
                        "key": "12-1-뒷거래",
                        "name": "뒷거래",
                        "description": "현금을 얻습니다.",
                        "deck_index": 12,
                        "is_hidden": True,
                        "is_current_target": True,
                    },
                ]
            },
        )

    def test_build_hand_tray_view_state_falls_back_to_latest_persisted_burden_cards(self) -> None:
        view_state = build_hand_tray_view_state(
            [
                {
                    "type": "prompt",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "request_id": "req_burden_1",
                        "request_type": "burden_exchange",
                        "player_id": 1,
                        "public_context": {
                            "burden_cards": [
                                {
                                    "deck_index": 91,
                                    "name": "무거운 짐",
                                    "card_description": "이동 -1",
                                    "is_current_target": True,
                                }
                            ]
                        },
                    },
                },
                {
                    "type": "decision_ack",
                    "seq": 2,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "request_id": "req_burden_1",
                        "status": "accepted",
                    },
                },
            ]
        )

        self.assertEqual(
            view_state,
            {
                "cards": [
                    {
                        "key": "91-0-무거운 짐",
                        "name": "무거운 짐",
                        "description": "이동 -1",
                        "deck_index": 91,
                        "is_hidden": False,
                        "is_current_target": True,
                    }
                ]
            },
        )
