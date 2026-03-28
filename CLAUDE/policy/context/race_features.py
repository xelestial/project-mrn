"""policy/context/race_features — 레이스(F 타일) 관련 순수 함수 모음.

state + player만으로 계산 가능한 레이스 피처.
f_progress 복합 계산은 TurnContextBuilder(policy_ref)에 위임.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state import GameState, PlayerState


def current_f_value(state: "GameState") -> float:
    """현재 F 타일 누적값."""
    return float(state.f_value)


def is_f_leader(state: "GameState", player: "PlayerState") -> bool:
    """이 플레이어가 F 리더(최고 F 포인트 보유자)인지 여부."""
    if not state.players:
        return False
    max_f = max((p.f_points for p in state.players if p.alive), default=0)
    return player.alive and player.f_points >= max_f and max_f > 0


def alive_players_sorted_by_f(state: "GameState") -> list:
    """생존 플레이어를 F 포인트 내림차순으로 정렬."""
    return sorted(
        (p for p in state.players if p.alive),
        key=lambda p: p.f_points,
        reverse=True,
    )


def f_leader_gap(state: "GameState", player: "PlayerState") -> float:
    """리더와 이 플레이어의 F 포인트 차이 (음수면 뒤처짐)."""
    alive = [p for p in state.players if p.alive]
    if not alive:
        return 0.0
    max_f = max(p.f_points for p in alive)
    return float(player.f_points - max_f)


def rounds_completed(state: "GameState") -> int:
    """완료된 라운드 수."""
    return int(getattr(state, "rounds_completed", 0))
