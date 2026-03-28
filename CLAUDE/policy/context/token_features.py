"""policy/context/token_features — 코인 토큰 관련 순수 함수 모음.

state + player만으로 계산 가능한 토큰 피처.
재방문 확률 등 확률 계산은 TurnContextBuilder(policy_ref)에 위임.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import GameState, PlayerState


def placeable_own_tiles(state: "GameState", player: "PlayerState") -> list[int]:
    """코인을 추가 배치할 수 있는 자신의 타일 인덱스 목록."""
    max_coins = state.config.rules.token.max_coins_per_tile
    return [
        i for i in player.visited_owned_tile_indices
        if state.tile_owner[i] == player.player_id
        and state.tile_coins[i] < max_coins
    ]


def has_placeable_tile(state: "GameState", player: "PlayerState") -> bool:
    """배치 가능한 자신의 타일이 있는지 여부."""
    return bool(placeable_own_tiles(state, player))


def total_placed_coins(state: "GameState", player: "PlayerState") -> int:
    """자신의 모든 타일에 배치된 코인 총합."""
    return sum(
        state.tile_coins[i]
        for i in range(len(state.board))
        if state.tile_owner[i] == player.player_id
    )


def hand_coins_shortage(player: "PlayerState", threshold: int = 2) -> int:
    """hand_coins가 threshold에 미달하는 양 (0 이상)."""
    return max(0, threshold - player.hand_coins)
