from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

import tempfile
from pathlib import Path
from unittest import TestCase

from board_layout_creator import load_board_config, load_board_config_from_csv, load_board_config_from_json
from config import DEFAULT_CONFIG

_MODULE_DIR = Path(__file__).resolve().parent


class BoardLayoutCreatorTest(TestCase):
    def test_json_layout_matches_default_board(self):
        runtime_config = load_board_config_from_json(_MODULE_DIR / "board_layout.json")
        self.assertEqual(runtime_config.build_tile_metadata(), DEFAULT_CONFIG.board.build_tile_metadata())
        self.assertEqual(runtime_config.f1_increment, DEFAULT_CONFIG.board.f1_increment)
        self.assertEqual(runtime_config.special_tile_s_display_name, DEFAULT_CONFIG.board.special_tile_s_display_name)

    def test_csv_layout_with_sidecar_metadata_matches_default_board(self):
        runtime_config = load_board_config_from_csv(_MODULE_DIR / "board_layout.csv")
        self.assertEqual(runtime_config.build_tile_metadata(), DEFAULT_CONFIG.board.build_tile_metadata())
        self.assertEqual(runtime_config.f2_shards, DEFAULT_CONFIG.board.f2_shards)
        self.assertEqual(runtime_config.zone_colors, DEFAULT_CONFIG.board.zone_colors)

    def test_csv_layout_with_explicit_metadata_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "alt_layout.csv"
            meta_path = tmp_path / "alt_meta.json"
            csv_path.write_text((_MODULE_DIR / "board_layout.csv").read_text(encoding="utf-8"), encoding="utf-8")
            meta_path.write_text((_MODULE_DIR / "board_layout_meta.json").read_text(encoding="utf-8"), encoding="utf-8")
            runtime_config = load_board_config(csv_path, metadata_path=meta_path)
        self.assertEqual(runtime_config.special_tile_s_display_name, DEFAULT_CONFIG.board.special_tile_s_display_name)
        self.assertEqual(runtime_config.malicious_land_multiplier, DEFAULT_CONFIG.board.malicious_land_multiplier)
