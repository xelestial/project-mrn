from __future__ import annotations

from typing import Any

from characters import CARD_TO_NAMES, CHARACTERS
from config import CellKind
from policy.decision.support_choices import count_burden_cards
from policy.evaluator.character_scoring import (
    V1CharacterStructuralInputs,
    V2EmergencyRiskInputs,
    V2ExpansionInputs,
    V2PostRiskInputs,
    V2ProfileInputs,
    V2RentTailInputs,
    V2RouteInputs,
    V2TailThreatInputs,
    V2TacticalInputs,
    V2UhsaTailInputs,
    V3CharacterInputs,
    evaluate_v1_character_structural_rules,
    evaluate_v2_emergency_risk_rules,
    evaluate_v2_expansion_rules,
    evaluate_v2_post_risk_rules,
    evaluate_v2_profile_rules,
    evaluate_v2_rent_tail_rules,
    evaluate_v2_route_rules,
    evaluate_v2_tail_threat_rules,
    evaluate_v2_tactical_rules,
    evaluate_v2_uhsa_tail_rules,
    evaluate_v3_character_rules,
)
from policy.character_traits import is_assassin, is_bandit, is_swindler, is_tamgwanori


def score_character_v1(policy: Any, state: Any, player: Any, character_name: str) -> tuple[float, list[str]]:
    score = policy.character_values.get(character_name, 0.0)
    reasons: list[str] = [f"base={score:.1f}"]

    legal_mark_targets = policy._allowed_mark_targets(state, player)
    burden_context = policy._burden_context(state, player, legal_targets=legal_mark_targets)
    monopoly = policy._monopoly_block_metrics(state, player)
    scammer = policy._scammer_takeover_metrics(state, player)
    stack_ctx = policy._enemy_stack_metrics(state, player)
    lap_ctx = policy._lap_engine_context(state, player)

    board_len = len(state.board)
    near_unowned = 0
    for step in range(2, 8):
        pos = (player.position + step) % board_len
        if state.board[pos] in (CellKind.T2, CellKind.T3) and state.tile_owner[pos] is None:
            near_unowned += 1

    removed_small, payout_small = policy._failed_mark_fallback_metrics(player, 6)
    removed_large, payout_large = policy._failed_mark_fallback_metrics(player, 8)
    structural_delta, structural_reasons = evaluate_v1_character_structural_rules(
        character_name,
        V1CharacterStructuralInputs(
            low_cash=player.cash < 8,
            very_low_cash=player.cash < 5,
            shards=player.shards,
            near_unowned=near_unowned,
            enemy_tiles=sum(p.tiles_owned for p in policy._alive_enemies(state, player)),
            own_near_complete=float(monopoly["own_near_complete"]),
            own_claimable_blocks=float(monopoly["own_claimable_blocks"]),
            enemy_near_complete=float(monopoly["enemy_near_complete"]),
            contested_blocks=float(monopoly["contested_blocks"]),
            matchmaker_adjacent_value=policy._matchmaker_adjacent_value(state, player),
            builder_free_purchase_value=policy._builder_free_purchase_value(state, player),
            scammer_coin_value=float(scammer["coin_value"]),
            scammer_best_tile_coins=float(scammer["best_tile_coins"]),
            scammer_blocks_enemy_monopoly=float(scammer["blocks_enemy_monopoly"]),
            scammer_finishes_own_monopoly=float(scammer["finishes_own_monopoly"]),
            max_enemy_stack=float(stack_ctx["max_enemy_stack"]),
            max_enemy_owned_stack=float(stack_ctx["max_enemy_owned_stack"]),
            mobility_leverage=policy._mobility_leverage_score(player),
            own_tile_income=policy._expected_own_tile_income(state, player),
            lap_fast_window=float(lap_ctx["fast_window"]),
            lap_mobility=float(lap_ctx["mobility"]),
            lap_rich_pool=float(lap_ctx["rich_pool"]),
            lap_double_lap_threat=float(lap_ctx["double_lap_threat"]),
            own_burden=float(burden_context["own_burdens"]),
            cleanup_pressure=float(burden_context["cleanup_pressure"]),
            legal_visible_burden_total=float(burden_context["legal_visible_burden_total"]),
            legal_visible_burden_peak=float(burden_context["legal_visible_burden_peak"]),
            legal_low_cash_targets=float(burden_context["legal_low_cash_targets"]),
            has_mark_targets=bool(legal_mark_targets),
            failed_mark_removed_small=float(removed_small),
            failed_mark_removed_large=float(removed_large),
            failed_mark_payout_small=float(payout_small),
            failed_mark_payout_large=float(payout_large),
            reachable_specials_with_one_short=policy._reachable_specials_with_one_short(state, player),
            marker_owner_is_self=state.marker_owner_id == player.player_id,
            uroe_blocked=policy._has_uhsa_alive(state, exclude_player_id=player.player_id)
            and CHARACTERS[character_name].attribute == CHARACTERS[CARD_TO_NAMES[2][1]].attribute,
        ),
    )
    score += structural_delta
    reasons.extend(structural_reasons)

    mark_risk, mark_reasons = policy._public_mark_risk_breakdown(state, player, character_name)
    if mark_risk > 0.0:
        score -= mark_risk
        reasons.append(f"mark_risk=-{mark_risk:.2f}")
        reasons.extend(mark_reasons)

    rent_pressure, rent_reasons = policy._rent_pressure_breakdown(state, player, character_name)
    if rent_pressure > 0.0:
        score += policy._apply_rent_pressure_adjustment_v1(state, player, character_name, rent_pressure, reasons)
        reasons.append(f"rent_pressure={rent_pressure:.2f}")
        reasons.extend(rent_reasons)
    return score, reasons


