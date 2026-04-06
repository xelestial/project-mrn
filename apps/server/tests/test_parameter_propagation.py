from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.server.src.services.parameter_service import (
    GameParameterResolver,
    PublicManifestBuilder,
    RootSourceRegistry,
)
from apps.server.src.services.session_service import SessionService


class _TempRootSourceRegistry(RootSourceRegistry):
    def __init__(self, temp_root: Path) -> None:
        super().__init__(root_dir=temp_root)
        self._temp_root = temp_root

    def list_sources(self) -> list[tuple[str, Path]]:
        return [
            ("ruleset", self._temp_root / "ruleset.txt"),
            ("board_layout", self._temp_root / "board_layout.txt"),
        ]


class ParameterPropagationTests(unittest.TestCase):
    def test_manifest_hash_changes_when_external_participant_parameters_change(self) -> None:
        resolver = GameParameterResolver()
        builder = PublicManifestBuilder()

        before = builder.build_public_manifest(
            resolver.resolve(
                {
                    "seed": 42,
                    "participants": {
                        "external_ai": {
                            "transport": "http",
                            "healthcheck_policy": "auto",
                        }
                    },
                }
            )
        )
        after = builder.build_public_manifest(
            resolver.resolve(
                {
                    "seed": 42,
                    "participants": {
                        "external_ai": {
                            "transport": "http",
                            "healthcheck_policy": "required",
                        }
                    },
                }
            )
        )

        self.assertNotEqual(before["manifest_hash"], after["manifest_hash"])
        self.assertEqual(before["participants"]["external_ai"]["healthcheck_policy"], "auto")
        self.assertEqual(after["participants"]["external_ai"]["healthcheck_policy"], "required")

    def test_manifest_hash_changes_when_root_source_file_changes(self) -> None:
        resolver = GameParameterResolver()
        resolved = resolver.resolve({"seed": 42})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ruleset.txt").write_text("ruleset_v1", encoding="utf-8")
            (root / "board_layout.txt").write_text("board_layout_v1", encoding="utf-8")

            builder = PublicManifestBuilder(registry=_TempRootSourceRegistry(root))
            before = builder.build_public_manifest(resolved)
            (root / "ruleset.txt").write_text("ruleset_v2", encoding="utf-8")
            after = builder.build_public_manifest(resolved)

        self.assertNotEqual(
            before["source_fingerprints"]["ruleset"],
            after["source_fingerprints"]["ruleset"],
        )
        self.assertNotEqual(before["manifest_hash"], after["manifest_hash"])

    def test_session_bootstrap_manifest_reflects_root_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ruleset.txt").write_text("ruleset_a", encoding="utf-8")
            (root / "board_layout.txt").write_text("board_a", encoding="utf-8")
            registry = _TempRootSourceRegistry(root)
            session_service = SessionService(
                parameter_resolver=GameParameterResolver(),
                manifest_builder=PublicManifestBuilder(registry=registry),
            )
            seats = [
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ]

            first = session_service.create_session(seats=seats, config={"seed": 42})
            first_hash = first.parameter_manifest["manifest_hash"]
            first_ruleset_fp = first.parameter_manifest["source_fingerprints"]["ruleset"]

            (root / "ruleset.txt").write_text("ruleset_b", encoding="utf-8")

            second = session_service.create_session(seats=seats, config={"seed": 42})
            second_hash = second.parameter_manifest["manifest_hash"]
            second_ruleset_fp = second.parameter_manifest["source_fingerprints"]["ruleset"]

        self.assertNotEqual(first_ruleset_fp, second_ruleset_fp)
        self.assertNotEqual(first_hash, second_hash)


if __name__ == "__main__":
    unittest.main()
