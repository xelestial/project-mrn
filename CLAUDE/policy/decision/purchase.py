"""policy/decision/purchase.py — choose_purchase_tile 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState
    from game_enums import CellKind


def choose_purchase_tile(
    state: "GameState",
    player: "PlayerState",
    pos: int,
    cell: "CellKind",
    cost: int,
    policy_ref: "HeuristicPolicy",
    *,
    source: str = "landing",
) -> bool:
    p = policy_ref
    if cost <= 0 or p._is_random_mode():
        return True
    liquidity = p._liquidity_risk_metrics(state, player, player.current_character)
    survival_ctx = p._generic_survival_context(state, player, player.current_character)
    remaining_cash = player.cash - cost
    reserve = max(float(liquidity["reserve"]), float(survival_ctx["reserve"]))
    if not p._is_action_survivable(state, player, immediate_cost=float(cost), survival_ctx=survival_ctx, reserve_floor=reserve, buffer=0.5):
        p._set_debug("purchase_decision", player.player_id, {
            "source": source,
            "pos": pos,
            "cell": cell.name,
            "cost": cost,
            "decision": False,
            "reason": "global_action_survival_guard",
            "reserve": round(float(reserve), 3),
            "cash": player.cash,
        })
        return False
    complete_monopoly = p._would_complete_monopoly_with_purchase(state, player, pos)
    blocks_enemy = p._would_block_enemy_monopoly_with_purchase(state, player, pos)
    immediate_win = False
    if state.config.rules.end.tiles_to_trigger_end and player.tiles_owned + 1 >= state.config.rules.end.tiles_to_trigger_end:
        immediate_win = True
    if state.config.rules.end.monopolies_to_trigger_end and complete_monopoly:
        immediate_win = True
    if immediate_win:
        decision = True
    else:
        from game_enums import CellKind as _CellKind
        benefit = 0.8
        if cell == _CellKind.T3:
            benefit += 1.4
        elif cell == _CellKind.T2:
            benefit += 0.8
        if complete_monopoly:
            benefit += 2.4
        if blocks_enemy:
            benefit += 3.2
        elif state.block_ids[pos] >= 0:
            owned_in_block = sum(1 for i, bid in enumerate(state.block_ids) if bid == state.block_ids[pos] and state.tile_owner[i] == player.player_id)
            benefit += 0.45 * owned_in_block
        profile = p._profile_from_mode()
        if profile in {"growth", "aggressive"}:
            benefit += 0.35
        if profile == "token_opt" and state.tile_owner[pos] is None:
            benefit += 0.25
        # [burden_patch] aggressive/token_opt/growth는 기본 survival 가중치가 낮아
        # 짐 보유 중에도 구매를 강행하는 경향이 있다.
        # 짐 보유 시 benefit을 프로파일별로 추가 감산해 구매 억제를 보완한다.
        own_burden_count_purchase = sum(1 for c in player.trick_hand if c.is_burden)
        if own_burden_count_purchase >= 1:
            burden_benefit_penalty = {
                "aggressive": 0.55,
                "token_opt":  0.35,
                "growth":     0.30,
                "balanced":   0.10,
                "control":    0.05,
                "avoid_control": 0.0,
                "v3_claude":  0.45,  # 짐 보유 중 구매 강하게 억제 (생존 우선)
            }.get(profile, 0.10)
            benefit -= burden_benefit_penalty * own_burden_count_purchase
        money_distress = float(survival_ctx.get("money_distress", 0.0))
        reserve_floor = reserve + 1.25 * float(survival_ctx.get("two_turn_lethal_prob", 0.0)) + 0.65 * money_distress
        # [burden_patch] 짐 보유 중 구매 억제 강화: latent/expected 가중치를 0.28/0.22 → 0.65/0.50 으로 상향
        # 짐을 들고 있는 상태에서 구매로 현금을 소진하면 청산 시 파산 위험이 크게 높아진다.
        latent_cleanup = float(survival_ctx.get("latent_cleanup_cost", 0.0))
        expected_cleanup = float(survival_ctx.get("expected_cleanup_cost", 0.0))
        # [v3_claude] 짐 없을 때 reserve_floor 경감 (구매 억제 과잉 해소)
        #             짐 있을 때 reserve_floor 강화 (파산 방지)
        if profile == "v3_claude":
            if own_burden_count_purchase == 0:
                # 짐 없으면 latent/expected 반영 비율을 낮춰 구매 문턱 낮춤
                reserve_floor += 0.30 * latent_cleanup
                reserve_floor += 0.20 * expected_cleanup
            else:
                # 짐 보유 중엔 기존보다 더 강하게 reserve 확보
                reserve_floor += 0.85 * latent_cleanup
                reserve_floor += 0.70 * expected_cleanup
        else:
            reserve_floor += 0.65 * latent_cleanup
            reserve_floor += 0.50 * expected_cleanup
        if float(survival_ctx.get("public_cleanup_active", 0.0)) > 0.0:
            reserve_floor += 0.65 * float(survival_ctx.get("active_cleanup_cost", 0.0))
        if float(survival_ctx.get("needs_income", 0.0)) > 0.0:
            reserve_floor += 1.0
        shortfall = max(0.0, reserve_floor - remaining_cash)
        danger_cash = remaining_cash <= max(5.0, 0.60 * reserve_floor)
        own_burdens = float(survival_ctx.get("own_burdens", 0.0))
        cleanup_lock = (
            float(survival_ctx.get("public_cleanup_active", 0.0)) > 0.0
            and remaining_cash < float(survival_ctx.get("active_cleanup_cost", 0.0))
            and not blocks_enemy and not complete_monopoly
        ) or (
            float(survival_ctx.get("latent_cleanup_cost", 0.0)) >= max(8.0, player.cash * 0.8)
            and remaining_cash < reserve_floor
            and not blocks_enemy and not complete_monopoly
        ) or (
            # [burden_patch] 짐 2장 이상 보유 중 현금이 빠듯하면 구매 차단
            own_burdens >= 2.0
            and float(survival_ctx.get("expected_cleanup_cost", 0.0)) >= player.cash * 0.45
            and remaining_cash < reserve_floor
            and not blocks_enemy and not complete_monopoly
        )
        # [v3_claude + 시스템 이해] 박수 + 조각 5개 이상 + 짐 있으면
        # 폴백이 확정되어 짐 파산 위험이 없으므로 cleanup_lock 해제
        if profile == "v3_claude" and cleanup_lock and own_burden_count_purchase >= 1:
            if player.current_character == "박수" and player.shards >= 5:
                cleanup_lock = False  # 폴백으로 짐 해소 확정 → 구매 허용
        decision = not (
            shortfall > benefit
            or (danger_cash and shortfall > 0.25)
            or (money_distress >= 1.1 and not blocks_enemy and not complete_monopoly and remaining_cash < reserve_floor + 1.0)
            or cleanup_lock
        )
    p._set_debug("purchase_decision", player.player_id, {
        "source": source,
        "pos": pos,
        "cell": cell.name,
        "cost": cost,
        "cash_before": player.cash,
        "cash_after": remaining_cash,
        "reserve": round(reserve, 3),
        "money_distress": round(float(survival_ctx.get("money_distress", 0.0)), 3),
        "two_turn_lethal_prob": round(float(survival_ctx.get("two_turn_lethal_prob", 0.0)), 3),
        "latent_cleanup_cost": round(float(survival_ctx.get("latent_cleanup_cost", 0.0)), 3),
        "cleanup_cash_gap": round(float(survival_ctx.get("cleanup_cash_gap", 0.0)), 3),
        "expected_loss": round(liquidity["expected_loss"], 3),
        "worst_loss": round(liquidity["worst_loss"], 3),
        "blocks_enemy_monopoly": blocks_enemy,
        "decision": decision,
    })
    return decision