def score_character_v2(policy: Any, state: Any, player: Any, character_name: str) -> tuple[float, list[str]]:
    w = policy._weights()
    score = policy.character_values.get(character_name, 0.0)
    reasons = [f"base={score:.1f}"]
    expansion = economy = disruption = meta = combo = survival = 0.0

    buy_value = policy._expected_buy_value(state, player)
    cross_start = policy._will_cross_start(state, player)
    land_f = policy._will_land_on_f(state, player)
    f_ctx = policy._f_progress_context(state, player)
    land_f_value = float(f_ctx["land_f_value"])
    burden_count = count_burden_cards(player.trick_hand)
    legal_marks = policy._allowed_mark_targets(state, player)
    has_marks = bool(legal_marks)
    burden_context = policy._burden_context(state, player, legal_targets=legal_marks)
    monopoly = policy._monopoly_block_metrics(state, player)
    scammer = policy._scammer_takeover_metrics(state, player)
    weather_bonus, weather_reasons = policy._weather_character_adjustment(state, player, character_name)
    if weather_bonus:
        combo += weather_bonus
        reasons.extend(weather_reasons)

    cleanup_pressure = float(burden_context["cleanup_pressure"])
    legal_visible_burden_total = float(burden_context["legal_visible_burden_total"])
    legal_visible_burden_peak = float(burden_context["legal_visible_burden_peak"])
    legal_low_cash_targets = float(burden_context["legal_low_cash_targets"])
    liquidity = policy._liquidity_risk_metrics(state, player, character_name)
    reserve_gap = max(0.0, float(liquidity["reserve"]) - float(player.cash))
    money_distress = max(0.0, reserve_gap * 0.55 + max(0.0, cleanup_pressure - 1.0) * 0.30)
    profile = policy._profile_from_mode()
    cleanup_strategy = policy._cleanup_strategy_context(
        policy._generic_survival_context(state, player, character_name),
        player,
    )
    threat_targets = sorted(
        policy._alive_enemies(state, player),
        key=lambda op: policy._estimated_threat(state, player, op),
        reverse=True,
    )
    top_threat = threat_targets[0] if threat_targets else None
    top_tags = policy._predicted_opponent_archetypes(state, player, top_threat) if top_threat else set()
    leader_pressure = policy._leader_pressure(state, player, top_threat)
    denial_snapshot = policy._leader_denial_snapshot(state, player, threat_targets=threat_targets, top_threat=top_threat)
    leader_emergency = float(denial_snapshot["emergency"])
    leader_is_solo = bool(denial_snapshot["solo_leader"])
    leader_near_end = bool(denial_snapshot["near_end"])
    land_race = policy._early_land_race_context(state, player)
    lap_ctx = policy._lap_engine_context(state, player)
    stack_ctx = policy._enemy_stack_metrics(state, player)
    mobility_leverage = policy._mobility_leverage_score(player)
    token_combo = policy._token_teleport_combo_score(player)
    own_land = policy._prob_land_on_placeable_own_tile(state, player)
    token_window = policy._best_token_window_value(state, player)
    distress_level = max(0.0, reserve_gap) + 0.75 * max(0.0, cleanup_pressure - 1.5) + 1.10 * max(0.0, money_distress - 0.9)
    placeable = any(
        state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        for i in player.visited_owned_tile_indices
    )
    combo_names = {c.name for c in player.trick_hand}
    marker_plan = policy._leader_marker_flip_plan(state, player, top_threat) if top_threat else {"best_score": 0.0}
    top_threat_cash = max([top_threat.cash if top_threat else 0] + [op.cash for op in legal_marks]) if legal_marks else (0 if top_threat is None else top_threat.cash)
    leading = sum(
        1
        for op in policy._alive_enemies(state, player)
        if policy._estimated_threat(state, player, player) >= policy._estimated_threat(state, player, op)
    ) == len(policy._alive_enemies(state, player))
    finisher_window, finisher_reason = policy._control_finisher_window(player)

    expansion_delta, disruption_delta, combo_delta, helper_reasons = evaluate_v2_expansion_rules(
        character_name,
        V2ExpansionInputs(
            buy_value=buy_value,
            cleanup_pressure=cleanup_pressure,
            cash_after_reserve=float(liquidity["cash_after_reserve"]),
            near_unowned=float(land_race["near_unowned"]),
            shards=player.shards,
            enemy_tiles=sum(p.tiles_owned for p in policy._alive_enemies(state, player)),
            leader_pressure=leader_pressure,
            top_threat_tiles_owned=0 if top_threat is None else top_threat.tiles_owned,
            top_threat_is_expansion=top_threat is not None and ("expansion" in top_tags or top_threat.tiles_owned >= 5),
            top_threat_present=top_threat is not None,
            land_f=land_f,
            exclusive_blocks=policy._exclusive_blocks_owned(state, player.player_id),
            scammer_coin_value=float(scammer["coin_value"]),
            scammer_best_tile_coins=float(scammer["best_tile_coins"]),
            matchmaker_adjacent_value=policy._matchmaker_adjacent_value(state, player),
            builder_free_purchase_value=policy._builder_free_purchase_value(state, player),
            combo_has_expansion_trick=any(name in combo_names for name in {"è‡¾ëŒ€ì¦º ï§ì•¹ì ™", "ï§ëˆë–¦è«›?"}),
            combo_has_arrival_takeover_trick="æ´¹ë±€ë––??éºê¾¨â”éºë‰ë¸ž" in combo_names,
        ),
        profile=profile,
    )
    expansion += expansion_delta
    disruption += disruption_delta
    combo += combo_delta
    reasons.extend(helper_reasons)

    pieces: list[tuple] = [
        evaluate_v2_route_rules(
            character_name,
            V2RouteInputs(
                cash=player.cash,
                placeable=placeable,
                own_near_complete=float(monopoly["own_near_complete"]),
                own_claimable_blocks=float(monopoly["own_claimable_blocks"]),
                enemy_near_complete=float(monopoly["enemy_near_complete"]),
                contested_blocks=float(monopoly["contested_blocks"]),
                deny_now=float(monopoly["deny_now"]),
                matchmaker_adjacent_value=policy._matchmaker_adjacent_value(state, player),
                builder_free_purchase_value=policy._builder_free_purchase_value(state, player),
            ),
        ),
        evaluate_v2_profile_rules(
            character_name,
            V2ProfileInputs(
                profile=profile,
                leading=leading,
                has_marks=has_marks,
                leader_emergency=leader_emergency,
                leader_is_solo=leader_is_solo,
                leader_near_end=leader_near_end,
                top_threat_present=top_threat is not None,
                leader_pressure=leader_pressure,
                buy_value=buy_value,
                finisher_window=finisher_window,
                finisher_reason=finisher_reason,
                cross_start=cross_start,
                land_f=land_f,
                land_f_value=land_f_value,
                own_land=own_land,
                token_combo=token_combo,
                placeable=placeable,
                matchmaker_adjacent_value=policy._matchmaker_adjacent_value(state, player),
                builder_free_purchase_value=policy._builder_free_purchase_value(state, player),
            ),
        ),
        evaluate_v2_tactical_rules(
            character_name,
            V2TacticalInputs(
                profile=profile,
                buy_value=buy_value,
                cross_start=cross_start,
                land_f=land_f,
                land_f_value=land_f_value,
                player_shards=player.shards,
                burden_count=float(burden_count),
                cleanup_pressure=cleanup_pressure,
                legal_visible_burden_total=legal_visible_burden_total,
                legal_visible_burden_peak=legal_visible_burden_peak,
                legal_low_cash_targets=legal_low_cash_targets,
                has_marks=has_marks,
                leader_pressure=leader_pressure,
                top_threat_present=top_threat is not None,
                top_threat_tiles_owned=0 if top_threat is None else top_threat.tiles_owned,
                top_threat_cash=top_threat_cash,
                top_threat_cross=0.0 if top_threat is None else policy._will_cross_start(state, top_threat),
                top_threat_land_f=0.0 if top_threat is None else policy._will_land_on_f(state, top_threat),
                top_threat_is_expansion_geo_combo=top_threat is not None and ("expansion" in top_tags or "geo" in top_tags or "combo_ready" in top_tags or top_threat.tiles_owned >= 5),
                top_threat_is_burden="burden" in top_tags,
                top_threat_is_shard_attack_counter_target=top_threat is not None and ("shard_attack" in top_tags or is_bandit(top_threat.current_character) or is_assassin(top_threat.current_character) or is_tamgwanori(top_threat.current_character) or is_swindler(top_threat.current_character)),
                land_race_pressure=float(land_race["race_pressure"]),
                premium_unowned=float(land_race["premium_unowned"]),
                near_unowned=float(land_race["near_unowned"]),
                behind_tiles=float(land_race["behind_tiles"]),
                early_round=float(land_race["early_round"]),
                visited_owned_tile_count=len(player.visited_owned_tile_indices),
                lap_fast_window=float(lap_ctx["fast_window"]),
                lap_rich_pool=float(lap_ctx["rich_pool"]),
                lap_double_lap_threat=float(lap_ctx["double_lap_threat"]),
                mobility_leverage=mobility_leverage,
                max_enemy_stack=float(stack_ctx["max_enemy_stack"]),
                max_enemy_owned_stack=float(stack_ctx["max_enemy_owned_stack"]),
                reachable_specials_with_one_short=policy._reachable_specials_with_one_short(state, player),
                combo_has_speed_tricks=any(name in combo_names for name in {"æ€¨ì‡±ëƒ½", "?ëŒ€ì›»!", "?ê¾©? ?ãƒªë¦°"}),
                combo_has_lap_combo_tricks=any(name in combo_names for name in {"?ëš¯ì …??", "æ´¹ë±€ë––??éºê¾¨â”éºë‰ë¸ž", "?ê¾©? ?ãƒªë¦°"}),
                combo_has_relic_collector="?ê¹…Ðª ?ì„ì­›åª›Â€" in combo_names,
                cleanup_growth_locked=cleanup_strategy.growth_locked,
                cleanup_stage_score=cleanup_strategy.stage_score,
                cleanup_controller_bias=cleanup_strategy.controller_bias,
                marker_plan_best_score=float(marker_plan["best_score"]),
                own_burden_cost=float(liquidity["own_burden_cost"]),
            ),
        ),
        evaluate_v2_emergency_risk_rules(
            character_name,
            V2EmergencyRiskInputs(
                profile=profile,
                leader_emergency=leader_emergency,
                leader_is_solo=leader_is_solo,
                leader_near_end=leader_near_end,
                reserve_gap=reserve_gap,
                expected_loss=float(liquidity["expected_loss"]),
                worst_loss=float(liquidity["worst_loss"]),
                own_burden_cost=float(liquidity["own_burden_cost"]),
                player_shards=player.shards,
            ),
        ),
    ]

    if profile == "v3_gpt":
        v3_deltas = evaluate_v3_character_rules(
            character_name,
            V3CharacterInputs(
                shards=player.shards,
                burden_count=float(burden_count),
                cleanup_pressure=cleanup_pressure,
                reserve_gap=reserve_gap,
                money_distress=money_distress,
                distress_level=distress_level,
                cross_start=cross_start,
                land_f=land_f,
                land_f_value=land_f_value,
                own_land=own_land,
                token_combo=token_combo,
                token_window=token_window,
                buy_value=buy_value,
                legal_visible_burden_total=legal_visible_burden_total,
                top_threat_cash=top_threat_cash,
                stack_max_enemy=float(stack_ctx["max_enemy_stack"]),
                stack_max_enemy_owned=float(stack_ctx["max_enemy_owned_stack"]),
                mobility_leverage=mobility_leverage,
                lap_fast_window=float(lap_ctx["fast_window"]),
                lap_rich_pool=float(lap_ctx["rich_pool"]),
                lap_double_lap_threat=float(lap_ctx["double_lap_threat"]),
                placeable=placeable,
            ),
        )
        expansion += v3_deltas[0]
        economy += v3_deltas[1]
        disruption += v3_deltas[2]
        survival += v3_deltas[3]
        combo += v3_deltas[4]
        meta += v3_deltas[5]
        reasons.extend(v3_deltas[6])

    for deltas in pieces:
        expansion += deltas[0]
        economy += deltas[1]
        disruption += deltas[2]
        if len(deltas) == 5:
            survival += deltas[3]
            reasons.extend(deltas[4])
        elif len(deltas) == 6:
            survival += deltas[3]
            combo += deltas[4]
            reasons.extend(deltas[5])
        else:
            meta += deltas[3]
            combo += deltas[4]
            survival += deltas[5]
            reasons.extend(deltas[6])

    _, survival_delta, helper_reasons = evaluate_v2_post_risk_rules(
        character_name,
        V2PostRiskInputs(
            has_uhsa_alive=policy._has_uhsa_alive(state, exclude_player_id=player.player_id),
            is_muroe=CHARACTERS[character_name].attribute == CHARACTERS[CARD_TO_NAMES[2][1]].attribute,
            reserve_gap=reserve_gap,
        ),
    )
    survival += survival_delta
    reasons.extend(helper_reasons)

    mark_risk, mark_reasons = policy._public_mark_risk_breakdown(state, player, character_name)
    survival_delta, helper_reasons = evaluate_v2_tail_threat_rules(V2TailThreatInputs(mark_risk=mark_risk))
    survival += survival_delta
    reasons.extend(helper_reasons)
    reasons.extend(mark_reasons)

    rent_pressure, rent_reasons = policy._rent_pressure_breakdown(state, player, character_name)
    if rent_pressure > 0.0:
        rent_economy, rent_combo, rent_survival = policy._apply_rent_pressure_adjustment_v2(
            state,
            player,
            character_name,
            cross_start,
            land_f,
            rent_pressure,
            [],
        )
        economy_delta, combo_delta, survival_delta, helper_reasons = evaluate_v2_rent_tail_rules(
            V2RentTailInputs(
                rent_pressure=rent_pressure,
                rent_economy=rent_economy,
                rent_combo=rent_combo,
                rent_survival=rent_survival,
            )
        )
        economy += economy_delta
        combo += combo_delta
        survival += survival_delta
        reasons.extend(helper_reasons)
        reasons.extend(rent_reasons)

    survival_delta, helper_reasons = evaluate_v2_uhsa_tail_rules(
        V2UhsaTailInputs(
            blocked=policy._has_uhsa_alive(state, exclude_player_id=player.player_id)
            and CHARACTERS[character_name].attribute == CHARACTERS[CARD_TO_NAMES[2][1]].attribute,
        )
    )
    survival += survival_delta
    reasons.extend(helper_reasons)

    total = (
        score
        + w["expansion"] * expansion
        + w["economy"] * economy
        + w["disruption"] * disruption
        + w["meta"] * meta
        + w["combo"] * combo
        + w["survival"] * survival
    )
    reasons.append(f"mix=e{economy:.1f}/x{expansion:.1f}/d{disruption:.1f}/m{meta:.1f}/c{combo:.1f}/s{survival:.1f}")
    return total, reasons


