"""policy/context/danger_features — 위험 지표 순수 함수 모음.

state + player만으로 계산 가능한 위험 관련 피처.
두_턴_사망_확률 등 복합 계산은 TurnContextBuilder(policy_ref)에 위임.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import GameState, PlayerState


def burden_count(player: "PlayerState") -> int:
    """보유 짐 카드 수."""
    return sum(1 for c in player.trick_hand if c.is_burden)


def burden_cleanup_cost(player: "PlayerState") -> float:
    """짐 카드 총 청산 비용 (burden_cost 합산)."""
    return float(sum(getattr(c, "burden_cost", 0) for c in player.trick_hand if c.is_burden))


def has_active_burden(player: "PlayerState") -> bool:
    """짐 카드가 1장 이상 있는지 여부."""
    return any(c.is_burden for c in player.trick_hand)


def malicious_tile_count(state: "GameState") -> int:
    """보드 상 악성 타일 수."""
    from game_enums import CellKind
    return sum(1 for cell in state.board if cell == CellKind.MALICIOUS)


def alive_player_count(state: "GameState") -> int:
    """생존 플레이어 수."""
    return sum(1 for p in state.players if p.alive)
