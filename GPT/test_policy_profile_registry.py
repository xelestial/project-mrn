from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)

from ai_policy import ArenaPolicy, HeuristicPolicy
from policy.profile.presets import DEFAULT_PROFILE_REGISTRY


def test_profile_registry_resolves_stable_keys_and_legacy_modes() -> None:
    assert DEFAULT_PROFILE_REGISTRY.resolve_profile_key("heuristic_v1") == "balanced"
    assert DEFAULT_PROFILE_REGISTRY.resolve_profile_key("control") == "control"
    assert DEFAULT_PROFILE_REGISTRY.resolve_profile_key("heuristic_v2_control") == "control"
    assert DEFAULT_PROFILE_REGISTRY.resolve_profile_key("heuristic_v3_gpt") == "v3_gpt"
    assert DEFAULT_PROFILE_REGISTRY.canonicalize_character_mode("control") == "heuristic_v2_control"
    assert DEFAULT_PROFILE_REGISTRY.canonicalize_lap_mode("v3_gpt") == "heuristic_v3_gpt"


def test_heuristic_policy_canonicalizes_profile_alias_inputs() -> None:
    policy = HeuristicPolicy(character_policy_mode="control", lap_policy_mode="v3_gpt", player_lap_policy_modes={1: "token_opt"})

    assert policy.character_policy_mode == "heuristic_v2_control"
    assert policy.lap_policy_mode == "heuristic_v3_gpt"
    assert policy.player_lap_policy_modes[1] == "heuristic_v2_token_opt"
    assert policy._profile_from_mode() == "control"
    assert policy._profile_from_mode(policy.lap_policy_mode) == "v3_gpt"


def test_arena_policy_normalizes_per_player_profile_modes() -> None:
    arena = ArenaPolicy(
        player_character_policy_modes={1: "control", 2: "heuristic_v3_gpt"},
        player_lap_policy_modes={1: "token_opt", 2: "v3_gpt"},
    )

    assert arena.player_character_policy_modes[1] == "heuristic_v2_control"
    assert arena.player_character_policy_modes[2] == "heuristic_v3_gpt"
    assert arena.player_lap_policy_modes[1] == "heuristic_v2_token_opt"
    assert arena.player_lap_policy_modes[2] == "heuristic_v3_gpt"
