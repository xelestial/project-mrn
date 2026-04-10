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