def score_target_v1(policy: Any, state: Any, player: Any, actor_name: str, target: Any) -> tuple[float, list[str]]:
    score = policy.character_values.get(target.current_character, 0.0)
    reasons = [f"target_base={score:.1f}"]
    if actor_name == "?ë¨­ì»¼":
        score += 0.9 * len(target.pending_marks)
        if target.attribute == CHARACTERS[CARD_TO_NAMES[2][1]].attribute:
            score += 0.8
            reasons.append("reveal_muroe")
        if target.tiles_owned >= 2:
            score += 0.5
            reasons.append("stall_owner")
    elif actor_name == "?ê³—ìŸ»":
        score += 0.7 * player.shards
        score += 0.15 * target.cash
        reasons.append("bandit_shard_scale")
    elif actor_name == "ç•°ë¶¾ë‚è¢?":
        landing_owner = state.tile_owner[player.position]
        if landing_owner is not None and landing_owner != target.player_id:
            score += 1.6
            reasons.append("force_into_rent")
        if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
            score += 1.0
            reasons.append("force_special_tile")
    elif actor_name == "è«›ëº¤ë‹”":
        remaining = len(state.config.rules.dice.values) - len(target.used_dice_cards)
        burden = policy._visible_burden_count(player, target)
        score += 0.4 * remaining + 0.9 * burden + 0.14 * max(0, 12 - target.cash)
        reasons.append("target_many_cards")
    elif actor_name == "ï§ëš¯ë–Š":
        remaining = len(state.config.rules.dice.values) - len(target.used_dice_cards)
        burden = policy._visible_burden_count(player, target)
        score += 0.3 * max(0, 5 - remaining) + 2.0 * burden + 0.12 * max(0, 14 - target.cash)
        reasons.append("target_few_cards")
    return score, reasons


