from __future__ import annotations

from policy.asset.spec import ArenaPolicyAsset, DEFAULT_ARENA_CHARACTER_LINEUP, HeuristicPolicyAsset


class PolicyFactory:
    @staticmethod
    def normalize_heuristic_asset(asset: HeuristicPolicyAsset | None = None) -> HeuristicPolicyAsset:
        from ai_policy import HeuristicPolicy

        source = asset or HeuristicPolicyAsset()
        character_policy_mode = source.character_policy_mode
        lap_policy_mode = source.lap_policy_mode

        if character_policy_mode not in HeuristicPolicy.VALID_CHARACTER_POLICIES:
            raise ValueError(f"Unsupported character_policy_mode: {character_policy_mode}")
        if lap_policy_mode not in HeuristicPolicy.VALID_LAP_POLICIES:
            raise ValueError(f"Unsupported lap_policy_mode: {lap_policy_mode}")

        normalized_lap_modes: dict[int, str] = {}
        for pid, mode in dict(source.player_lap_policy_modes or {}).items():
            if mode not in HeuristicPolicy.VALID_LAP_POLICIES:
                raise ValueError(f"Unsupported lap policy for player {pid}: {mode}")
            normalized_lap_modes[int(pid)] = HeuristicPolicy.canonical_lap_policy_mode(mode)

        return HeuristicPolicyAsset(
            character_policy_mode=HeuristicPolicy.canonical_character_policy_mode(character_policy_mode),
            lap_policy_mode=HeuristicPolicy.canonical_lap_policy_mode(lap_policy_mode),
            player_lap_policy_modes=normalized_lap_modes,
        )

    @staticmethod
    def normalize_arena_asset(asset: ArenaPolicyAsset | None = None) -> ArenaPolicyAsset:
        from ai_policy import HeuristicPolicy

        source = asset or ArenaPolicyAsset()
        src_modes = dict(source.player_character_policy_modes or {})
        if not src_modes:
            src_modes = {i + 1: mode for i, mode in enumerate(DEFAULT_ARENA_CHARACTER_LINEUP)}

        player_character_policy_modes: dict[int, str] = {}
        for pid, mode in src_modes.items():
            if mode not in HeuristicPolicy.VALID_CHARACTER_POLICIES or mode == "arena":
                raise ValueError(f"Unsupported arena character policy for player {pid}: {mode}")
            player_character_policy_modes[int(pid)] = HeuristicPolicy.canonical_character_policy_mode(mode)

        player_lap_policy_modes: dict[int, str] = {}
        for pid, mode in dict(source.player_lap_policy_modes or {}).items():
            if mode not in HeuristicPolicy.VALID_LAP_POLICIES:
                raise ValueError(f"Unsupported arena lap policy for player {pid}: {mode}")
            player_lap_policy_modes[int(pid)] = HeuristicPolicy.canonical_lap_policy_mode(mode)

        for pid in range(1, 5):
            char_mode = player_character_policy_modes.get(
                pid,
                DEFAULT_ARENA_CHARACTER_LINEUP[(pid - 1) % len(DEFAULT_ARENA_CHARACTER_LINEUP)],
            )
            player_character_policy_modes.setdefault(pid, char_mode)
            player_lap_policy_modes.setdefault(
                pid,
                char_mode if char_mode in HeuristicPolicy.VALID_LAP_POLICIES else "heuristic_v1",
            )

        return ArenaPolicyAsset(
            player_character_policy_modes=player_character_policy_modes,
            player_lap_policy_modes=player_lap_policy_modes,
        )

    @staticmethod
    def create_heuristic_policy(asset: HeuristicPolicyAsset, *, rng=None):
        from ai_policy import HeuristicPolicy

        normalized_asset = PolicyFactory.normalize_heuristic_asset(asset)
        return HeuristicPolicy(
            character_policy_mode=normalized_asset.character_policy_mode,
            lap_policy_mode=normalized_asset.lap_policy_mode,
            rng=rng,
            player_lap_policy_modes=dict(normalized_asset.player_lap_policy_modes),
        )

    @staticmethod
    def create_heuristic_policy_from_modes(
        *,
        character_policy_mode: str,
        lap_policy_mode: str,
        player_lap_policy_modes: dict[int, str] | None = None,
        rng=None,
    ):
        return PolicyFactory.create_heuristic_policy(
            HeuristicPolicyAsset(
                character_policy_mode=character_policy_mode,
                lap_policy_mode=lap_policy_mode,
                player_lap_policy_modes=dict(player_lap_policy_modes or {}),
            ),
            rng=rng,
        )

    @staticmethod
    def create_runtime_policy(
        *,
        policy_mode: str,
        lap_policy_mode: str = "heuristic_v1",
        player_lap_policy_modes: dict[int, str] | None = None,
        player_character_policy_modes: dict[int, str] | None = None,
        rng=None,
    ):
        if policy_mode == "arena":
            return PolicyFactory.create_arena_policy(
                ArenaPolicyAsset(
                    player_character_policy_modes=dict(player_character_policy_modes or {}),
                    player_lap_policy_modes=dict(player_lap_policy_modes or {}),
                ),
                rng=rng,
            )
        return PolicyFactory.create_heuristic_policy_from_modes(
            character_policy_mode=policy_mode,
            lap_policy_mode=lap_policy_mode,
            player_lap_policy_modes=player_lap_policy_modes,
            rng=rng,
        )

    @staticmethod
    def create_arena_policy(asset: ArenaPolicyAsset, *, rng=None):
        from ai_policy import ArenaPolicy

        normalized_asset = PolicyFactory.normalize_arena_asset(asset)
        return ArenaPolicy(
            player_character_policy_modes=dict(normalized_asset.player_character_policy_modes),
            player_lap_policy_modes=dict(normalized_asset.player_lap_policy_modes),
            rng=rng,
        )
