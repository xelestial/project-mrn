"""policy/decision/lap_reward.py — choose_lap_reward 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy, LapRewardDecision
    from game_state import GameState, PlayerState


def choose_lap_reward(state: "GameState", player: "PlayerState", policy_ref: "HeuristicPolicy") -> "LapRewardDecision":
    from ai_policy import LapRewardDecision

    p = policy_ref
    mode = p._lap_mode_for_player(player.player_id)
    if mode == "cash_focus":
        return p._lap_reward_bundle(state, 1.0, 0.01, 0.01, preferred="cash")
    if mode == "shard_focus":
        return p._lap_reward_bundle(state, 0.01, 1.0, 0.01, preferred="shards")
    if mode == "coin_focus":
        return p._lap_reward_bundle(state, 0.01, 0.01, 1.0, preferred="coins")
    placeable = any(
        state.tile_owner[i] == player.player_id
        and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        for i in player.visited_owned_tile_indices
    )
    buy_value = p._expected_buy_value(state, player)
    cross_start = p._will_cross_start(state, player)
    land_f = p._will_land_on_f(state, player)
    survival_ctx = p._generic_survival_context(state, player, player.current_character)
    f_ctx = p._f_progress_context(state, player)
    # [burden_patch] survival_urgency >= 1.0 이 너무 늦은 트리거였음.
    # 짐 2장 이상이거나 latent_cleanup_cost 가 현금 50% 초과면 urgency 무관하게 현금 압박 상태로 본다.
    _scp_burdens = sum(1 for c in player.trick_hand if c.is_burden)
    _scp_latent = float(survival_ctx.get("latent_cleanup_cost", 0.0))
    survival_cash_pressure = (
        (
            survival_ctx["survival_urgency"] >= 1.0
            and (
                player.cash <= 4
                or survival_ctx["rent_pressure"] >= 1.2
                or survival_ctx["lethal_hit_prob"] > 0.0
                or survival_ctx["own_burden_cost"] > 0.0
                or survival_ctx["cleanup_pressure"] >= 2.0
            )
        )
        or (_scp_burdens >= 2)
        or (_scp_burdens >= 1 and _scp_latent >= player.cash * 0.5)
    )
    if mode.startswith("heuristic_v2_"):
        profile = p._profile_from_mode(mode)
        preferred_override: str | None = None
        current_char = player.current_character
        coin_score = (2.5 if placeable else -0.5) + (1.6 if current_char in {"객주", "사기꾼"} else 0.0) + 1.2 * cross_start
        if current_char == "중매꾼":
            coin_score += 0.9 + 0.35 * p._matchmaker_adjacent_value(state, player)
        elif current_char == "건설업자":
            coin_score += 1.00 + 0.55 * p._builder_free_purchase_value(state, player)
        shard_score = 0.8 + (1.9 if current_char in {"산적", "탐관오리", "아전"} else 0.0) + 0.35 * max(0, 6 - player.shards) + max(0.0, 0.7 * land_f * float(f_ctx["land_f_value"]))
        if current_char == "중매꾼" and player.shards < 2:
            shard_score += 0.75 + 0.20 * max(0, 2 - player.shards)
        if current_char == "박수":
            # 폴백 임계(5개) 미달: 조각 적극 모으기. 임계 달성 후: 현금/코인 전환
            if player.shards < 5:
                shard_score += 0.80 + 0.12 * (5 - player.shards)
            else:
                shard_score -= 0.30  # 임계 달성 후 조각 선호 억제 → 현금/코인으로
        if current_char == "만신":
            # 폴백 임계(7개) 미달: 적극 모으기. 임계 달성 후: 현금/코인 전환
            visible_enemy_burdens = sum(
                p._visible_burden_count(state.players[player.player_id], ep)
                for ep in state.players
                if ep.alive and ep.player_id != player.player_id
            )
            if player.shards < 7:
                base_shard = 0.70 + 0.10 * (7 - player.shards)
            else:
                base_shard = -0.20  # 임계 달성 후 억제
            shard_score += base_shard + 0.15 * min(2, visible_enemy_burdens)
        cash_score = 1.2 + 0.4 * max(0, 10 - player.cash)
        if survival_cash_pressure:
            cash_score += 1.35 + 0.95 * survival_ctx["survival_urgency"] + 0.25 * max(0.0, -survival_ctx["cash_after_reserve"])
            coin_score -= 0.55 * survival_ctx["survival_urgency"]
            shard_score -= 0.40 * survival_ctx["survival_urgency"]
            if placeable and survival_ctx["recovery_score"] >= 1.2:
                coin_score += 0.25
        # [burden_patch] 짐 보유 시 랩보상에서 현금 선택 압력 추가
        # latent_cleanup_cost 가 크거나 짐을 여러 장 들고 있으면 현금으로 유동성을 확보해야 한다.
        _lap_latent = float(survival_ctx.get("latent_cleanup_cost", 0.0))
        _lap_burdens = float(survival_ctx.get("own_burdens", 0.0))
        _lap_expected = float(survival_ctx.get("expected_cleanup_cost", 0.0))
        if _lap_burdens >= 1.0:
            # 짐 1장당 +0.70, latent_cleanup / expected_cleanup 가중치 반영
            cash_score += 0.70 * _lap_burdens + 0.40 * _lap_latent + 0.35 * _lap_expected
            coin_score -= 0.30 * _lap_burdens
            shard_score -= 0.20 * _lap_burdens
        if not bool(f_ctx["is_leader"]):
            cash_score += 0.45 + 0.30 * float(f_ctx["avoid_f_acceleration"])
            shard_score -= 0.35 + 0.20 * float(f_ctx["avoid_f_acceleration"])
        if current_char == "객주":
            shard_score += max(0.0, 0.9 * land_f * float(f_ctx["land_f_value"]))
            coin_score += 0.8 * cross_start
        if profile == "control":
            denial_snapshot = p._leader_denial_snapshot(state, player)
            emergency = float(denial_snapshot["emergency"])
            liquidity = p._liquidity_risk_metrics(state, player, player.current_character)
            rent_pressure, _ = p._rent_pressure_breakdown(state, player, player.current_character or "")
            burden_count = sum(1 for c in player.trick_hand if c.is_burden)
            burden_context = p._burden_context(state, player)
            cleanup_pressure = float(burden_context.get("cleanup_pressure", 0.0))
            low_cash = max(0.0, 7.0 - player.cash)
            finisher_window, _ = p._control_finisher_window(player)
            shard_score += 1.1 + 0.55 * emergency
            cash_score += 0.1
            if denial_snapshot.get("solo_leader"):
                shard_score += 0.45
            if denial_snapshot.get("near_end"):
                shard_score += 0.55
            if player.current_character in {"교리 연구관", "교리 감독관", "산적", "탐관오리", "아전", "어사", "사기꾼"}:
                shard_score += 0.4
            if placeable:
                coin_score += 0.45
            if finisher_window > 0.0 and placeable and liquidity["cash_after_reserve"] >= 0.5:
                coin_score += 1.85 + 0.55 * finisher_window
                cash_score += 0.25 * finisher_window
                preferred_override = "coins"
            if finisher_window > 0.0 and buy_value > 0.0 and liquidity["cash_after_reserve"] >= 0.0:
                cash_score += 0.35 + 0.15 * finisher_window
            if low_cash > 0.0:
                cash_score += 0.55 * low_cash
            if liquidity["cash_after_reserve"] <= 0.0:
                cash_score += 0.9 + 0.2 * max(0.0, -float(liquidity["cash_after_reserve"]))
            if rent_pressure >= 1.7:
                cash_score += 0.45 + 0.18 * rent_pressure
            if burden_count >= 1 and cleanup_pressure >= 2.2:
                cash_score += 0.5 + 0.18 * burden_count + 0.08 * max(0.0, cleanup_pressure - 2.2)
            if player.cash <= 3:
                cash_score += 2.0
            elif player.cash <= 5 and liquidity["cash_after_reserve"] <= -0.5 and emergency < 3.0:
                cash_score += 1.5
            elif player.cash <= 6 and rent_pressure >= 2.0 and emergency < 2.6:
                cash_score += 1.25
        elif profile == "growth":
            shard_score += 0.4
            coin_score += 0.8
        elif profile == "avoid_control":
            cash_score += 0.8
        elif profile == "aggressive":
            coin_score += 1.8
            cash_score -= 0.2
        elif profile == "token_opt":
            own_land = p._prob_land_on_placeable_own_tile(state, player)
            token_combo = p._token_teleport_combo_score(player)
            token_window = p._token_placement_window_metrics(state, player)
            coin_score += 1.8 + 2.1 * own_land + 0.9 * token_combo + 0.75 * token_window["window_score"]
            if token_window["placeable_count"] <= 0.0:
                coin_score -= 2.1
                cash_score += 0.55
            if token_window["nearest_distance"] <= 4.0:
                coin_score += 0.9
            if token_window["revisit_prob"] >= 0.28:
                coin_score += 0.8
            if player.hand_coins >= 3 and token_window["revisit_prob"] < 0.12:
                cash_score += 0.9
            shard_score += max(0.0, 0.20 * land_f * float(f_ctx["land_f_value"]))
            cash_score -= 0.2
        elif profile == "v3_claude":
            # [v3_claude v2] 랩보상 원칙:
            # 초반(랩 1회 이하): 코인 투자 가능 (타일 기반 구축)
            # 중반(랩 2회+): 현금 우선 전환
            # 조각: 인물별 임계까지만, 항상 산적/탐관오리/아전 보정 포함
            laps_done = getattr(state, 'rounds_completed', 0) // max(1, sum(1 for ep in state.players if ep.alive))
            char = current_char or ""

            # 조각 임계
            shard_threshold = 5 if char == "박수" else 7 if char == "만신" else 4
            gap = shard_threshold - player.shards
            if gap > 0:
                # 임계까지 부족한 만큼 강하게 선호
                # 특히 임계 바로 1개 아래(gap=1)일 때 강제에 가깝게
                urgency_bonus = 2.0 if gap == 1 else (0.8 + 0.12 * gap)
                shard_score += urgency_bonus
                if gap == 1 and char in {"박수", "만신"}:
                    # 조각 1개만 더 있으면 폴백 확정 → 현금/코인 억제
                    cash_score -= 0.8
                    coin_score -= 0.8
            elif char in {"산적", "탐관오리", "아전"}:
                shard_score += 0.5  # 조각 현금환전 인물은 계속 유지
            else:
                shard_score -= 0.3  # 임계 초과 억제

            # 코인: 초반 + 타일 있고 재방문 가능할 때만
            if laps_done <= 1 and placeable:
                token_window = p._token_placement_window_metrics(state, player)
                if token_window["revisit_prob"] >= 0.18:
                    coin_score += 1.0 + 0.6 * token_window["revisit_prob"]
                else:
                    coin_score -= 0.2
            elif placeable and player.hand_coins < 1:
                token_window = p._token_placement_window_metrics(state, player)
                if token_window["revisit_prob"] >= 0.25:
                    coin_score += 0.6
                else:
                    coin_score -= 0.4
            else:
                coin_score -= 0.5

            # 현금: 중후반 강화 + 생존 압박 시
            cash_score += 0.5 + 0.2 * max(0, laps_done - 1)
            if player.cash < 10:
                cash_score += 0.8
        cash_unit = cash_score / max(1.0, float(state.config.coins.lap_reward_cash))
        shard_unit = shard_score / max(1.0, float(state.config.shards.lap_reward_shards))
        coin_unit = coin_score / max(1.0, float(state.config.coins.lap_reward_coins))
        preferred = preferred_override or max([("cash", cash_score), ("shards", shard_score), ("coins", coin_score)], key=lambda x: x[1])[0]
        return p._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
    if mode == "balanced":
        if survival_cash_pressure:
            return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
        if placeable and player.hand_coins < 2:
            return p._lap_reward_bundle(state, 0.2, 0.1, 1.0, preferred="coins")
        if player.cash < 8:
            return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
        if player.current_character in {"산적", "탐관오리", "아전"} or player.shards < 4:
            return p._lap_reward_bundle(state, 0.2, 1.0, 0.1, preferred="shards")
        return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
    if survival_cash_pressure:
        return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
    if player.cash < 8:
        return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
    if player.current_character in {"산적", "탐관오리", "아전"}:
        return LapRewardDecision("shards")
    if placeable:
        return LapRewardDecision("coins")
    return p._lap_reward_bundle(state, 1.0, 0.2, 0.1, preferred="cash")