def score_target_v2(policy: Any, state: Any, player: Any, actor_name: str, target: Any) -> tuple[float, list[str]]:
    score = policy._estimated_threat(state, player, target)
    reasons = [f"threat={score:.1f}"]
    tags = policy._predicted_opponent_archetypes(state, player, target)
    denial_snapshot = policy._leader_denial_snapshot(state, player)
    top_threat = denial_snapshot["top_threat"]
    if top_threat is not None and target.player_id == top_threat.player_id and denial_snapshot["emergency"] > 0.0:
        score += 2.4 + 0.65 * float(denial_snapshot["emergency"])
        reasons.append("urgent_leader_target")
        if denial_snapshot["solo_leader"]:
            score += 0.8
            reasons.append("solo_leader_target")
        if denial_snapshot["near_end"]:
            score += 1.0
            reasons.append("near_end_target")
    if actor_name == "?ë¨­ì»¼":
        if "expansion" in tags or "geo" in tags or "combo_ready" in tags:
            score += 3.0
            reasons.append("prevent_big_turn")
    elif actor_name == "?ê³—ìŸ»":
        score += 0.25 * target.cash + 0.5 * player.shards
        if target.cash <= max(0, player.shards + 3):
            score += 1.5
            reasons.append("near_bankrupt_after_raid")
    elif actor_name == "ç•°ë¶¾ë‚è¢?":
        score += 0.8 * policy._expected_buy_value(state, player)
        landing_owner = state.tile_owner[player.position]
        if landing_owner is not None and landing_owner != target.player_id:
            score += 1.8
            reasons.append("force_into_rent")
        if state.board[player.position] in {CellKind.F1, CellKind.F2, CellKind.S, CellKind.MALICIOUS}:
            score += 1.2
            reasons.append("force_special_tile")
    elif actor_name == "è«›ëº¤ë‹”":
        burden = count_burden_cards(player.trick_hand)
        target_burden = policy._visible_burden_count(player, target)
        score += 1.1 * burden + 0.9 * target_burden + 0.16 * max(0, 12 - target.cash)
        reasons.append("dump_burdens")
    elif actor_name == "ï§ëš¯ë–Š":
        burden = policy._visible_burden_count(player, target)
        score += 2.1 * burden + 0.14 * max(0, 14 - target.cash)
        reasons.append("clear_target_burdens")
    return score, reasons
