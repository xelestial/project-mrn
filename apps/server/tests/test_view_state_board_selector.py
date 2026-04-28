from __future__ import annotations

import json
import unittest
from pathlib import Path

from apps.server.src.domain.view_state.board_selector import build_board_view_state


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_board_fixture() -> dict:
    path = _project_root() / "packages" / "runtime-contracts" / "ws" / "examples" / "selector.board.live_tiles.json"
    return json.loads(path.read_text(encoding="utf-8"))


class ViewStateBoardSelectorTests(unittest.TestCase):
    def test_build_board_view_state_matches_shared_fixture_contract(self) -> None:
        fixture = _load_board_fixture()
        view_state = build_board_view_state(fixture["messages"])
        self.assertEqual(view_state, fixture["expected"]["board"])

    def test_build_board_view_state_projects_live_end_timer_after_trick(self) -> None:
        view_state = build_board_view_state(
            [
                {
                    "type": "event",
                    "seq": 1,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "turn_end_snapshot",
                        "snapshot": {
                            "players": [{"player_id": 1, "position": 0, "alive": True}],
                            "board": {
                                "f_value": 2,
                                "marker_owner_player_id": 1,
                                "tiles": [{"tile_index": 0, "pawn_player_ids": [1]}],
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
                        "event_type": "f_value_change",
                        "acting_player_id": 1,
                        "after": 3,
                    },
                },
                {
                    "type": "event",
                    "seq": 3,
                    "session_id": "s1",
                    "server_time_ms": 3,
                    "payload": {
                        "event_type": "trick_used",
                        "acting_player_id": 1,
                        "f_value": 3,
                    },
                },
            ]
        )

        self.assertEqual(view_state["f_value"], 3)
