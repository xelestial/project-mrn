"""policy/decision/movement.py — choose_movement 결정 모듈."""
from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy, MovementDecision
    from game_state import GameState, PlayerState


def choose_movement(
    state: "GameState",
    player: "PlayerState",
    policy_ref: "HeuristicPolicy",
):
    from ai_policy import MovementDecision
    from game_enums import CellKind

    p = policy_ref
    best_score = -(10 ** 9)
    best = MovementDecision(False, ())
    board_len = len(state.board)
    survival_ctx = p._generic_survival_context(state, player, player.current_character)
    f_ctx = p._f_progress_context(state, player)

    token_profile = p._profile_from_mode() == "token_opt"
    v3_profile = p._profile_from_mode() == "v3_claude"
    placeable_tiles = set(p._placeable_own_tiles(state, player))

    def _move_bonus(pos: int) -> float:
        bonus = 0.0
        if token_profile and pos in placeable_tiles and player.hand_coins > 0:
            revisit_gap = (pos - player.position) % board_len
            bonus += 8.5 + 0.9 * state.tile_coins[pos] + (1.2 if revisit_gap <= 4 else 0.4)
        if token_profile and state.tile_owner[pos] == player.player_id:
            bonus += 2.2 + 0.25 * state.tile_coins[pos]
        if token_profile and state.board[pos] in {CellKind.F1, CellKind.F2}:
            bonus += max(0.0, 0.35 * float(f_ctx["land_f_value"]))
        # [v3_claude] 탐관오리 전략: 상대가 내 칸으로 오면 조각 2개당 1냥 수취
        # 탐관오리는 이동 방향이 아니라 '머물 위치'가 중요
        # → 상대 플레이어들이 자주 지나가는 칸(교통량 높은 칸)에 위치하는 게 유리
        # → 이동 결정: 상대 뒤쪽(상대가 지나쳐갈 위치)보다는 빈 타일 매입이 우선
        # (별도 이동 보너스 없음 - 탐관오리의 이동 우선순위는 일반 구매/F칸 논리를 따름)
        return bonus

    def _eval_move(pos: int, move_total: int, *, use_cards: bool = False, card_count: int = 0) -> float:
        predicted_cost = p._predict_tile_landing_cost(state, player, pos)
        cell = state.board[pos]
        # [burden_patch v3] 악성 타일 강화 회피:
        # 카드 사용 여부와 무관하게, 악성 타일 비용이 생존선을 침범하면 하드 블록
        if cell == CellKind.MALICIOUS and predicted_cost > 0.0:
            if not p._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.0):
                return -(10 ** 8)
        if use_cards and predicted_cost > 0.0 and not p._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.5 * card_count):
            return -(10 ** 8)
        projected_cash = p._project_end_turn_cash(state, player, immediate_cost=predicted_cost, crosses_start=(player.position + move_total >= len(state.board)))
        score = p._landing_score(state, player, pos)
        score += _move_bonus(pos)
        score += p._movement_survival_adjustment(state, player, pos, move_total, survival_ctx, projected_cash=projected_cash)
        score += p._f_move_adjustment(state, player, pos, move_total, survival_ctx, f_ctx, use_cards=use_cards, card_count=card_count)
        if use_cards and predicted_cost > 0.0 and not p._is_action_survivable(state, player, immediate_cost=predicted_cost, survival_ctx=survival_ctx, buffer=0.0):
            score -= 8.0
        return score

    base_scores = []
    for d1 in range(1, 7):
        for d2 in range(1, 7):
            move_total = d1 + d2
            pos = (player.position + move_total) % board_len
            base_scores.append(_eval_move(pos, move_total, use_cards=False, card_count=0))
    avg_no_cards = sum(base_scores) / len(base_scores)
    best_score = avg_no_cards

    # [burden_patch v3] 악성 타일 회피 우선: 카드 없이 가면 악성 타일이 불가피할 때
    # 주사위 카드로 악성 타일을 피할 수 있으면 평균 점수 비교 대신 우선 선택
    no_card_malicious_unavoidable = all(
        state.board[(player.position + d1 + d2) % board_len] == CellKind.MALICIOUS
        or not p._is_action_survivable(
            state, player,
            immediate_cost=p._predict_tile_landing_cost(state, player, (player.position + d1 + d2) % board_len),
            survival_ctx=survival_ctx, buffer=0.0,
        )
        for d1 in range(1, 7) for d2 in range(1, 7)
    )

    remaining = p._remaining_cards(player)
    for c in remaining:
        vals = []
        for d in range(1, 7):
            move_total = c + d
            pos = (player.position + move_total) % board_len
            vals.append(_eval_move(pos, move_total, use_cards=True, card_count=1))
        score = sum(vals) / len(vals)
        # 카드로 악성 타일을 일부 피할 수 있고, 카드 없인 불가피하면 보너스
        if no_card_malicious_unavoidable:
            safe_count = sum(
                1 for d in range(1, 7)
                if state.board[(player.position + c + d) % board_len] != CellKind.MALICIOUS
                and p._is_action_survivable(
                    state, player,
                    immediate_cost=p._predict_tile_landing_cost(state, player, (player.position + c + d) % board_len),
                    survival_ctx=survival_ctx, buffer=0.0,
                )
            )
            if safe_count > 0:
                score += 4.0 + 0.8 * safe_count  # 악성 회피 가능성에 강한 보너스
        if score > best_score:
            best_score = score
            best = MovementDecision(True, (c,))
    for a, b in combinations(remaining, 2):
        move_total = a + b
        pos = (player.position + move_total) % board_len
        score = _eval_move(pos, move_total, use_cards=True, card_count=2)
        if score > best_score:
            best_score = score
            best = MovementDecision(True, (a, b))
    return best
