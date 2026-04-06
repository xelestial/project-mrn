from __future__ import annotations

import unittest

from apps.server.src.services.parameter_service import (
    GameParameterResolver,
    ParameterValidationError,
    PublicManifestBuilder,
    RootSourceRegistry,
)


class ParameterServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = RootSourceRegistry()
        self.resolver = GameParameterResolver(registry=self.registry)
        self.manifest_builder = PublicManifestBuilder(registry=self.registry)

    def test_resolve_defaults_has_core_sections(self) -> None:
        resolved = self.resolver.resolve({"seed": 42})
        self.assertIn("seats", resolved)
        self.assertIn("participants", resolved)
        self.assertIn("board", resolved)
        self.assertIn("dice", resolved)
        self.assertIn("economy", resolved)
        self.assertIn("resources", resolved)
        self.assertGreaterEqual(resolved["board"]["tile_count"], 1)

    def test_resolve_rejects_invalid_dice_values(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"dice_values": []})

    def test_manifest_contains_hash_and_fingerprints(self) -> None:
        manifest = self.manifest_builder.build_public_manifest(self.resolver.resolve({"seed": 1}))
        self.assertIn("manifest_hash", manifest)
        self.assertIn("source_fingerprints", manifest)
        self.assertIsInstance(manifest["source_fingerprints"], dict)
        self.assertTrue(manifest["source_fingerprints"])
        self.assertNotIn("missing", manifest["source_fingerprints"].values())

    def test_manifest_hash_changes_when_parameters_change(self) -> None:
        default_manifest = self.manifest_builder.build_public_manifest(self.resolver.resolve({"seed": 1}))
        changed_manifest = self.manifest_builder.build_public_manifest(
            self.resolver.resolve({"seed": 1, "starting_shards": 9})
        )
        self.assertNotEqual(default_manifest["manifest_hash"], changed_manifest["manifest_hash"])

    def test_resolve_accepts_board_topology_override(self) -> None:
        resolved = self.resolver.resolve({"seed": 1, "board_topology": "line"})
        self.assertEqual(resolved["board"]["topology"], "line")

    def test_resolve_rejects_invalid_board_topology(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"board_topology": "hex"})

    def test_resolve_accepts_extended_parameter_matrix(self) -> None:
        resolved = self.resolver.resolve(
            {
                "seed": 77,
                "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
                "board_topology": "line",
                "starting_cash": 55,
                "starting_shards": 7,
                "dice_values": [2, 4, 8],
                "dice_max_cards_per_turn": 1,
                "labels": {"event_labels": {"player_move": "Move"}},
                "participants": {
                    "external_ai": {
                        "transport": "http",
                        "contract_version": "v1",
                        "endpoint": "http://bot-worker.local/decide",
                        "timeout_ms": 9000,
                        "retry_count": 2,
                        "backoff_ms": 100,
                        "fallback_mode": "local_ai",
                        "healthcheck_path": "/health",
                        "healthcheck_ttl_ms": 5000,
                        "required_capabilities": ["choice_id_response", "healthcheck"],
                        "headers": {"Authorization": "Bearer token"},
                    }
                },
            }
        )
        self.assertEqual(resolved["runtime"]["player_count"], 2)
        self.assertEqual(resolved["board"]["topology"], "line")
        self.assertEqual(resolved["seats"]["allowed"], [1, 2])
        self.assertEqual(resolved["economy"]["starting_cash"], 55)
        self.assertEqual(resolved["resources"]["starting_shards"], 7)
        self.assertEqual(resolved["dice"]["values"], [2, 4, 8])
        self.assertEqual(resolved["dice"]["max_cards_per_turn"], 1)
        self.assertEqual(resolved["participants"]["external_ai"]["transport"], "http")
        self.assertEqual(resolved["participants"]["external_ai"]["contract_version"], "v1")
        self.assertEqual(resolved["participants"]["external_ai"]["timeout_ms"], 9000)
        self.assertEqual(resolved["participants"]["external_ai"]["retry_count"], 2)
        self.assertEqual(resolved["participants"]["external_ai"]["backoff_ms"], 100)
        self.assertEqual(resolved["participants"]["external_ai"]["fallback_mode"], "local_ai")
        self.assertEqual(resolved["participants"]["external_ai"]["healthcheck_path"], "/health")
        self.assertEqual(resolved["participants"]["external_ai"]["healthcheck_ttl_ms"], 5000)
        self.assertEqual(resolved["participants"]["external_ai"]["required_capabilities"], ["choice_id_response", "healthcheck"])
        self.assertIn("event_labels", resolved["labels"])

    def test_resolve_rejects_invalid_external_ai_transport(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"transport": "grpc"}}})

    def test_resolve_rejects_invalid_external_ai_required_capabilities(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_capabilities": "choice_id_response"}}})

    def test_manifest_hash_changes_for_dice_and_economy_updates(self) -> None:
        base = self.manifest_builder.build_public_manifest(
            self.resolver.resolve({"seed": 7, "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]}})
        )
        changed = self.manifest_builder.build_public_manifest(
            self.resolver.resolve(
                {
                    "seed": 7,
                    "seat_limits": {"min": 1, "max": 2, "allowed": [1, 2]},
                    "starting_cash": 77,
                    "dice_values": [1, 3, 5],
                    "dice_max_cards_per_turn": 1,
                }
            )
        )
        self.assertNotEqual(base["manifest_hash"], changed["manifest_hash"])


if __name__ == "__main__":
    unittest.main()
