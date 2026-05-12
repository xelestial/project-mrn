from __future__ import annotations

import unittest

from apps.server.src.services.engine_config_factory import EngineConfigFactory
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
        self.assertEqual(resolved["economy"]["starting_cash"], 20)
        self.assertEqual(resolved["resources"]["starting_shards"], 2)
        self.assertEqual(resolved["rules"]["start_reward"]["points_budget"], 20)
        self.assertEqual(resolved["rules"]["start_reward"]["cash_point_cost"], 2)
        self.assertEqual(resolved["rules"]["start_reward"]["shards_point_cost"], 3)
        self.assertEqual(resolved["rules"]["start_reward"]["coins_point_cost"], 3)
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
                "runtime": {
                    "policy_mode": "baseline",
                    "runner_kind": "module",
                    "ai_decision_delay_ms": 0,
                },
                "rules": {
                    "end": {
                        "f_threshold": 1,
                        "monopolies_to_trigger_end": 0,
                        "tiles_to_trigger_end": 2,
                        "alive_players_at_most": 1,
                    }
                },
                "labels": {"event_labels": {"player_move": "Move"}},
                "participants": {
                    "external_ai": {
                        "transport": "http",
                        "contract_version": "v1",
                        "expected_worker_id": "bot-worker-1",
                        "auth_token": "worker-secret",
                        "auth_header_name": "X-Worker-Auth",
                        "auth_scheme": "Token",
                        "endpoint": "http://bot-worker.local/decide",
                        "timeout_ms": 9000,
                        "retry_count": 2,
                        "backoff_ms": 100,
                        "fallback_mode": "local_ai",
                        "healthcheck_path": "/health",
                        "healthcheck_ttl_ms": 5000,
                        "healthcheck_policy": "required",
                        "require_ready": True,
                        "max_attempt_count": 4,
                        "required_capabilities": ["choice_id_response", "healthcheck"],
                        "required_request_types": ["movement", "purchase_tile"],
                        "required_policy_mode": "heuristic_v3_engine",
                        "required_worker_adapter": "reference_heuristic_v1",
                        "required_policy_class": "HeuristicPolicy",
                        "required_decision_style": "contract_heuristic",
                        "headers": {"Authorization": "Bearer token"},
                    }
                },
            }
        )
        self.assertEqual(resolved["runtime"]["seed"], 77)
        self.assertEqual(resolved["runtime"]["policy_mode"], "baseline")
        self.assertEqual(resolved["runtime"]["player_count"], 2)
        self.assertEqual(resolved["runtime"]["runner_kind"], "module")
        self.assertEqual(resolved["runtime"]["ai_decision_delay_ms"], 0)
        self.assertEqual(resolved["board"]["topology"], "line")
        self.assertEqual(resolved["seats"]["allowed"], [1, 2])
        self.assertEqual(resolved["economy"]["starting_cash"], 55)
        self.assertEqual(resolved["resources"]["starting_shards"], 7)
        self.assertEqual(resolved["rules"]["end"]["f_threshold"], 1.0)
        self.assertEqual(resolved["rules"]["end"]["tiles_to_trigger_end"], 2)
        self.assertEqual(resolved["dice"]["values"], [2, 4, 8])
        self.assertEqual(resolved["dice"]["max_cards_per_turn"], 1)
        self.assertEqual(resolved["participants"]["external_ai"]["transport"], "http")
        self.assertEqual(resolved["participants"]["external_ai"]["contract_version"], "v1")
        self.assertEqual(resolved["participants"]["external_ai"]["expected_worker_id"], "bot-worker-1")
        self.assertEqual(resolved["participants"]["external_ai"]["auth_token"], "worker-secret")
        self.assertEqual(resolved["participants"]["external_ai"]["auth_header_name"], "X-Worker-Auth")
        self.assertEqual(resolved["participants"]["external_ai"]["auth_scheme"], "Token")
        self.assertEqual(resolved["participants"]["external_ai"]["timeout_ms"], 9000)
        self.assertEqual(resolved["participants"]["external_ai"]["retry_count"], 2)
        self.assertEqual(resolved["participants"]["external_ai"]["backoff_ms"], 100)
        self.assertEqual(resolved["participants"]["external_ai"]["fallback_mode"], "local_ai")
        self.assertEqual(resolved["participants"]["external_ai"]["healthcheck_path"], "/health")
        self.assertEqual(resolved["participants"]["external_ai"]["healthcheck_ttl_ms"], 5000)
        self.assertEqual(resolved["participants"]["external_ai"]["healthcheck_policy"], "required")
        self.assertEqual(resolved["participants"]["external_ai"]["require_ready"], True)
        self.assertEqual(resolved["participants"]["external_ai"]["max_attempt_count"], 4)
        self.assertEqual(resolved["participants"]["external_ai"]["required_capabilities"], ["choice_id_response", "healthcheck"])
        self.assertEqual(resolved["participants"]["external_ai"]["required_request_types"], ["movement", "purchase_tile"])
        self.assertEqual(resolved["participants"]["external_ai"]["required_policy_mode"], "heuristic_v3_engine")
        self.assertEqual(resolved["participants"]["external_ai"]["required_worker_adapter"], "reference_heuristic_v1")
        self.assertEqual(resolved["participants"]["external_ai"]["required_policy_class"], "HeuristicPolicy")
        self.assertEqual(resolved["participants"]["external_ai"]["required_decision_style"], "contract_heuristic")
        self.assertIn("event_labels", resolved["labels"])

    def test_resolve_applies_external_ai_worker_profile_presets(self) -> None:
        resolved = self.resolver.resolve(
            {
                "seed": 42,
                "participants": {
                    "external_ai": {
                        "transport": "http",
                        "worker_profile": "priority_scored",
                    }
                },
            }
        )

        external_ai = resolved["participants"]["external_ai"]
        self.assertEqual(external_ai["worker_profile"], "priority_scored")
        self.assertEqual(external_ai["required_worker_adapter"], "priority_score_v1")
        self.assertEqual(external_ai["required_policy_class"], "PriorityScoredPolicy")
        self.assertEqual(external_ai["required_decision_style"], "priority_scored_contract")
        self.assertIn("priority_scored_choice", external_ai["required_capabilities"])
        self.assertIn("scored_choice_strategy_v1", external_ai["required_capabilities"])

    def test_resolve_accepts_explicit_end_rule_overrides(self) -> None:
        resolved = self.resolver.resolve(
            {
                "seed": 42,
                "rules": {
                    "end": {
                        "f_threshold": 1,
                        "monopolies_to_trigger_end": 0,
                        "tiles_to_trigger_end": 1,
                        "alive_players_at_most": 1,
                    }
                },
            }
        )

        self.assertEqual(
            resolved["rules"]["end"],
            {
                "f_threshold": 1.0,
                "monopolies_to_trigger_end": 0,
                "tiles_to_trigger_end": 1,
                "alive_players_at_most": 1,
                "max_rounds": None,
                "max_turns": None,
            },
        )

    def test_resolve_rejects_invalid_end_rule_overrides(self) -> None:
        invalid_configs = [
            {"rules": []},
            {"rules": {"end": []}},
            {"rules": {"end": {"f_threshold": 0}}},
            {"rules": {"end": {"monopolies_to_trigger_end": -1}}},
            {"rules": {"end": {"tiles_to_trigger_end": 0}}},
            {"rules": {"end": {"alive_players_at_most": 0}}},
            {"rules": {"end": {"max_rounds": 0}}},
            {"rules": {"end": {"max_turns": 0}}},
            {"runtime": []},
            {"runtime": {"seed": False}},
            {"runtime": {"policy_mode": 123}},
            {"runtime": {"runner_kind": ""}},
            {"runtime": {"ai_decision_delay_ms": True}},
            {"runtime": {"ai_decision_delay_ms": -1}},
            {"runtime": {"max_rounds": False}},
            {"runtime": {"max_turns": False}},
        ]
        for config in invalid_configs:
            with self.subTest(config=config):
                with self.assertRaises(ParameterValidationError):
                    self.resolver.resolve(config)

    def test_engine_config_factory_applies_explicit_end_rule_overrides(self) -> None:
        resolved = self.resolver.resolve(
            {
                "seed": 42,
                "end": {
                    "f_threshold": 2,
                    "monopolies_to_trigger_end": 0,
                    "tiles_to_trigger_end": 1,
                    "alive_players_at_most": 1,
                    "max_rounds": 2,
                    "max_turns": 8,
                },
            }
        )

        runtime_config = EngineConfigFactory().create(resolved)

        self.assertEqual(runtime_config.rules.end.f_threshold, 2.0)
        self.assertEqual(runtime_config.rules.end.monopolies_to_trigger_end, 0)
        self.assertEqual(runtime_config.rules.end.tiles_to_trigger_end, 1)
        self.assertEqual(runtime_config.rules.end.alive_players_at_most, 1)
        self.assertEqual(runtime_config.rules.end.max_rounds, 2)
        self.assertEqual(runtime_config.rules.end.max_turns, 8)
        self.assertEqual(runtime_config.board.f_end_value, 2.0)
        self.assertEqual(runtime_config.end.monopolies_to_trigger_end, 0)
        self.assertEqual(runtime_config.end.higher_tiles_to_trigger_end, 1)
        self.assertEqual(runtime_config.end.end_when_alive_players_at_most, 1)
        self.assertEqual(runtime_config.end.max_rounds, 2)
        self.assertEqual(runtime_config.end.max_turns, 8)

    def test_engine_config_factory_applies_runtime_max_rounds_alias(self) -> None:
        resolved = self.resolver.resolve({"seed": 42, "runtime": {"max_rounds": 3}})

        runtime_config = EngineConfigFactory().create(resolved)

        self.assertEqual(runtime_config.rules.end.max_rounds, 3)
        self.assertEqual(runtime_config.end.max_rounds, 3)

    def test_engine_config_factory_applies_runtime_max_turns_alias(self) -> None:
        resolved = self.resolver.resolve({"seed": 42, "runtime": {"max_turns": 7}})

        runtime_config = EngineConfigFactory().create(resolved)

        self.assertEqual(runtime_config.rules.end.max_turns, 7)
        self.assertEqual(runtime_config.end.max_turns, 7)

    def test_resolve_rejects_invalid_external_ai_transport(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"transport": "grpc"}}})

    def test_resolve_rejects_invalid_external_ai_worker_profile(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"worker_profile": "unknown_profile"}}})

    def test_resolve_rejects_invalid_external_ai_required_capabilities(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_capabilities": "choice_id_response"}}})

    def test_resolve_rejects_invalid_external_ai_required_request_types(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_request_types": "movement"}}})

    def test_resolve_rejects_invalid_external_ai_healthcheck_policy(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"healthcheck_policy": "sometimes"}}})

    def test_resolve_rejects_invalid_external_ai_readiness_and_attempt_limits(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"require_ready": "yes"}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"max_attempt_count": 0}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_policy_mode": "  "}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_worker_adapter": "   "}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_policy_class": "   "}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"required_decision_style": ""}}})

    def test_resolve_rejects_blank_external_ai_identity_fields(self) -> None:
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"expected_worker_id": "  "}}})
        with self.assertRaises(ParameterValidationError):
            self.resolver.resolve({"participants": {"external_ai": {"auth_token": "  "}}})

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
