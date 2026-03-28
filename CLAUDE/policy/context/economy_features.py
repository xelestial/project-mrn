"""policy/context/economy_features — 경제 지표 순수 함수 모음.

state + player만으로 계산 가능한 경제 관련 피처.
policy_ref가 필요한 복합 계산(rent_exposure 등)은 TurnContextBuilder에 위임.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import GameState, PlayerState


def own_cash(player: "PlayerState") -> float:
    """현재 보유 현금."""
    return float(player.cash)


def own_shards(player: "PlayerState") -> float:
    """현재 보유 조각 수."""
    return float(player.shards)


def own_hand_coins(player: "PlayerState") -> float:
    """현재 보유 코인 수."""
    return float(player.hand_coins)


def own_tiles_count(player: "PlayerState") -> int:
    """보유 타일 수."""
    return int(player.tiles_owned)


def own_burden_count(player: "PlayerState") -> int:
    """보유 짐 카드 수."""
    return sum(1 for c in player.trick_hand if c.is_burden)


def own_burden_cost_total(player: "PlayerState") -> float:
    """보유 짐 카드 총 청산 비용."""
    return float(sum(getattr(c, "burden_cost", 0) for c in player.trick_hand if c.is_burden))


def cash_shortage(player: "PlayerState", threshold: float = 8.0) -> float:
    """현금이 threshold에 미달하는 양 (0 이상)."""
    return max(0.0, threshold - float(player.cash))
