from __future__ import annotations

import json
import unittest
from pathlib import Path

from apps.server.src.services.parameter_service import GameParameterResolver, PublicManifestBuilder


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _current_snapshot_payload() -> dict:
    resolver = GameParameterResolver()
    builder = PublicManifestBuilder()
    resolved = resolver.resolve({"seed": 42})
    manifest = builder.build_public_manifest(resolved)
    return {
        "manifest_version": manifest.get("manifest_version"),
        "manifest_hash": manifest.get("manifest_hash"),
        "source_fingerprints": manifest.get("source_fingerprints", {}),
        "board_tile_count": manifest.get("board", {}).get("tile_count"),
        "seat_limits": manifest.get("seats", {}),
        "dice_values": manifest.get("dice", {}).get("values", []),
    }


class ParameterManifestSnapshotTests(unittest.TestCase):
    def test_snapshot_file_is_in_sync(self) -> None:
        root = _project_root()
        snapshot_path = root / "tools" / "parameter_manifest_snapshot.json"
        self.assertTrue(snapshot_path.exists(), f"Snapshot file not found: {snapshot_path}")
        expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
        current = _current_snapshot_payload()
        self.assertEqual(
            expected,
            current,
            "Parameter manifest snapshot is stale. Run: python tools/parameter_manifest_gate.py --write",
        )


if __name__ == "__main__":
    unittest.main()
