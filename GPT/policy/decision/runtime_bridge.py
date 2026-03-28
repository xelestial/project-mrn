from __future__ import annotations

from typing import Any

from characters import CARD_TO_NAMES
from config import CellKind
from policy.context.survival_context import build_policy_survival_context
from policy.context.turn_plan import build_turn_plan_context
from policy.decision.lap_reward import (
    BasicLapRewardInputs,
    V2ProfileLapRewardInputs,
    V3LapRewardInputs,
    apply_v2_profile_lap_reward_bias,
    evaluate_basic_lap_reward,
    evaluate_v3_lap_reward,
    normalize_lap_reward_scores,
)
from policy.decision.character_choice import (
    build_character_choice_debug_payload,
    build_named_character_choice_policy,
    build_uniform_random_character_choice_debug_payload,
    run_named_character_choice_with_policy,
)
from policy.decision.mark_target import filter_public_mark_candidates, run_public_mark_choice
from policy.decision.coin_placement import choose_coin_placement_tile_id
from policy.decision.hidden_trick import COMBO_PRIORITY_TRICKS, resolve_hidden_trick_choice_run
from policy.decision.active_flip import resolve_random_active_flip_choice, resolve_scored_active_flip_choice
from policy.decision.movement import apply_movement_intent_adjustment, resolve_movement_choice
from policy.decision.purchase import (
    PurchaseBenefitInputs,
    PurchaseWindowAssessment,
    TraitPurchaseDecisionInputs,
    assess_purchase_decision_from_inputs,
    assess_v3_purchase_window_with_traits,
    build_immediate_win_purchase_result,
    build_purchase_benefit,
    build_purchase_decision_trace,
    build_purchase_debug_context,
    build_purchase_debug_payload,
    build_purchase_early_debug_payload,
    build_purchase_reserve_floor,
    count_owned_tiles_in_block,
    prepare_v3_purchase_benefit_with_traits,
    would_purchase_trigger_immediate_win,
)
from policy.pipeline_trace import DecisionTrace, build_decision_trace_payload, build_detector_hit
from policy.decision.support_choices import (
    BurdenExchangeDecisionInputs,
    GeoBonusDecisionInputs,
    choose_doctrine_relief_player_id,
    choose_geo_bonus_kind,
    count_burden_cards,
    should_exchange_burden_on_supply,
)
from policy.decision.trick_reward import resolve_trick_reward_choice_run
from policy.decision.trick_usage import apply_trick_preserve_rules, build_trick_use_debug_payload, resolve_trick_use_choice
from policy.character_traits import (
    is_active_money_drain_character,
    is_ajeon,
    is_bandit,
    is_baksu,
    is_controller_character,
    is_eosa,
    is_gakju,
    is_low_cash_controller_character,
    is_low_cash_escape_character,
    is_low_cash_income_character,
    is_mansin,
    is_shard_hunter_character,
    is_swindler,
    is_tamgwanori,
)


def _payload_with_trace(payload: dict[str, object], trace: DecisionTrace) -> dict[str, object]:
    enriched = dict(payload)
    enriched["trace"] = build_decision_trace_payload(trace)
    return enriched


def _build_character_choice_trace(
    *,
    decision_type: str,
    candidate_scores: dict[str, float],
    candidate_reasons: dict[str, list[str]],
    hard_blocked_map: dict[str, dict[str, object]],
    candidate_characters: dict[str, str] | None,
    offered_cards: list[int] | None,
    generic_survival_score: float,
    survival_urgency: float,
    survival_first: bool,
    survival_weight_multiplier: float,
    marker_bonus_by_name: dict[str, float],
    chosen_key: object,
    chosen_name: str,
) -> DecisionTrace:
    detector_hits = []
    if survival_first:
        detector_hits.append(
            build_detector_hit(
                "survival_priority_weighting",
                kind="preference",
                severity=min(1.0, max(0.0, survival_weight_multiplier - 1.0)),
                confidence=0.8,
                reason="Survival-first weighting boosted candidate evaluation.",
                tags=("character", decision_type),
                score_delta=max(0.0, survival_weight_multiplier - 1.0),
            )
        )
    for candidate_name, bonus in marker_bonus_by_name.items():
        if bonus <= 0.0:
            continue
        detector_hits.append(
            build_detector_hit(
                "distress_marker_bonus",
                kind="advantage",
                severity=min(1.0, bonus / 2.5),
                confidence=0.75,
                reason=f"{candidate_name} gained marker rescue value.",
                tags=("character", candidate_name),
                score_delta=bonus,
            )
        )
    for candidate_name, detail in hard_blocked_map.items():
        detector_hits.append(
            build_detector_hit(
                "survival_hard_block",
                kind="hard_veto",
                severity=1.0,
                confidence=0.95,
                reason=f"{candidate_name} was blocked by survival guard.",
                tags=("character", candidate_name, *tuple(sorted(str(key) for key in detail.keys()))),
            )
        )
    features: dict[str, object] = {
        "offered_cards": offered_cards or [],
        "candidate_scores": candidate_scores,
        "candidate_reasons": candidate_reasons,
        "generic_survival_score": generic_survival_score,
        "survival_urgency": survival_urgency,
        "survival_first": survival_first,
        "survival_weight_multiplier": survival_weight_multiplier,
    }
    if candidate_characters is not None:
        features["candidate_characters"] = candidate_characters
    return DecisionTrace(
        decision_type=decision_type,
        features=features,
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "hard_blocks", "value": hard_blocked_map},
            {"kind": "marker_bonus_by_name", "value": marker_bonus_by_name},
        ),
        final_choice={"key": chosen_key, "name": chosen_name},
    )


def _build_mark_target_trace(
    *,
    actor_name: str,
    legal_target_count: int,
    debug_payload: dict[str, object],
    choice: object,
) -> DecisionTrace:
    candidate_scores = dict(debug_payload.get("candidate_scores", {}))
    candidate_probabilities = dict(debug_payload.get("candidate_probabilities", {}))
    top_probability = float(debug_payload.get("top_probability", 0.0) or 0.0)
    second_probability = float(debug_payload.get("second_probability", 0.0) or 0.0)
    ambiguity = float(debug_payload.get("ambiguity", 0.0) or 0.0)
    uniform_mix = float(debug_payload.get("uniform_mix", 0.0) or 0.0)
    reasons = list(debug_payload.get("reasons", []))
    detector_hits = []
    if legal_target_count <= 0:
        detector_hits.append(
            build_detector_hit(
                "no_legal_targets",
                kind="hard_veto",
                severity=1.0,
                confidence=1.0,
                reason="No legal public mark targets were available.",
                tags=("mark_target",),
            )
        )
    if top_probability >= 0.65:
        detector_hits.append(
            build_detector_hit(
                "confident_public_guess",
                kind="advantage",
                severity=top_probability,
                confidence=top_probability,
                reason="Public mark inference had a clear top target.",
                tags=("mark_target", str(debug_payload.get("top_candidate", ""))),
            )
        )
    if ambiguity >= 0.2 or uniform_mix >= 0.1:
        detector_hits.append(
            build_detector_hit(
                "ambiguous_public_guess",
                kind="risk",
                severity=max(ambiguity, uniform_mix),
                confidence=0.7,
                reason="Public mark inference remained ambiguous.",
                tags=("mark_target",),
            )
        )
    return DecisionTrace(
        decision_type="mark_target",
        features={
            "actor_name": actor_name,
            "legal_target_count": legal_target_count,
            "candidate_scores": candidate_scores,
            "candidate_probabilities": candidate_probabilities,
            "top_probability": top_probability,
            "second_probability": second_probability,
            "ambiguity": ambiguity,
            "uniform_mix": uniform_mix,
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "chosen_reasons", "value": reasons},
            {"kind": "top_candidate", "value": debug_payload.get("top_candidate")},
        ),
        final_choice=choice,
    )


def _build_coin_placement_trace(
    *,
    candidates: list[int],
    tile_coins: list[int],
    board: list[Any],
    player_position: int,
    max_coins_per_tile: int,
    token_opt_profile: bool,
    choice: int | None,
) -> DecisionTrace:
    board_len = max(1, len(board))
    candidate_details = []
    for tile_id in candidates:
        distance = ((tile_id - player_position) % board_len) or board_len
        detail = {
            "tile_id": tile_id,
            "coins": int(tile_coins[tile_id]),
            "is_t3": board[tile_id] == CellKind.T3,
            "distance": distance,
            "open_slots": int(max_coins_per_tile - tile_coins[tile_id]),
        }
        if token_opt_profile:
            detail["rank_tuple"] = [
                int(tile_coins[tile_id]),
                1 if board[tile_id] == CellKind.T3 else 0,
                -distance,
                int(max_coins_per_tile - tile_coins[tile_id]),
                -int(tile_id),
            ]
        else:
            detail["rank_tuple"] = [
                int(max_coins_per_tile - tile_coins[tile_id]),
                1 if board[tile_id] == CellKind.T3 else 0,
                -int(tile_id),
            ]
        candidate_details.append(detail)
    detector_hits = []
    if token_opt_profile:
        detector_hits.append(
            build_detector_hit(
                "token_opt_profile",
                kind="preference",
                severity=0.8,
                confidence=0.9,
                reason="Token-optimization profile prefers revisit-heavy placement.",
                tags=("coin_placement",),
            )
        )
    if choice is not None and board[choice] == CellKind.T3:
        detector_hits.append(
            build_detector_hit(
                "t3_coin_preference",
                kind="advantage",
                severity=0.6,
                confidence=0.8,
                reason="Chosen tile is a high-value T3 placement target.",
                tags=("coin_placement", str(choice)),
            )
        )
    if choice is not None:
        chosen_distance = ((choice - player_position) % board_len) or board_len
        if chosen_distance <= 4:
            detector_hits.append(
                build_detector_hit(
                    "near_revisit_window",
                    kind="advantage",
                    severity=max(0.2, 1.0 - chosen_distance / 4.0),
                    confidence=0.7,
                    reason="Chosen placement sits close to the player's route.",
                    tags=("coin_placement", str(choice)),
                )
            )
    return DecisionTrace(
        decision_type="coin_placement",
        features={
            "player_position": player_position,
            "max_coins_per_tile": max_coins_per_tile,
            "token_opt_profile": token_opt_profile,
            "candidates": candidate_details,
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=({"kind": "candidate_rankings", "value": candidate_details},),
        final_choice=choice,
    )


def _build_active_flip_trace(
    *,
    flippable_cards: list[int],
    state: Any,
    scored: dict[int, float],
    reasons: dict[int, list[str]],
    choice: int | None,
    generic_survival_score: float,
    money_distress: float,
    controller_need: float,
) -> DecisionTrace:
    detector_hits = []
    if choice is not None:
        for reason in reasons.get(choice, []):
            if reason.startswith("counter_leader_needed_face"):
                detector_hits.append(
                    build_detector_hit(
                        "counter_leader_flip",
                        kind="advantage",
                        severity=0.9,
                        confidence=0.8,
                        reason="Flip helps deny the current leader package.",
                        tags=("marker_flip", str(choice)),
                    )
                )
            elif reason.startswith("avoid_feeding_leader"):
                detector_hits.append(
                    build_detector_hit(
                        "avoid_feeding_leader",
                        kind="risk",
                        severity=0.8,
                        confidence=0.8,
                        reason="Flip avoids empowering a leading opponent.",
                        tags=("marker_flip", str(choice)),
                    )
                )
            elif "money_relief_flip" in reason:
                detector_hits.append(
                    build_detector_hit(
                        "money_relief_flip",
                        kind="advantage",
                        severity=min(1.0, 0.5 + controller_need + money_distress),
                        confidence=0.8,
                        reason="Flip relieves an active money-drain burden.",
                        tags=("marker_flip", str(choice)),
                    )
                )
            elif "avoid_enable_money_drain" in reason:
                detector_hits.append(
                    build_detector_hit(
                        "avoid_enable_money_drain",
                        kind="risk",
                        severity=min(1.0, 0.5 + controller_need + money_distress),
                        confidence=0.8,
                        reason="Flip avoids enabling an active money-drain face.",
                        tags=("marker_flip", str(choice)),
                    )
                )
    return DecisionTrace(
        decision_type="active_flip",
        features={
            "flippable_cards": flippable_cards,
            "current_faces": {str(card_no): state.active_by_card[card_no] for card_no in flippable_cards},
            "candidate_scores": {str(card_no): round(score, 3) for card_no, score in scored.items()},
            "generic_survival_score": generic_survival_score,
            "money_distress": money_distress,
            "controller_need": controller_need,
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "candidate_reasons", "value": {str(card_no): why for card_no, why in reasons.items()}},
        ),
        final_choice=choice,
    )


def _build_burden_exchange_trace(
    *,
    card_name: str,
    burden_cost: float,
    cash_before: float,
    remaining_cash: float,
    reserve: float,
    target_floor: float,
    hard_reason: str | None,
    decision: bool,
    escape_guard: bool,
) -> DecisionTrace:
    detector_hits = []
    if cash_before < burden_cost:
        detector_hits.append(
            build_detector_hit(
                "insufficient_cash",
                kind="hard_veto",
                severity=1.0,
                confidence=1.0,
                reason="Player cannot afford the burden exchange cost.",
                tags=("burden_exchange",),
            )
        )
    if escape_guard:
        detector_hits.append(
            build_detector_hit(
                "escape_package_guard",
                kind="hard_veto",
                severity=1.0,
                confidence=0.9,
                reason="Escape-package pressure blocks burden exchange.",
                tags=("burden_exchange",),
            )
        )
    floor_gate = max(5.0, 0.80 * reserve)
    if remaining_cash <= floor_gate:
        detector_hits.append(
            build_detector_hit(
                "danger_cash_floor",
                kind="risk",
                severity=min(1.0, max(0.0, floor_gate - remaining_cash + 1.0) / max(1.0, floor_gate)),
                confidence=0.85,
                reason="Remaining cash would fall under the exchange safety floor.",
                tags=("burden_exchange",),
            )
        )
    if hard_reason is not None:
        detector_hits.append(
            build_detector_hit(
                "survival_hard_guard",
                kind="hard_veto",
                severity=1.0,
                confidence=0.95,
                reason=f"Survival guard blocked the exchange: {hard_reason}",
                tags=("burden_exchange", hard_reason),
            )
        )
    if decision:
        detector_hits.append(
            build_detector_hit(
                "safe_exchange_window",
                kind="advantage",
                severity=min(1.0, max(0.0, remaining_cash - target_floor + 1.0) / max(1.0, target_floor)),
                confidence=0.8,
                reason="Exchange stays above the projected safety floor.",
                tags=("burden_exchange",),
            )
        )
    return DecisionTrace(
        decision_type="burden_exchange",
        features={
            "card_name": card_name,
            "burden_cost": burden_cost,
            "cash_before": cash_before,
            "remaining_cash": remaining_cash,
            "reserve": reserve,
            "target_floor": target_floor,
            "hard_reason": hard_reason,
            "escape_guard": escape_guard,
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "decision_thresholds", "value": {"cash_floor": floor_gate, "target_floor": target_floor}},
        ),
        final_choice=decision,
    )


def _build_doctrine_relief_trace(
    *,
    self_player_id: int,
    candidate_ids: list[int],
    choice: int | None,
) -> DecisionTrace:
    detector_hits = []
    if self_player_id in candidate_ids and choice == self_player_id:
        detector_hits.append(
            build_detector_hit(
                "self_relief_preference",
                kind="advantage",
                severity=0.7,
                confidence=0.9,
                reason="Doctrine relief keeps burden removal on the acting player.",
                tags=("doctrine_relief", str(self_player_id)),
            )
        )
    elif choice is not None:
        detector_hits.append(
            build_detector_hit(
                "fallback_relief_target",
                kind="fallback",
                severity=0.4,
                confidence=0.9,
                reason="Doctrine relief fell back to the first legal candidate.",
                tags=("doctrine_relief", str(choice)),
            )
        )
    return DecisionTrace(
        decision_type="doctrine_relief",
        features={"self_player_id": self_player_id, "candidate_ids": candidate_ids},
        detector_hits=tuple(detector_hits),
        effect_adjustments=(),
        final_choice=choice,
    )


def _build_geo_bonus_trace(
    *,
    actor_name: str,
    features: dict[str, object],
    scores: dict[str, float],
    choice: str,
) -> DecisionTrace:
    detector_hits = []
    own_burdens = float(features.get("own_burdens", 0.0) or 0.0)
    next_neg = float(features.get("next_neg", 0.0) or 0.0)
    two_neg = float(features.get("two_neg", 0.0) or 0.0)
    cleanup_cash_gap = float(features.get("cleanup_cash_gap", 0.0) or 0.0)
    is_leader = bool(features.get("is_leader", True))
    if choice == "cash" and (
        own_burdens >= 1.0
        or next_neg >= 0.10
        or two_neg >= 0.22
        or cleanup_cash_gap > 0.0
        or not is_leader
    ):
        detector_hits.append(
            build_detector_hit(
                "cleanup_cash_pressure",
                kind="advantage",
                severity=min(1.0, max(own_burdens * 0.25, next_neg + two_neg, cleanup_cash_gap / 6.0, 0.35 if not is_leader else 0.0)),
                confidence=0.85,
                reason="Cash bonus chosen to cover cleanup or pacing pressure.",
                tags=("geo_bonus", actor_name),
                score_delta=max(0.0, scores.get("cash", 0.0) - max(scores.get("shards", 0.0), scores.get("coins", 0.0))),
            )
        )
    if choice == "shards":
        detector_hits.append(
            build_detector_hit(
                "shard_window",
                kind="advantage",
                severity=min(1.0, max(0.2, scores.get("shards", 0.0) / max(1.0, max(scores.values()) if scores else 1.0))),
                confidence=0.75,
                reason="Shard bonus best matched the actor's advancement window.",
                tags=("geo_bonus", actor_name),
            )
        )
    if choice == "coins":
        detector_hits.append(
            build_detector_hit(
                "coin_engine_window",
                kind="advantage",
                severity=min(1.0, max(0.2, scores.get("coins", 0.0) / max(1.0, max(scores.values()) if scores else 1.0))),
                confidence=0.75,
                reason="Coin bonus best matched the actor's board engine window.",
                tags=("geo_bonus", actor_name),
            )
        )
    return DecisionTrace(
        decision_type="geo_bonus",
        features={"actor_name": actor_name, **features, "candidate_scores": scores},
        detector_hits=tuple(detector_hits),
        effect_adjustments=({"kind": "candidate_scores", "value": scores},),
        final_choice=choice,
    )


def choose_purchase_tile_runtime(
    policy: Any,
    state: Any,
    player: Any,
    pos: int,
    cell: Any,
    cost: int,
    *,
    source: str = "landing",
) -> bool:
    if cost <= 0 or policy._is_random_mode():
        return True
    liquidity = policy._liquidity_risk_metrics(state, player, player.current_character)
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    remaining_cash = player.cash - cost
    reserve = max(float(liquidity["reserve"]), float(survival_ctx["reserve"]))
    if not policy._is_action_survivable(
        state,
        player,
        immediate_cost=float(cost),
        survival_ctx=survival_ctx,
        reserve_floor=reserve,
        buffer=0.5,
    ):
        policy._set_debug(
            "purchase_decision",
            player.player_id,
            {
                "source": source,
                "pos": pos,
                "cell": cell.name,
                "cost": cost,
                "decision": False,
                "reason": "global_action_survival_guard",
                "reserve": round(float(reserve), 3),
                "cash": player.cash,
            },
        )
        return False

    complete_monopoly = policy._would_complete_monopoly_with_purchase(state, player, pos)
    blocks_enemy = policy._would_block_enemy_monopoly_with_purchase(state, player, pos)
    immediate_win = would_purchase_trigger_immediate_win(
        tiles_owned=player.tiles_owned,
        tiles_to_trigger_end=state.config.rules.end.tiles_to_trigger_end,
        monopolies_to_trigger_end=state.config.rules.end.monopolies_to_trigger_end,
        complete_monopoly=complete_monopoly,
    )
    profile = policy._profile_from_mode()
    survival_view = build_policy_survival_context(survival_ctx, cash=player.cash, shards=player.shards)
    token_window_value = 0.0

    if immediate_win:
        result = build_immediate_win_purchase_result(reserve=reserve)
        purchase_trace = build_purchase_decision_trace(
            context=build_purchase_debug_context(
                source=source,
                pos=pos,
                cell_name=cell.name,
                cost=cost,
                cash_before=float(player.cash),
                cash_after=float(remaining_cash),
                reserve=float(reserve),
                money_distress=float(survival_view.money_distress),
                two_turn_lethal_prob=float(survival_view.signals.two_turn_lethal_prob),
                latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                cleanup_cash_gap=float(survival_view.cleanup_cash_gap),
                expected_loss=float(liquidity["expected_loss"]),
                worst_loss=float(liquidity["worst_loss"]),
                blocks_enemy_monopoly=blocks_enemy,
                token_window_value=float(0.0),
            ),
            result=result,
            benefit=float(cost),
            complete_monopoly=complete_monopoly,
            hard_reason=None,
            purchase_window=None,
        )
    else:
        owned_in_block = count_owned_tiles_in_block(
            block_ids=state.block_ids,
            tile_owner=state.tile_owner,
            pos=pos,
            player_id=player.player_id,
        )
        benefit = build_purchase_benefit(
            PurchaseBenefitInputs(
                cell=cell,
                profile=profile,
                complete_monopoly=complete_monopoly,
                blocks_enemy=blocks_enemy,
                owned_in_block=owned_in_block,
                is_unowned_tile=state.tile_owner[pos] is None,
            )
        )
        token_window_value = policy._best_token_window_value(state, player)
        if profile == "v3_gpt":
            prepared = prepare_v3_purchase_benefit_with_traits(
                current_character=player.current_character,
                shards=player.shards,
                cell=cell,
                cost=cost,
                remaining_cash=remaining_cash,
                reserve=reserve,
                cleanup_pressure=survival_view.cleanup_pressure,
                money_distress=survival_view.money_distress,
                own_burdens=survival_view.own_burdens,
                token_window_value=token_window_value,
                complete_monopoly=complete_monopoly,
                blocks_enemy=blocks_enemy,
                current_benefit=benefit,
            )
            if prepared.early_token_window_veto:
                purchase_trace = build_purchase_decision_trace(
                    context=build_purchase_debug_context(
                        source=source,
                        pos=pos,
                        cell_name=cell.name,
                        cost=cost,
                        cash_before=float(player.cash),
                        cash_after=float(remaining_cash),
                        reserve=float(reserve),
                        money_distress=float(survival_view.money_distress),
                        two_turn_lethal_prob=float(survival_view.signals.two_turn_lethal_prob),
                        latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                        cleanup_cash_gap=float(survival_view.cleanup_cash_gap),
                        expected_loss=float(liquidity["expected_loss"]),
                        worst_loss=float(liquidity["worst_loss"]),
                        blocks_enemy_monopoly=blocks_enemy,
                        token_window_value=float(token_window_value),
                    ),
                    result=assess_purchase_decision_from_inputs(
                        TraitPurchaseDecisionInputs(
                            profile=profile,
                            current_character=player.current_character,
                            cash_before=float(player.cash),
                            remaining_cash=float(remaining_cash),
                            reserve=float(reserve),
                            reserve_floor=float(reserve),
                            benefit=float(benefit),
                            token_window_value=float(token_window_value),
                            money_distress=float(survival_view.money_distress),
                            complete_monopoly=complete_monopoly,
                            blocks_enemy=blocks_enemy,
                            hard_reason=None,
                            own_burdens=float(survival_view.own_burdens),
                            next_neg=float(survival_view.next_draw_negative_cleanup_prob),
                            two_neg=float(survival_view.two_draw_negative_cleanup_prob),
                            negative_cards=float(survival_view.remaining_negative_cleanup_cards),
                            downside_cleanup=float(survival_view.downside_expected_cleanup_cost),
                            worst_cleanup=float(survival_view.worst_cleanup_cost),
                            public_cleanup_active=bool(survival_view.public_cleanup_active),
                            active_cleanup_cost=float(survival_view.active_cleanup_cost),
                            latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                            purchase_window=PurchaseWindowAssessment(
                                reserve_floor=float(reserve),
                                safe_low_cost_t3=prepared.safe_low_cost_t3,
                                safe_growth_buy=prepared.safe_growth_buy,
                                token_preferred=True,
                                v3_cleanup_soft_block=False,
                                baksu_online_exception=False,
                            ),
                        )
                    ),
                    benefit=float(benefit),
                    complete_monopoly=complete_monopoly,
                    hard_reason=None,
                    purchase_window=PurchaseWindowAssessment(
                        reserve_floor=float(reserve),
                        safe_low_cost_t3=prepared.safe_low_cost_t3,
                        safe_growth_buy=prepared.safe_growth_buy,
                        token_preferred=True,
                        v3_cleanup_soft_block=False,
                        baksu_online_exception=False,
                    ),
                )
                policy._set_debug(
                    "buy",
                    player.player_id,
                    build_purchase_early_debug_payload(
                        source=source,
                        pos=pos,
                        cell_name=cell.name,
                        cost=cost,
                        decision=False,
                        reason="v3_prefers_token_window",
                        benefit=benefit,
                        token_window=token_window_value,
                        trace=purchase_trace,
                    ),
                )
                return False
            benefit = prepared.benefit
            purchase_window = assess_v3_purchase_window_with_traits(
                current_character=player.current_character,
                shards=player.shards,
                cell=cell,
                cost=cost,
                remaining_cash=remaining_cash,
                reserve=reserve,
                survival=survival_view,
                token_window_value=token_window_value,
                benefit=benefit,
                complete_monopoly=complete_monopoly,
                blocks_enemy=blocks_enemy,
            )
            reserve_floor = purchase_window.reserve_floor
        else:
            purchase_window = None
            reserve_floor = build_purchase_reserve_floor(
                reserve=reserve,
                remaining_cash=remaining_cash,
                survival=survival_view,
                public_cleanup_active=survival_view.public_cleanup_active,
                active_cleanup_cost=survival_view.active_cleanup_cost,
                downside_expected_cleanup_cost=survival_view.downside_expected_cleanup_cost,
                worst_cleanup_cost=survival_view.worst_cleanup_cost,
                latent_cleanup_cost=survival_view.latent_cleanup_cost,
                needs_income=survival_view.needs_income,
            )

        result = assess_purchase_decision_from_inputs(
            TraitPurchaseDecisionInputs(
                profile=profile,
                current_character=player.current_character,
                cash_before=float(player.cash),
                remaining_cash=float(remaining_cash),
                reserve=float(reserve),
                reserve_floor=float(reserve_floor),
                benefit=float(benefit),
                token_window_value=float(token_window_value),
                money_distress=float(survival_view.money_distress),
                complete_monopoly=complete_monopoly,
                blocks_enemy=blocks_enemy,
                hard_reason=policy._survival_hard_guard_reason(
                    state,
                    player,
                    survival_ctx,
                    post_action_cash=remaining_cash,
                ),
                own_burdens=float(survival_view.own_burdens),
                next_neg=float(survival_view.next_draw_negative_cleanup_prob),
                two_neg=float(survival_view.two_draw_negative_cleanup_prob),
                negative_cards=float(survival_view.remaining_negative_cleanup_cards),
                downside_cleanup=float(survival_view.downside_expected_cleanup_cost),
                worst_cleanup=float(survival_view.worst_cleanup_cost),
                public_cleanup_active=bool(survival_view.public_cleanup_active),
                active_cleanup_cost=float(survival_view.active_cleanup_cost),
                latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                purchase_window=purchase_window,
            )
        )
        purchase_trace = build_purchase_decision_trace(
            context=build_purchase_debug_context(
                source=source,
                pos=pos,
                cell_name=cell.name,
                cost=cost,
                cash_before=float(player.cash),
                cash_after=float(remaining_cash),
                reserve=float(reserve),
                money_distress=float(survival_view.money_distress),
                two_turn_lethal_prob=float(survival_view.signals.two_turn_lethal_prob),
                latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                cleanup_cash_gap=float(survival_view.cleanup_cash_gap),
                expected_loss=float(liquidity["expected_loss"]),
                worst_loss=float(liquidity["worst_loss"]),
                blocks_enemy_monopoly=blocks_enemy,
                token_window_value=float(0.0 if immediate_win else token_window_value),
            ),
            result=result,
            benefit=float(benefit),
            complete_monopoly=complete_monopoly,
            hard_reason=policy._survival_hard_guard_reason(
                state,
                player,
                survival_ctx,
                post_action_cash=remaining_cash,
            ),
            purchase_window=purchase_window,
        )

    policy._set_debug(
        "purchase_decision",
        player.player_id,
        build_purchase_debug_payload(
            context=build_purchase_debug_context(
                source=source,
                pos=pos,
                cell_name=cell.name,
                cost=cost,
                cash_before=float(player.cash),
                cash_after=float(remaining_cash),
                reserve=float(reserve),
                money_distress=float(survival_view.money_distress),
                two_turn_lethal_prob=float(survival_view.signals.two_turn_lethal_prob),
                latent_cleanup_cost=float(survival_view.latent_cleanup_cost),
                cleanup_cash_gap=float(survival_view.cleanup_cash_gap),
                expected_loss=float(liquidity["expected_loss"]),
                worst_loss=float(liquidity["worst_loss"]),
                blocks_enemy_monopoly=blocks_enemy,
                token_window_value=float(0.0 if immediate_win else token_window_value),
            ),
            result=result,
            trace=purchase_trace,
        ),
    )
    return result.decision


def _build_movement_trace(*, resolution: Any, intent: Any, f_ctx: dict[str, Any], remaining_cards: tuple[int, ...]) -> DecisionTrace:
    detector_hits = []
    best_single = max(resolution.single_card_scores, key=lambda item: item[1], default=None)
    best_double = max(resolution.double_card_scores, key=lambda item: item[1], default=None)
    if resolution.use_cards and intent.resource_intent == "card_preserve":
        detector_hits.append(
            build_detector_hit(
                "preserve_cards_bias",
                kind="guard",
                severity=0.72,
                confidence=0.82,
                reason="Turn plan prefers preserving cards, so card-spend movement needs a clear upside.",
                tags=("movement", "intent"),
                score_delta=-0.55 * len(resolution.card_values),
            )
        )
    if not resolution.use_cards and remaining_cards:
        best_card_score = max(
            [score for _, score in resolution.single_card_scores] + [score for _, score in resolution.double_card_scores],
            default=resolution.avg_no_cards,
        )
        detector_hits.append(
            build_detector_hit(
                "hold_cards_default",
                kind="advantage",
                severity=0.62,
                confidence=0.8,
                reason="The baseline dice line stayed ahead, so the policy kept movement cards for later turns.",
                tags=("movement", "card_economy"),
                score_delta=max(0.0, resolution.avg_no_cards - best_card_score),
            )
        )
    if bool(f_ctx["is_leader"]) and resolution.score >= resolution.avg_no_cards + 6.0:
        detector_hits.append(
            build_detector_hit(
                "leader_spike_window",
                kind="advantage",
                severity=0.75,
                confidence=0.78,
                reason="Leader status allows a strong tempo spike from this movement line.",
                tags=("movement", "tempo"),
                score_delta=0.4,
            )
        )
    if resolution.use_cards and len(resolution.card_values) == 1 and resolution.score >= resolution.avg_no_cards + 1.5:
        detector_hits.append(
            build_detector_hit(
                "single_card_tempo_pick",
                kind="advantage",
                severity=0.58,
                confidence=0.76,
                reason="A one-card movement line created enough tempo to beat the baseline dice plan.",
                tags=("movement", "tempo"),
                score_delta=resolution.score - resolution.avg_no_cards,
            )
        )
    if len(resolution.card_values) >= 2 and intent.plan_key == "lap_engine":
        detector_hits.append(
            build_detector_hit(
                "two_card_commit_window",
                kind="advantage",
                severity=0.68,
                confidence=0.76,
                reason="Two-card movement is being accepted as part of an active lap-engine push.",
                tags=("movement", "lap_engine"),
                score_delta=resolution.score - resolution.avg_no_cards,
            )
        )

    return DecisionTrace(
        decision_type="movement",
        features={
            "avg_no_cards": resolution.avg_no_cards,
            "chosen_score": resolution.score,
            "remaining_cards": list(remaining_cards),
            "best_single_card": None if best_single is None else {"card": best_single[0], "score": round(float(best_single[1]), 3)},
            "best_double_card": None if best_double is None else {"cards": list(best_double[0]), "score": round(float(best_double[1]), 3)},
            "plan_key": intent.plan_key,
            "resource_intent": intent.resource_intent,
            "is_leader": bool(f_ctx["is_leader"]),
            "land_f_value": float(f_ctx["land_f_value"]),
            "avoid_f_acceleration": float(f_ctx["avoid_f_acceleration"]),
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {
                "kind": "single_card_scores",
                "values": {str(card): round(score, 3) for card, score in resolution.single_card_scores},
            },
            {
                "kind": "double_card_scores",
                "values": {
                    f"{first}+{second}": round(score, 3)
                    for (first, second), score in resolution.double_card_scores
                },
            },
        ),
        final_choice={
            "use_cards": resolution.use_cards,
            "card_values": list(resolution.card_values),
            "score": round(float(resolution.score), 3),
        },
    )


def _build_trick_use_trace(
    *,
    hand: list[Any],
    resolution: Any,
    generic_survival_score: float,
    survival_urgency: float,
    strategic_mode: float,
    intent: Any,
) -> DecisionTrace:
    detector_hits = []
    score_map = dict(getattr(resolution, "score_map", {}) or {})
    top_score = max(score_map.values(), default=0.0)
    chosen = getattr(resolution, "choice", None)
    if chosen is None:
        detector_hits.append(
            build_detector_hit(
                "no_positive_trick_line",
                kind="guard",
                severity=0.72,
                confidence=0.86,
                reason="No trick card cleared the minimum value threshold, so the hand was preserved.",
                tags=("trick_use", "card_preserve"),
                score_delta=-max(0.0, float(top_score)),
            )
        )
    else:
        if survival_urgency >= 1.0:
            detector_hits.append(
                build_detector_hit(
                    "emergency_trick_use",
                    kind="advantage",
                    severity=min(1.0, survival_urgency / 2.0),
                    confidence=0.82,
                    reason="The chosen trick was committed in a high-survival-urgency spot.",
                    tags=("trick_use", "survival", chosen.name),
                    score_delta=max(0.0, float(score_map.get(chosen.name, 0.0))),
                )
            )
        if strategic_mode >= 1.0:
            detector_hits.append(
                build_detector_hit(
                    "decisive_trick_window",
                    kind="advantage",
                    severity=min(1.0, strategic_mode / 2.0),
                    confidence=0.78,
                    reason="The chosen trick aligned with a decisive tactical window.",
                    tags=("trick_use", "tempo", chosen.name),
                    score_delta=max(0.0, float(score_map.get(chosen.name, 0.0))),
                )
            )
        if bool(getattr(chosen, "is_anytime", False)):
            detector_hits.append(
                build_detector_hit(
                    "spent_anytime_trick",
                    kind="preference",
                    severity=0.45,
                    confidence=0.72,
                    reason="An anytime trick was spent now instead of being held for a later reaction window.",
                    tags=("trick_use", "anytime", chosen.name),
                )
            )
    return DecisionTrace(
        decision_type="trick_use",
        features={
            "hand": [getattr(card, "name", str(card)) for card in hand],
            "score_map": score_map,
            "generic_survival_score": generic_survival_score,
            "survival_urgency": survival_urgency,
            "strategic_mode": strategic_mode,
            "intent": None if intent is None else getattr(intent, "resource_intent", None),
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "top_score", "value": round(float(top_score), 3)},
        ),
        final_choice=None if chosen is None else {"name": chosen.name, "is_anytime": bool(getattr(chosen, "is_anytime", False))},
    )


def _build_hidden_trick_trace(*, actor_name: str | None, hand: list[Any], choice: Any, score_map: dict[str, float]) -> DecisionTrace:
    detector_hits = []
    if choice is None:
        detector_hits.append(
            build_detector_hit(
                "no_hidden_trick_choice",
                kind="hard_veto",
                severity=1.0,
                confidence=1.0,
                reason="No trick card was available to hide.",
                tags=("hidden_trick",),
            )
        )
    else:
        if bool(getattr(choice, "is_burden", False)):
            detector_hits.append(
                build_detector_hit(
                    "hide_burden_first",
                    kind="advantage",
                    severity=0.9,
                    confidence=0.9,
                    reason="A burden card was hidden first to reduce exposed downside.",
                    tags=("hidden_trick", "burden", choice.name),
                    score_delta=float(getattr(choice, "burden_cost", 0.0)),
                )
            )
        if getattr(choice, "name", "") in COMBO_PRIORITY_TRICKS:
            detector_hits.append(
                build_detector_hit(
                    "hide_combo_piece",
                    kind="preference",
                    severity=0.68,
                    confidence=0.76,
                    reason="A combo-priority trick was hidden to preserve future sequencing value.",
                    tags=("hidden_trick", "combo", choice.name),
                    score_delta=float(score_map.get(choice.name, 0.0)),
                )
            )
        if bool(getattr(choice, "is_anytime", False)):
            detector_hits.append(
                build_detector_hit(
                    "hide_anytime_flex",
                    kind="preference",
                    severity=0.42,
                    confidence=0.7,
                    reason="An anytime trick was hidden to preserve flexible reaction timing.",
                    tags=("hidden_trick", "anytime", choice.name),
                )
            )
    return DecisionTrace(
        decision_type="hidden_trick",
        features={
            "actor_name": actor_name,
            "hand": [
                {
                    "name": getattr(card, "name", str(card)),
                    "is_burden": bool(getattr(card, "is_burden", False)),
                    "burden_cost": int(getattr(card, "burden_cost", 0) or 0),
                    "is_anytime": bool(getattr(card, "is_anytime", False)),
                }
                for card in hand
            ],
            "score_map": dict(score_map),
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(),
        final_choice=None if choice is None else {"name": choice.name},
    )


def _build_trick_reward_trace(
    *,
    choices: list[Any],
    choice_run: Any,
    generic_survival_score: float,
    survival_urgency: float,
) -> DecisionTrace:
    detector_hits = []
    chosen = getattr(choice_run, "choice", None)
    score_map = dict((choice_run.debug_payload or {}).get("scores", {}) or {})
    top_score = max(score_map.values(), default=0.0)
    if chosen is not None:
        if any(bool(getattr(card, "is_burden", False)) for card in choices) and not bool(getattr(chosen, "is_burden", False)):
            detector_hits.append(
                build_detector_hit(
                    "avoid_reward_burden",
                    kind="guard",
                    severity=0.82,
                    confidence=0.86,
                    reason="The reward picker avoided taking a burden card when a safer trick reward existed.",
                    tags=("trick_reward", chosen.name),
                )
            )
        if top_score >= 3.0:
            detector_hits.append(
                build_detector_hit(
                    "high_value_trick_reward",
                    kind="advantage",
                    severity=min(1.0, float(top_score) / 4.0),
                    confidence=0.8,
                    reason="The chosen reward came from a clearly strong trick reward slot.",
                    tags=("trick_reward", chosen.name),
                    score_delta=float(score_map.get(chosen.name, 0.0)),
                )
            )
        if survival_urgency >= 1.0:
            detector_hits.append(
                build_detector_hit(
                    "survival_safe_reward_pick",
                    kind="preference",
                    severity=min(1.0, survival_urgency / 2.0),
                    confidence=0.75,
                    reason="Reward choice was evaluated under elevated survival pressure.",
                    tags=("trick_reward", chosen.name),
                )
            )
    return DecisionTrace(
        decision_type="trick_reward",
        features={
            "choices": [getattr(card, "name", str(card)) for card in choices],
            "score_map": score_map,
            "generic_survival_score": generic_survival_score,
            "survival_urgency": survival_urgency,
        },
        detector_hits=tuple(detector_hits),
        effect_adjustments=(
            {"kind": "top_score", "value": round(float(top_score), 3)},
        ),
        final_choice=None if chosen is None else {"name": chosen.name},
    )


def choose_movement_runtime(policy: Any, state: Any, player: Any):
    from ai_policy import MovementDecision

    board_len = len(state.board)
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    f_ctx = policy._f_progress_context(state, player)
    intent = policy._current_player_intent(state, player, player.current_character)
    token_profile = policy._profile_from_mode() == "token_opt"

    def _move_bonus(pos: int) -> float:
        bonus = 0.0
        revisit_gap = (pos - player.position) % board_len
        bonus += policy._common_token_place_bonus(state, player, pos, revisit_gap)
        if token_profile and state.tile_owner[pos] == player.player_id:
            bonus += 1.4 + 0.15 * state.tile_coins[pos]
        if token_profile and state.board[pos] in {CellKind.F1, CellKind.F2}:
            bonus += max(0.0, 0.35 * float(f_ctx["land_f_value"]))
        return bonus

    def _eval_move(pos: int, move_total: int, *, use_cards: bool = False, card_count: int = 0) -> float:
        predicted_cost = policy._predict_tile_landing_cost(state, player, pos)
        if use_cards and predicted_cost > 0.0 and not policy._is_action_survivable(
            state,
            player,
            immediate_cost=predicted_cost,
            survival_ctx=survival_ctx,
            buffer=0.5 * card_count,
        ):
            return -10**8
        projected_cash = policy._project_end_turn_cash(
            state,
            player,
            immediate_cost=predicted_cost,
            crosses_start=(player.position + move_total >= len(state.board)),
        )
        movement_block = policy._movement_survival_hard_block_reason(
            state,
            player,
            pos,
            survival_ctx,
            projected_cash=projected_cash,
        )
        if movement_block is not None:
            return -10**8 if use_cards else -10**6
        score = policy._landing_score(state, player, pos)
        score += _move_bonus(pos)
        score += policy._movement_survival_adjustment(
            state,
            player,
            pos,
            move_total,
            survival_ctx,
            projected_cash=projected_cash,
        )
        score += policy._f_move_adjustment(
            state,
            player,
            pos,
            move_total,
            survival_ctx,
            f_ctx,
            use_cards=use_cards,
            card_count=card_count,
        )
        score += apply_movement_intent_adjustment(
            current_character=player.current_character,
            rounds_completed=int(getattr(state, "rounds_completed", getattr(state, "round_index", 0))),
            cell_kind=state.board[pos],
            owner=state.tile_owner[pos],
            crosses_start=(player.position + move_total >= len(state.board)),
            use_cards=use_cards,
            card_count=card_count,
            intent=intent,
        )
        if use_cards and predicted_cost > 0.0 and not policy._is_action_survivable(
            state,
            player,
            immediate_cost=predicted_cost,
            survival_ctx=survival_ctx,
            buffer=0.0,
        ):
            score -= 8.0
        return score

    base_scores: list[float] = []
    for d1 in range(1, 7):
        for d2 in range(1, 7):
            move_total = d1 + d2
            pos = (player.position + move_total) % board_len
            base_scores.append(_eval_move(pos, move_total, use_cards=False, card_count=0))
    avg_no_cards = sum(base_scores) / len(base_scores)
    remaining_cards = tuple(policy._remaining_cards(player))

    resolution = resolve_movement_choice(
        avg_no_cards=avg_no_cards,
        remaining_cards=remaining_cards,
        single_card_scorer=lambda card_value, die_roll: _eval_move(
            (player.position + card_value + die_roll) % board_len,
            card_value + die_roll,
            use_cards=True,
            card_count=1,
        ),
        double_card_scorer=lambda first, second: _eval_move(
            (player.position + first + second) % board_len,
            first + second,
            use_cards=True,
            card_count=2,
        ),
        leader_trigger_value=lambda best_outcome, avg_score: (
            0.40 if bool(f_ctx["is_leader"]) and best_outcome >= avg_score + 6.0 else 0.0
        ),
    )
    policy._set_debug(
        "movement_decision",
        player.player_id,
        {
            "decision": {
                "use_cards": resolution.use_cards,
                "card_values": list(resolution.card_values),
                "score": round(float(resolution.score), 3),
                "avg_no_cards": round(float(resolution.avg_no_cards), 3),
            },
            "trace": build_decision_trace_payload(
                _build_movement_trace(
                    resolution=resolution,
                    intent=intent,
                    f_ctx=f_ctx,
                    remaining_cards=remaining_cards,
                )
            ),
        },
    )
    return MovementDecision(resolution.use_cards, resolution.card_values)


def choose_trick_to_use_runtime(policy: Any, state: Any, player: Any, hand: list[Any]) -> Any:
    supported = {
        "?ê¹…Ðª ?ì„ì­›åª›Â€": 1.8,
        "å«„ë‹¿ì»¯ å¯ƒÂ€ï§ž?": 1.2,
        "?ê³•?æ²…?": 1.4,
        "è‡¾ëŒ€ì¦º ï§ì•¹ì ™": 1.6,
        "?ì¢Žì“½??": 1.0,
        "åª›Â€è¸°ì‡±ìŠ« éºê¾¨â”éºë‰ë¸ž": 0.9,
        "æ´¹ë±€ë––??éºê¾¨â”éºë‰ë¸ž": 1.2,
        "ï§ëˆë–¦è«›?": 1.4,
        "?ëš­í€¬??": 1.1,
        "?ëš¯ì …??": 1.3,
        "?Ñ‰í“£ç”±Ñˆë¦°": 1.2,
        "æ¹²ëŒì˜£åª›?è­°ê³—ê½¦": 1.3,
        "è‡¾ëŒë¿­???ì¢ŠÐª": 1.0,
        "?ê¾©? ?ãƒªë¦°": 1.1,
        "è¸°ëˆì‘Š??": 0.8,
        "?ë¨¯ë’¯???ë¨¯ì‚¤??": 0.9,
        "æ´¹ë°¸ë£„???ë¨¯ë’¯???ë¨¯ì‚¤??": 1.5,
        "æ€¨ì‡±ëƒ½": 0.8,
        "?Â€??": 0.3,
        "?ëŒ€ì›»!": 0.7,
        "?ê¾©ï¼œ ???ë¶¾ã‰ ?ì’•ì¤ˆ": 1.0,
        "å«„ê³•????ê³•í…‹": 1.3,
        "è‡¾ë‹¿êµ…??ï§ž?": -0.6,
        "åª›Â€è¸°ì‡±ìŠ« ï§ž?": -0.3,
    }
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    decisive_ctx = policy._trick_decisive_context(state, player, survival_ctx)
    intent = policy._current_player_intent(state, player, player.current_character)

    def score(card: Any) -> float:
        immediate_cost = policy._predict_trick_cash_cost(card)
        if immediate_cost > 0.0 and not policy._is_action_survivable(
            state,
            player,
            immediate_cost=immediate_cost,
            survival_ctx=survival_ctx,
            buffer=0.5,
        ):
            return -999.0
        if immediate_cost > 0.0:
            post_cash = float(player.cash) - float(immediate_cost)
            hard_reason = policy._survival_hard_guard_reason(state, player, survival_ctx, post_action_cash=post_cash)
            if hard_reason is not None and float(decisive_ctx.get("strategic_mode", 0.0)) < 1.0:
                return -998.0
        value = supported.get(card.name, -99.0)
        if card.name == "è‡¾ëŒ€ì¦º ï§ì•¹ì ™" and player.cash >= 3:
            value += 0.6
        if card.name == "æ€¨ì‡±ëƒ½" and player.cash >= 2:
            value += 0.4
        if card.name == "?Â€??":
            value += 0.2 if player.cash < 6 else -0.5
        if card.name == "?Ñ‰í“£ç”±Ñˆë¦°":
            value += 0.4 if any(
                state.tile_owner[i] not in {None, player.player_id}
                for i in range(len(state.board))
                if state.tile_at(i).purchase_cost is not None
            ) else -1.0
        if card.name == "æ¹²ëŒì˜£åª›?è­°ê³—ê½¦":
            value += 0.5 if player.tiles_owned > 0 else -1.0
        if card.name == "è‡¾ëŒë¿­???ì¢ŠÐª":
            value += 0.4 if player.tiles_owned > 0 and any(
                own is not None and own != player.player_id for own in state.tile_owner
            ) else -1.0
        if card.name in {"è‡¾ë‹¿êµ…??ï§ž?", "åª›Â€è¸°ì‡±ìŠ« ï§ž?"}:
            value = -1.0
        value += policy._trick_survival_adjustment(state, player, card, survival_ctx)
        own_burdens = float(survival_ctx.get("own_burdens", 0.0))
        next_neg = float(survival_ctx.get("next_draw_negative_cleanup_prob", 0.0))
        two_neg = float(survival_ctx.get("two_draw_negative_cleanup_prob", 0.0))
        if own_burdens >= 2.0 and (next_neg >= 0.10 or two_neg >= 0.22):
            if card.name not in {"å«„ë‹¿ì»¯ å¯ƒÂ€ï§ž?", "?ê³•?æ²…?", "?ëš­í€¬??", "?Â€??", "?ê¾©? ?ãƒªë¦°", "?ì¢Žì“½??"}:
                value -= 1.8
            if immediate_cost > 0.0:
                value -= 1.1
        elif own_burdens >= 1.0 and next_neg >= 0.10 and immediate_cost > 0.0:
            value -= 0.8
        value += policy._trick_decisive_adjustment(state, player, card, survival_ctx, decisive_ctx)
        value += policy._trick_preserve_adjustment(state, player, card, hand, survival_ctx, decisive_ctx)
        value += apply_trick_preserve_rules(
            card_name=card.name,
            actor_name=player.current_character,
            hand_names={c.name for c in hand},
            rounds_completed=int(getattr(state, "round_index", 0)),
            strategic_mode=float(decisive_ctx.get("strategic_mode", 0.0)),
            intent=intent,
            survival_urgency=float(survival_ctx.get("survival_urgency", 0.0)),
            cleanup_cash_gap=float(survival_ctx.get("cleanup_cash_gap", 0.0)),
            has_relic_collector_window=False,
            has_help_run_window=False,
            has_neojeol_chain_window=False,
            short_range_frontier_is_better=False,
        )
        if policy._profile_from_mode() == "v3_gpt" and card.name in {"?ê¹…Ðª ?ì„ì­›åª›Â€", "?ê¾©? ?ãƒªë¦°"}:
            return -999.0
        return value

    resolution = resolve_trick_use_choice(hand, scorer=score)
    policy._set_debug(
        "trick_use",
        player.player_id,
        _payload_with_trace(
            build_trick_use_debug_payload(
                score_map=resolution.score_map,
                chosen_name=None if resolution.choice is None else resolution.choice.name,
                generic_survival_score=survival_ctx["generic_survival_score"],
                survival_urgency=survival_ctx["survival_urgency"],
                strategic_mode=decisive_ctx["strategic_mode"],
            ),
            _build_trick_use_trace(
                hand=list(hand),
                resolution=resolution,
                generic_survival_score=float(survival_ctx["generic_survival_score"]),
                survival_urgency=float(survival_ctx["survival_urgency"]),
                strategic_mode=float(decisive_ctx["strategic_mode"]),
                intent=intent,
            ),
        ),
    )
    return resolution.choice


def choose_mark_target_runtime(policy: Any, state: Any, player: Any, actor_name: str) -> Any:
    legal_targets = policy._allowed_mark_targets(state, player)
    candidates = filter_public_mark_candidates(
        actor_name,
        policy._public_mark_guess_candidates(state, player),
        state.active_by_card.values(),
    )
    choice_run = run_public_mark_choice(
        candidates,
        policy=policy.character_policy_mode,
        actor_name=actor_name,
        legal_target_count=len(legal_targets),
        is_random_mode=policy._is_random_mode(),
        scorer=lambda target_name: policy._public_target_name_score_breakdown(
            state,
            player,
            actor_name,
            target_name,
        ),
        distribution_builder=policy._mark_guess_distribution,
        chooser=policy._weighted_choice,
        random_chooser=policy._choice,
    )
    policy._set_debug(
        "mark_target",
        player.player_id,
        _payload_with_trace(
            choice_run.debug_payload,
            _build_mark_target_trace(
                actor_name=actor_name,
                legal_target_count=len(legal_targets),
                debug_payload=choice_run.debug_payload,
                choice=choice_run.choice,
            ),
        ),
    )
    return choice_run.choice


def choose_hidden_trick_card_runtime(policy: Any, state: Any, player: Any, hand: list[Any]) -> Any:
    choice_run = resolve_hidden_trick_choice_run(hand, actor_name=player.current_character)
    policy._set_debug(
        "hide_trick",
        player.player_id,
        _payload_with_trace(
            choice_run.debug_payload,
            _build_hidden_trick_trace(
                actor_name=player.current_character,
                hand=list(hand),
                choice=choice_run.choice,
                score_map=dict(choice_run.debug_payload.get("scores", {})),
            ),
        ),
    )
    return choice_run.choice


def choose_draft_card_runtime(policy: Any, state: Any, player: Any, offered_cards: list[int]) -> int:
    if policy._is_random_mode():
        choice = policy._choice(offered_cards)
        debug_payload = build_uniform_random_character_choice_debug_payload(
            policy_name=policy.character_policy_mode,
            offered_cards=offered_cards,
            candidate_labels=[str(card) for card in offered_cards],
            chosen_key=choice,
            chosen_name=state.active_by_card[choice],
        )
        policy._set_debug(
            "draft_card",
            player.player_id,
            _payload_with_trace(
                debug_payload,
                _build_character_choice_trace(
                    decision_type="draft_character",
                    candidate_scores=dict(debug_payload["candidate_scores"]),
                    candidate_reasons={str(card): ["uniform_random"] for card in offered_cards},
                    hard_blocked_map={},
                    candidate_characters={str(card_no): state.active_by_card[card_no] for card_no in offered_cards},
                    offered_cards=offered_cards,
                    generic_survival_score=0.0,
                    survival_urgency=0.0,
                    survival_first=False,
                    survival_weight_multiplier=1.0,
                    marker_bonus_by_name={},
                    chosen_key=choice,
                    chosen_name=state.active_by_card[choice],
                ),
            ),
        )
        return choice

    survival_ctx, survival_orchestrator = policy._build_survival_orchestrator(state, player, player.current_character)
    marker_bonus = policy._distress_marker_bonus(state, player, [state.active_by_card[c] for c in offered_cards])
    choice_policy = build_named_character_choice_policy(
        resolve_name=lambda card_no: state.active_by_card[card_no],
        base_breakdown=lambda name: (
            policy._character_score_breakdown_v2(state, player, name)
            if policy._is_v2_mode()
            else policy._character_score_breakdown(state, player, name)
        ),
        survival_policy_advice=lambda name: policy._survival_policy_character_advice(state, player, name, survival_orchestrator),
        survival_adjustment=lambda name: policy._character_survival_adjustment(state, player, name, survival_ctx),
        marker_bonus_by_name=marker_bonus,
        weighted_marker_names={
            name
            for name in marker_bonus
            if (
                is_low_cash_income_character(name)
                or is_low_cash_escape_character(name)
                or is_low_cash_controller_character(name)
            )
        },
        survival_first=survival_orchestrator.survival_first,
        weight_multiplier=survival_orchestrator.weight_multiplier,
    )
    run = run_named_character_choice_with_policy(
        offered_cards,
        policy=choice_policy,
        label_for_key=lambda card_no: str(card_no),
        tiebreak_desc=False,
    )
    debug_payload = build_character_choice_debug_payload(
        policy_name=policy.character_policy_mode,
        offered_cards=offered_cards,
        debug_summary=run.debug_summary,
        generic_survival_score=survival_ctx["generic_survival_score"],
        survival_urgency=survival_ctx["survival_urgency"],
        survival_first=survival_orchestrator.survival_first,
        survival_weight_multiplier=survival_orchestrator.weight_multiplier,
        chosen_key=run.choice,
        chosen_name=state.active_by_card[run.choice],
        reasons_for_choice=list(run.evaluation.reasons[run.choice]),
        hard_blocked_map={
            state.active_by_card[card_no]: run.evaluation.hard_block_details[card_no]
            for card_no in run.evaluation.hard_blocked_keys
        },
        character_names_by_key={str(card_no): state.active_by_card[card_no] for card_no in offered_cards},
    )
    policy._set_debug(
        "draft_card",
        player.player_id,
        _payload_with_trace(
            debug_payload,
            _build_character_choice_trace(
                decision_type="draft_character",
                candidate_scores=run.debug_summary.score_map,
                candidate_reasons=run.debug_summary.reason_map,
                hard_blocked_map={
                    state.active_by_card[card_no]: run.evaluation.hard_block_details[card_no]
                    for card_no in run.evaluation.hard_blocked_keys
                },
                candidate_characters={str(card_no): state.active_by_card[card_no] for card_no in offered_cards},
                offered_cards=offered_cards,
                generic_survival_score=float(survival_ctx["generic_survival_score"]),
                survival_urgency=float(survival_ctx["survival_urgency"]),
                survival_first=bool(survival_orchestrator.survival_first),
                survival_weight_multiplier=float(survival_orchestrator.weight_multiplier),
                marker_bonus_by_name={str(name): float(bonus) for name, bonus in marker_bonus.items()},
                chosen_key=run.choice,
                chosen_name=state.active_by_card[run.choice],
            ),
        ),
    )
    return run.choice


def choose_final_character_runtime(policy: Any, state: Any, player: Any, card_choices: list[int]) -> str:
    options = [state.active_by_card[c] for c in card_choices]
    if policy._is_random_mode():
        choice = policy._choice(options)
        debug_payload = build_uniform_random_character_choice_debug_payload(
            policy_name=policy.character_policy_mode,
            offered_cards=card_choices,
            candidate_labels=list(options),
            chosen_key=choice,
            chosen_name=choice,
        )
        policy._set_debug(
            "final_character",
            player.player_id,
            _payload_with_trace(
                debug_payload,
                _build_character_choice_trace(
                    decision_type="final_character",
                    candidate_scores=dict(debug_payload["candidate_scores"]),
                    candidate_reasons={name: ["uniform_random"] for name in options},
                    hard_blocked_map={},
                    candidate_characters={name: name for name in options},
                    offered_cards=card_choices,
                    generic_survival_score=0.0,
                    survival_urgency=0.0,
                    survival_first=False,
                    survival_weight_multiplier=1.0,
                    marker_bonus_by_name={},
                    chosen_key=choice,
                    chosen_name=choice,
                ),
            ),
        )
        return choice

    survival_ctx, survival_orchestrator = policy._build_survival_orchestrator(state, player, player.current_character)
    marker_bonus = policy._distress_marker_bonus(state, player, options)
    choice_policy = build_named_character_choice_policy(
        resolve_name=lambda name: name,
        base_breakdown=lambda name: (
            policy._character_score_breakdown_v2(state, player, name)
            if policy._is_v2_mode()
            else policy._character_score_breakdown(state, player, name)
        ),
        survival_policy_advice=lambda name: policy._survival_policy_character_advice(state, player, name, survival_orchestrator),
        survival_adjustment=lambda name: policy._character_survival_adjustment(state, player, name, survival_ctx),
        marker_bonus_by_name=marker_bonus,
        weighted_marker_names={
            name
            for name in marker_bonus
            if (
                is_low_cash_income_character(name)
                or is_low_cash_escape_character(name)
                or is_low_cash_controller_character(name)
            )
        },
        survival_first=survival_orchestrator.survival_first,
        weight_multiplier=survival_orchestrator.weight_multiplier,
    )
    run = run_named_character_choice_with_policy(
        options,
        policy=choice_policy,
        label_for_key=lambda name: name,
        tiebreak_desc=True,
    )
    policy._remember_player_intent(state, player, run.choice, reason="choose_final_character")
    debug_payload = build_character_choice_debug_payload(
        policy_name=policy.character_policy_mode,
        offered_cards=card_choices,
        debug_summary=run.debug_summary,
        generic_survival_score=survival_ctx["generic_survival_score"],
        survival_urgency=survival_ctx["survival_urgency"],
        survival_first=survival_orchestrator.survival_first,
        survival_weight_multiplier=survival_orchestrator.weight_multiplier,
        chosen_key=run.choice,
        chosen_name=run.choice,
        reasons_for_choice=list(run.evaluation.reasons[run.choice]),
        hard_blocked_map={
            name: run.evaluation.hard_block_details[name]
            for name in run.evaluation.hard_blocked_keys
        },
    )
    policy._set_debug(
        "final_character",
        player.player_id,
        _payload_with_trace(
            debug_payload,
            _build_character_choice_trace(
                decision_type="final_character",
                candidate_scores=run.debug_summary.score_map,
                candidate_reasons=run.debug_summary.reason_map,
                hard_blocked_map={
                    name: run.evaluation.hard_block_details[name]
                    for name in run.evaluation.hard_blocked_keys
                },
                candidate_characters={name: name for name in options},
                offered_cards=card_choices,
                generic_survival_score=float(survival_ctx["generic_survival_score"]),
                survival_urgency=float(survival_ctx["survival_urgency"]),
                survival_first=bool(survival_orchestrator.survival_first),
                survival_weight_multiplier=float(survival_orchestrator.weight_multiplier),
                marker_bonus_by_name={str(name): float(bonus) for name, bonus in marker_bonus.items()},
                chosen_key=run.choice,
                chosen_name=run.choice,
            ),
        ),
    )
    return run.choice


def choose_specific_trick_reward_runtime(policy: Any, state: Any, player: Any, choices: list[Any]) -> Any:
    if not choices:
        return None
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)

    def score(card: Any) -> float:
        if getattr(card, "is_burden", False):
            return -10.0
        immediate_cost = policy._predict_trick_cash_cost(card)
        if immediate_cost > 0.0 and not policy._is_action_survivable(
            state,
            player,
            immediate_cost=immediate_cost,
            survival_ctx=survival_ctx,
            buffer=0.5,
        ):
            return -999.0
        base = {
            "?ì–œ?ï§?ç­Œì•¹ë¹˜??": 4.0,
            "?æ€¨?äº¦?": 3.4,
            "?æºë¦???ë¥ì¶¿æ¶ìŽ›Â€": 3.0,
            "æ¤°ê¾¨ë–¯è€Œ?é‡ŽêºœÂ€ç­Œ?": 2.5,
            "åŸŸë°¸ê°­çŒ·???ç™’?ë®£???ç™’?ê¶Ž??": 2.0,
        }.get(card.name, 1.0)
        return base + policy._trick_survival_adjustment(state, player, card, survival_ctx)

    choice_run = resolve_trick_reward_choice_run(
        choices=choices,
        scorer=score,
        generic_survival_score=survival_ctx["generic_survival_score"],
        survival_urgency=survival_ctx["survival_urgency"],
    )
    policy._set_debug(
        "trick_reward",
        player.player_id,
        _payload_with_trace(
            choice_run.debug_payload,
            _build_trick_reward_trace(
                choices=list(choices),
                choice_run=choice_run,
                generic_survival_score=float(survival_ctx["generic_survival_score"]),
                survival_urgency=float(survival_ctx["survival_urgency"]),
            ),
        ),
    )
    return choice_run.choice


def choose_coin_placement_tile_runtime(policy: Any, state: Any, player: Any) -> Any:
    candidates = [
        i
        for i in player.visited_owned_tile_indices
        if state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
    ]
    if not candidates:
        policy._set_debug(
            "coin_placement",
            player.player_id,
            _payload_with_trace(
                {
                    "policy": policy.character_policy_mode,
                    "candidates": [],
                    "chosen_tile": None,
                    "reasons": ["no_placeable_tiles"],
                },
                DecisionTrace(
                    decision_type="coin_placement",
                    features={
                        "player_position": int(player.position),
                        "max_coins_per_tile": int(state.config.rules.token.max_coins_per_tile),
                        "token_opt_profile": policy._profile_from_mode() in {"token_opt", "v3_gpt"},
                        "candidates": [],
                    },
                    detector_hits=(
                        build_detector_hit(
                            "no_placeable_tiles",
                            kind="hard_veto",
                            severity=1.0,
                            confidence=1.0,
                            reason="No eligible owned tiles could receive a score coin.",
                            tags=("coin_placement",),
                        ),
                    ),
                    effect_adjustments=(),
                    final_choice=None,
                ),
            ),
        )
        return None
    choice = choose_coin_placement_tile_id(
        candidates,
        tile_coins=state.tile_coins,
        board=state.board,
        player_position=player.position,
        max_coins_per_tile=state.config.rules.token.max_coins_per_tile,
        token_opt_profile=policy._profile_from_mode() in {"token_opt", "v3_gpt"},
    )
    policy._set_debug(
        "coin_placement",
        player.player_id,
        _payload_with_trace(
            {
                "policy": policy.character_policy_mode,
                "candidates": list(candidates),
                "chosen_tile": choice,
            },
            _build_coin_placement_trace(
                candidates=list(candidates),
                tile_coins=list(state.tile_coins),
                board=list(state.board),
                player_position=int(player.position),
                max_coins_per_tile=int(state.config.rules.token.max_coins_per_tile),
                token_opt_profile=policy._profile_from_mode() in {"token_opt", "v3_gpt"},
                choice=choice,
            ),
        ),
    )
    return choice


def choose_active_flip_card_runtime(policy: Any, state: Any, player: Any, flippable_cards: list[int]) -> Any:
    if not flippable_cards:
        return None
    if policy._is_random_mode():
        resolution = resolve_random_active_flip_choice(
            flippable_cards,
            policy=policy.character_policy_mode,
            chooser=policy._choice,
        )
        policy._set_debug(
            "marker_flip",
            player.player_id,
            _payload_with_trace(
                resolution.debug_payload,
                _build_active_flip_trace(
                    flippable_cards=flippable_cards,
                    state=state,
                    scored={card_no: 0.0 for card_no in flippable_cards},
                    reasons={card_no: ["uniform_random"] for card_no in flippable_cards},
                    choice=resolution.choice,
                    generic_survival_score=0.0,
                    money_distress=0.0,
                    controller_need=0.0,
                ),
            ),
        )
        return resolution.choice

    scored = {}
    reasons = {}
    advanced_marker_mode = policy._is_v2_mode() or policy._profile_from_mode() == "v3_gpt"
    denial_snapshot = policy._leader_denial_snapshot(state, player) if advanced_marker_mode else None
    marker_plan = policy._leader_marker_flip_plan(
        state,
        player,
        denial_snapshot.get("top_threat") if denial_snapshot else None,
    ) if advanced_marker_mode else None
    opportunities = marker_plan["opportunities"] if marker_plan else {}
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    controller_need = float(survival_ctx.get("controller_need", 0.0))
    money_distress = float(survival_ctx.get("money_distress", 0.0))
    own_burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))

    for card_no in flippable_cards:
        current = state.active_by_card[card_no]
        a, b = CARD_TO_NAMES[card_no]
        flipped = b if current == a else a
        if advanced_marker_mode:
            current_score, _ = policy._character_score_breakdown_v2(state, player, current)
            flipped_score, flipped_reasons = policy._character_score_breakdown_v2(state, player, flipped)
            deny = 0.0
            for op in policy._alive_enemies(state, player):
                tags = policy._predicted_opponent_archetypes(state, player, op)
                if flipped in {"?ë¨­ì»¼", "?ê³—ìŸ»", "åª›ì•¹ï¼œ", "ä»¥ë¬â„“è¢?", "å«„ëŒê½•?ë‚†ì˜„"} and ("expansion" in tags or "geo" in tags or "cash_rich" in tags):
                    deny += 0.6
                if current in {"ä»¥ë¬â„“è¢?", "å«„ëŒê½•?ë‚†ì˜„", "åª›ì•¹ï¼œ", "?ë¨­ì»¼"} and ("expansion" in tags or "geo" in tags):
                    deny += 0.6
            if denial_snapshot and denial_snapshot["emergency"] > 0.0:
                if flipped in {"?ë¨­ì»¼", "?ê³—ìŸ»", "ç•°ë¶¾ë‚è¢?", "?Ñˆë¦°è¢?", "è«›ëº¤ë‹”", "ï§ëš¯ë–Š", "?ëŒê¶—"}:
                    deny += 0.9 + 0.25 * float(denial_snapshot["emergency"])
                if flipped in {"æ´ë¨®â” ?ê³ŒëŽ„æ„¿Â€", "æ´ë¨®â” åª›ë¨®ë£†æ„¿Â€"}:
                    deny += 0.8 + 0.3 * float(denial_snapshot["emergency"])
                if current in {"ä»¥ë¬â„“è¢?", "å«„ëŒê½•?ë‚†ì˜„", "åª›ì•¹ï¼œ", "?ëš®ì»»è¢?"} and denial_snapshot["near_end"]:
                    deny += 0.7
            card_plan = opportunities.get(card_no, {})
            counter_delta = float(card_plan.get("score", 0.0))
            if counter_delta != 0.0:
                deny += 1.15 * counter_delta
                flipped_need = float(card_plan.get("flipped_need", 0.0))
                current_need = float(card_plan.get("current_need", 0.0))
                if current_need > flipped_need:
                    flipped_reasons = [f"counter_leader_needed_face={current_need - flipped_need:.2f}", *flipped_reasons]
                elif flipped_need > current_need:
                    flipped_reasons = [f"avoid_feeding_leader={flipped_need - current_need:.2f}", *flipped_reasons]
            if controller_need > 0.0 or money_distress > 0.0:
                if is_active_money_drain_character(current) and not is_active_money_drain_character(flipped):
                    relief = 0.95 + 0.75 * controller_need + 0.35 * money_distress
                    if current == "ï§ëš¯ë–Š" and own_burden_cost > 0.0:
                        relief += 0.25 * own_burden_cost
                    deny += relief
                    flipped_reasons = [f"money_relief_flip={relief:.2f}", *flipped_reasons]
                elif is_active_money_drain_character(flipped) and not is_active_money_drain_character(current):
                    deny -= 0.80 + 0.55 * controller_need + 0.25 * money_distress
                    flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
            scored[card_no] = (flipped_score - current_score) + deny
            reasons[card_no] = [f"flip_to={flipped}", f"deny={deny:.1f}", *flipped_reasons]
        else:
            current_score, _ = policy._character_score_breakdown(state, player, current)
            flipped_score, flipped_reasons = policy._character_score_breakdown(state, player, flipped)
            score = flipped_score - current_score
            if (controller_need > 0.0 or money_distress > 0.0) and is_active_money_drain_character(current) and not is_active_money_drain_character(flipped):
                score += 0.90 + 0.70 * controller_need + 0.30 * money_distress
                flipped_reasons = ["money_relief_flip", *flipped_reasons]
            elif (controller_need > 0.0 or money_distress > 0.0) and is_active_money_drain_character(flipped) and not is_active_money_drain_character(current):
                score -= 0.75 + 0.50 * controller_need + 0.20 * money_distress
                flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
            scored[card_no] = score
            reasons[card_no] = [f"flip_to={flipped}", *flipped_reasons]

    resolution = resolve_scored_active_flip_choice(
        flippable_cards,
        scored=scored,
        reasons=reasons,
        policy=policy.character_policy_mode,
        chosen_to_resolver=lambda choice: (
            CARD_TO_NAMES[choice][1]
            if state.active_by_card[choice] == CARD_TO_NAMES[choice][0]
            else CARD_TO_NAMES[choice][0]
        ),
        generic_survival_score=survival_ctx["generic_survival_score"],
        money_distress=money_distress,
        controller_need=controller_need,
    )
    policy._set_debug(
        "marker_flip",
        player.player_id,
        _payload_with_trace(
            resolution.debug_payload,
            _build_active_flip_trace(
                flippable_cards=flippable_cards,
                state=state,
                scored=scored,
                reasons=reasons,
                choice=resolution.choice,
                generic_survival_score=float(survival_ctx["generic_survival_score"]),
                money_distress=money_distress,
                controller_need=controller_need,
            ),
        ),
    )
    return resolution.choice


def choose_burden_exchange_on_supply_runtime(policy: Any, state: Any, player: Any, card: Any) -> bool:
    if player.cash < card.burden_cost:
        decision = False
        trace = _build_burden_exchange_trace(
            card_name=str(card.name),
            burden_cost=float(card.burden_cost),
            cash_before=float(player.cash),
            remaining_cash=float(player.cash - card.burden_cost),
            reserve=0.0,
            target_floor=0.0,
            hard_reason=None,
            decision=decision,
            escape_guard=False,
        )
        policy._set_debug(
            "burden_exchange",
            player.player_id,
            _payload_with_trace(
                {
                    "policy": policy.character_policy_mode,
                    "card_name": card.name,
                    "burden_cost": card.burden_cost,
                    "decision": decision,
                    "reasons": ["insufficient_cash"],
                },
                trace,
            ),
        )
        return decision
    if policy._is_random_mode():
        decision = True
        trace = _build_burden_exchange_trace(
            card_name=str(card.name),
            burden_cost=float(card.burden_cost),
            cash_before=float(player.cash),
            remaining_cash=float(player.cash - card.burden_cost),
            reserve=0.0,
            target_floor=0.0,
            hard_reason=None,
            decision=decision,
            escape_guard=False,
        )
        policy._set_debug(
            "burden_exchange",
            player.player_id,
            _payload_with_trace(
                {
                    "policy": policy.character_policy_mode,
                    "card_name": card.name,
                    "burden_cost": card.burden_cost,
                    "decision": decision,
                    "reasons": ["uniform_random"],
                },
                trace,
            ),
        )
        return decision
    liquidity = policy._liquidity_risk_metrics(state, player, player.current_character)
    escape_guard = bool(policy._should_seek_escape_package(state, player))
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    remaining_cash = player.cash - card.burden_cost
    reserve = float(liquidity["reserve"])
    latent_cleanup_cost = float(survival_ctx.get("latent_cleanup_cost", 0.0))
    expected_cleanup_cost = float(survival_ctx.get("expected_cleanup_cost", 0.0))
    downside_expected_cleanup_cost = float(survival_ctx.get("downside_expected_cleanup_cost", 0.0))
    target_floor = max(
        8.0,
        reserve + 0.90 * latent_cleanup_cost + 1.10 * expected_cleanup_cost + 0.95 * downside_expected_cleanup_cost,
    )
    if float(survival_ctx.get("own_burdens", 0.0)) >= 1.0 and float(survival_ctx.get("remaining_negative_cleanup_cards", 0.0)) > 0.0:
        target_floor = max(target_floor, reserve + downside_expected_cleanup_cost + 3.0)
    hard_reason = policy._survival_hard_guard_reason(state, player, survival_ctx, post_action_cash=remaining_cash)
    decision_inputs = BurdenExchangeDecisionInputs(
        remaining_cash=float(remaining_cash),
        reserve=float(reserve),
        target_floor=float(target_floor),
        hard_reason=hard_reason,
    )
    decision = False if escape_guard else should_exchange_burden_on_supply(decision_inputs)
    reasons = []
    if escape_guard:
        reasons.append("escape_package_guard")
    if remaining_cash <= max(5.0, 0.80 * reserve):
        reasons.append("danger_cash_floor")
    if hard_reason is not None:
        reasons.append(f"survival_hard_guard:{hard_reason}")
    if decision:
        reasons.append("safe_exchange_window")
    if not reasons:
        reasons.append("below_target_floor")
    policy._set_debug(
        "burden_exchange",
        player.player_id,
        _payload_with_trace(
            {
                "policy": policy.character_policy_mode,
                "card_name": card.name,
                "burden_cost": card.burden_cost,
                "decision": decision,
                "remaining_cash": round(float(remaining_cash), 3),
                "target_floor": round(float(target_floor), 3),
                "reasons": reasons,
            },
            _build_burden_exchange_trace(
                card_name=str(card.name),
                burden_cost=float(card.burden_cost),
                cash_before=float(player.cash),
                remaining_cash=float(remaining_cash),
                reserve=float(reserve),
                target_floor=float(target_floor),
                hard_reason=hard_reason,
                decision=bool(decision),
                escape_guard=escape_guard,
            ),
        ),
    )
    return decision


def choose_doctrine_relief_target_runtime(policy: Any, state: Any, player: Any, candidates: list[Any]) -> Any:
    candidate_ids = [candidate.player_id for candidate in candidates]
    choice = choose_doctrine_relief_player_id(self_player_id=player.player_id, candidate_ids=candidate_ids)
    policy._set_debug(
        "doctrine_relief",
        player.player_id,
        _payload_with_trace(
            {
                "policy": policy.character_policy_mode,
                "candidate_ids": candidate_ids,
                "chosen_player_id": choice,
                "reasons": [
                    "no_candidates"
                    if choice is None
                    else ("self_relief_preference" if choice == player.player_id else "fallback_first_candidate")
                ],
            },
            _build_doctrine_relief_trace(
                self_player_id=int(player.player_id),
                candidate_ids=candidate_ids,
                choice=choice,
            ),
        ),
    )
    return choice


def choose_geo_bonus_runtime(policy: Any, state: Any, player: Any, actor_name: str) -> str:
    survival_ctx = policy._generic_survival_context(state, player, actor_name)
    f_ctx = policy._f_progress_context(state, player)
    money_distress = float(survival_ctx.get("money_distress", 0.0))
    two_turn_lethal = float(survival_ctx.get("two_turn_lethal_prob", 0.0))
    controller_need = float(survival_ctx.get("controller_need", 0.0))
    burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
    cleanup_cash_gap = float(survival_ctx.get("cleanup_cash_gap", 0.0))
    latent_cleanup_cost = float(survival_ctx.get("latent_cleanup_cost", 0.0))
    expected_cleanup_cost = float(survival_ctx.get("expected_cleanup_cost", 0.0))

    if policy._is_v2_mode():
        cross_start = policy._will_cross_start(state, player)
        land_f = policy._will_land_on_f(state, player)
        coin_score = (1.8 if is_gakju(actor_name) else 0.8) + 0.8 * cross_start
        if actor_name == CARD_TO_NAMES[7][1]:
            coin_score += 0.55 + 0.25 * policy._matchmaker_adjacent_value(state, player)
        elif actor_name == CARD_TO_NAMES[8][0]:
            coin_score += 0.70 + 0.40 * policy._builder_free_purchase_value(state, player)
        shard_score = (1.8 if (is_bandit(actor_name) or is_baksu(actor_name) or is_mansin(actor_name)) else 0.6) + max(
            0.0,
            0.7 * land_f * float(f_ctx["land_f_value"]),
        )
        if actor_name == CARD_TO_NAMES[7][1] and player.shards < 2:
            shard_score += 0.80
        if is_baksu(actor_name) and policy._failed_mark_fallback_metrics(player, 5)[0] > 0:
            shard_score += 0.35
        if is_mansin(actor_name) and policy._failed_mark_fallback_metrics(player, 7)[0] > 0:
            shard_score += 0.20
        cash_score = 0.5 + 0.25 * max(0, 9 - player.cash)
        cash_score += (
            1.75 * money_distress
            + 2.60 * two_turn_lethal
            + 0.55 * controller_need
            + 0.36 * burden_cost
            + 0.95 * cleanup_cash_gap
            + 0.55 * latent_cleanup_cost
            + 0.70 * expected_cleanup_cost
            + 0.35 * float(survival_ctx.get("downside_expected_cleanup_cost", 0.0))
        )
        if not bool(f_ctx["is_leader"]):
            cash_score += 0.55 + 0.35 * float(f_ctx["avoid_f_acceleration"])
            shard_score -= 0.45 + 0.25 * float(f_ctx["avoid_f_acceleration"])
        profile = policy._profile_from_mode()
        if profile == "aggressive":
            coin_score += 1.0
        elif profile == "avoid_control":
            cash_score += 0.7
        elif profile == "token_opt":
            coin_score += 2.2 + 0.8 * cross_start + 0.5 * land_f
            shard_score += 0.3

        geo_inputs = GeoBonusDecisionInputs(
            own_burdens=float(survival_ctx.get("own_burdens", 0.0)),
            next_neg=float(survival_ctx.get("next_draw_negative_cleanup_prob", 0.0)),
            two_neg=float(survival_ctx.get("two_draw_negative_cleanup_prob", 0.0)),
            cleanup_cash_gap=cleanup_cash_gap,
            downside_cleanup=float(survival_ctx.get("downside_expected_cleanup_cost", 0.0)),
            cash=float(player.cash),
            cash_score=float(cash_score),
            shard_score=float(shard_score),
            coin_score=float(coin_score),
        )
        choice = choose_geo_bonus_kind(geo_inputs)
        scores = {"cash": round(float(cash_score), 3), "shards": round(float(shard_score), 3), "coins": round(float(coin_score), 3)}
        features = {
            "mode": "v2",
            "own_burdens": geo_inputs.own_burdens,
            "next_neg": geo_inputs.next_neg,
            "two_neg": geo_inputs.two_neg,
            "cleanup_cash_gap": geo_inputs.cleanup_cash_gap,
            "downside_cleanup": geo_inputs.downside_cleanup,
            "cash": geo_inputs.cash,
            "cross_start": round(float(cross_start), 3),
            "land_f": round(float(land_f), 3),
            "is_leader": bool(f_ctx["is_leader"]),
            "avoid_f_acceleration": round(float(f_ctx["avoid_f_acceleration"]), 3),
        }
        policy._set_debug(
            "geo_bonus",
            player.player_id,
            _payload_with_trace(
                {
                    "policy": policy.character_policy_mode,
                    "candidate_scores": scores,
                    "chosen_bonus": choice,
                    "reasons": [f"preferred_{choice}"],
                },
                _build_geo_bonus_trace(actor_name=actor_name, features=features, scores=scores, choice=choice),
            ),
        )
        return choice

    if player.cash < 8 or money_distress >= 0.95 or two_turn_lethal >= 0.16 or not bool(f_ctx["is_leader"]):
        choice = "cash"
        reasons = ["cash_pressure"]
    elif is_bandit(actor_name) or is_baksu(actor_name) or is_mansin(actor_name):
        choice = "shards"
        reasons = ["shard_window"]
    else:
        choice = "coins"
        reasons = ["coin_engine_window"]
    scores = {
        "cash": round(2.0 + money_distress + two_turn_lethal + (0.5 if not bool(f_ctx["is_leader"]) else 0.0), 3),
        "shards": round(1.0 + (1.0 if (is_bandit(actor_name) or is_baksu(actor_name) or is_mansin(actor_name)) else 0.0), 3),
        "coins": round(1.0 + (0.5 if choice == "coins" else 0.0), 3),
    }
    features = {
        "mode": "basic",
        "own_burdens": float(survival_ctx.get("own_burdens", 0.0)),
        "next_neg": float(survival_ctx.get("next_draw_negative_cleanup_prob", 0.0)),
        "two_neg": float(survival_ctx.get("two_draw_negative_cleanup_prob", 0.0)),
        "cleanup_cash_gap": cleanup_cash_gap,
        "cash": float(player.cash),
        "money_distress": money_distress,
        "two_turn_lethal": two_turn_lethal,
        "is_leader": bool(f_ctx["is_leader"]),
    }
    policy._set_debug(
        "geo_bonus",
        player.player_id,
        _payload_with_trace(
            {
                "policy": policy.character_policy_mode,
                "candidate_scores": scores,
                "chosen_bonus": choice,
                "reasons": reasons,
            },
            _build_geo_bonus_trace(actor_name=actor_name, features=features, scores=scores, choice=choice),
        ),
    )
    return choice


def choose_lap_reward_runtime(policy: Any, state: Any, player: Any) -> Any:
    mode = policy._lap_mode_for_player(player.player_id)
    if mode == "cash_focus":
        return policy._lap_reward_bundle(state, 1.0, 0.01, 0.01, preferred="cash")
    if mode == "shard_focus":
        return policy._lap_reward_bundle(state, 0.01, 1.0, 0.01, preferred="shards")
    if mode == "coin_focus":
        return policy._lap_reward_bundle(state, 0.01, 0.01, 1.0, preferred="coins")

    placeable = any(
        state.tile_owner[i] == player.player_id
        and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        for i in player.visited_owned_tile_indices
    )
    buy_value = policy._expected_buy_value(state, player)
    cross_start = policy._will_cross_start(state, player)
    land_f = policy._will_land_on_f(state, player)
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    cleanup_strategy = policy._cleanup_strategy_context(survival_ctx, player)
    f_ctx = policy._f_progress_context(state, player)
    survival_cash_pressure = (
        survival_ctx["survival_urgency"] >= 1.0
        and (
            player.cash <= 4
            or survival_ctx["rent_pressure"] >= 1.2
            or survival_ctx["lethal_hit_prob"] > 0.0
            or survival_ctx["own_burden_cost"] > 0.0
            or survival_ctx["cleanup_pressure"] >= 2.0
        )
    )

    def _record_lap_reward_debug(
        *,
        decision: Any,
        cash_score: float,
        shard_score: float,
        coin_score: float,
        preferred: str | None,
        token_window_score: float = 0.0,
        rich_pool: float = 0.0,
        plan_ctx: Any | None = None,
    ) -> None:
        detector_hits = []
        if survival_cash_pressure:
            detector_hits.append(
                build_detector_hit(
                    "adv_cleanup_cash_pressure",
                    kind="advantage",
                    severity=0.85,
                    confidence=0.9,
                    reason="Cash is being prioritized because survival pressure is high.",
                    tags=("lap_reward", "survival"),
                    score_delta=1.0,
                )
            )
        if player.shards < 5 and decision.choice == "shards":
            detector_hits.append(
                build_detector_hit(
                    "adv_shard_checkpoint",
                    kind="advantage",
                    severity=0.8,
                    confidence=0.88,
                    reason="Shard reward advances an important checkpoint for the current character plan.",
                    tags=("lap_reward", "shards"),
                    score_delta=max(0.0, shard_score - cash_score),
                )
            )
        if decision.choice == "coins" and placeable:
            detector_hits.append(
                build_detector_hit(
                    "adv_coin_conversion_window",
                    kind="advantage",
                    severity=0.76,
                    confidence=0.82,
                    reason="Score-coin conversion window is open on owned land.",
                    tags=("lap_reward", "coins"),
                    score_delta=max(0.0, coin_score - cash_score),
                )
            )
        if plan_ctx is not None and plan_ctx.plan_key == "lap_engine" and decision.choice in {"coins", "cash"}:
            detector_hits.append(
                build_detector_hit(
                    "adv_lap_engine_window",
                    kind="advantage",
                    severity=0.7,
                    confidence=0.78,
                    reason="Lap-engine plan is shaping the reward toward tempo resources.",
                    tags=("lap_reward", "lap_engine"),
                    score_delta=max(cash_score, coin_score) - shard_score,
                )
            )

        trace = DecisionTrace(
            decision_type="lap_reward",
            features={
                "mode": mode,
                "cash": player.cash,
                "shards": player.shards,
                "hand_coins": player.hand_coins,
                "placeable": placeable,
                "buy_value": buy_value,
                "cross_start": cross_start,
                "land_f": land_f,
                "land_f_value": float(f_ctx["land_f_value"]),
                "token_window_score": token_window_score,
                "cleanup_stage": cleanup_strategy.cleanup_stage,
                "survival_cash_pressure": survival_cash_pressure,
                "rich_pool": rich_pool,
                "plan_key": None if plan_ctx is None else plan_ctx.plan_key,
                "resource_intent": None if plan_ctx is None else plan_ctx.resource_intent,
            },
            detector_hits=tuple(detector_hits),
            effect_adjustments=(
                {"kind": "cash_score", "value": round(float(cash_score), 3)},
                {"kind": "shard_score", "value": round(float(shard_score), 3)},
                {"kind": "coin_score", "value": round(float(coin_score), 3)},
                {"kind": "preferred", "value": preferred},
            ),
            final_choice={
                "choice": decision.choice,
                "cash_units": decision.cash_units,
                "shard_units": decision.shard_units,
                "coin_units": decision.coin_units,
            },
        )
        policy._set_debug(
            "lap_reward",
            player.player_id,
            {
                "decision": {
                    "choice": decision.choice,
                    "cash_units": decision.cash_units,
                    "shard_units": decision.shard_units,
                    "coin_units": decision.coin_units,
                },
                "trace": build_decision_trace_payload(trace),
            },
        )

    if mode.startswith("heuristic_v2_") or mode == "heuristic_v3_gpt":
        profile = policy._profile_from_mode(mode)
        current_char = player.current_character
        preferred_override: str | None = None
        token_window_score = 0.0
        rich_pool = 0.0
        plan_ctx = None

        coin_score = (
            (2.5 if placeable else -0.5)
            + (1.6 if (is_gakju(current_char) or is_swindler(current_char)) else 0.0)
            + 1.2 * cross_start
        )
        if current_char == "ì±„ì¨©ì§œì±˜ì§­í˜¨ì°½?ì™¿Â€ì‘¦ã‰±â—ˆ?":
            coin_score += 0.9 + 0.35 * policy._matchmaker_adjacent_value(state, player)
        elif current_char == "ì±…ì§¬?ì™—ãƒ…ë®»ê²·ã¢ì©Â€?ì±˜?ì‹¢Â€ì¡—?ì’‹Â€?":
            coin_score += 1.00 + 0.55 * policy._builder_free_purchase_value(state, player)

        shard_score = 0.8 + (1.9 if (is_shard_hunter_character(current_char) or is_baksu(current_char) or is_mansin(current_char)) else 0.0)
        shard_score += 0.35 * max(0, 6 - player.shards) + max(0.0, 0.7 * land_f * float(f_ctx["land_f_value"]))
        if current_char == "ì±„ì¨©ì§œì±˜ì§­í˜¨ì°½?ì™¿Â€ì‘¦ã‰±â—ˆ?" and player.shards < 2:
            shard_score += 0.75 + 0.20 * max(0, 2 - player.shards)
        if is_baksu(current_char):
            shard_score += 0.25 * min(2, player.shards // 5 + 1)
        if is_mansin(current_char):
            shard_score += 0.18 * min(2, player.shards // 7 + 1)

        cash_score = 1.2 + 0.4 * max(0, 10 - player.cash)
        if survival_cash_pressure:
            cash_score += 1.35 + 0.95 * survival_ctx["survival_urgency"] + 0.25 * max(0.0, -survival_ctx["cash_after_reserve"])
            coin_score -= 0.55 * survival_ctx["survival_urgency"]
            shard_score -= 0.40 * survival_ctx["survival_urgency"]
            if placeable and survival_ctx["recovery_score"] >= 1.2:
                coin_score += 0.25
        if not bool(f_ctx["is_leader"]):
            cash_score += 0.45 + 0.30 * float(f_ctx["avoid_f_acceleration"])
            shard_score -= 0.35 + 0.20 * float(f_ctx["avoid_f_acceleration"])
        if is_gakju(current_char):
            shard_score += max(0.0, 0.9 * land_f * float(f_ctx["land_f_value"]))
            coin_score += 0.8 * cross_start

        if profile == "v3_gpt":
            token_window = policy._token_placement_window_metrics(state, player)
            lap_ctx = policy._lap_engine_context(state, player)
            token_window_score = float(token_window["window_score"])
            rich_pool = float(lap_ctx["rich_pool"])
            plan_ctx = build_turn_plan_context(
                policy._current_player_intent(state, player, current_char),
                cleanup_strategy,
                current_character=current_char,
                cash=player.cash,
                shards=player.shards,
            )
            cash_score, shard_score, coin_score, preferred = evaluate_v3_lap_reward(
                V3LapRewardInputs(
                    current_character=current_char,
                    cash=player.cash,
                    shards=player.shards,
                    hand_coins=player.hand_coins,
                    placeable=placeable,
                    buy_value=buy_value,
                    cross_start=cross_start,
                    land_f=land_f,
                    land_f_value=float(f_ctx["land_f_value"]),
                    own_land=policy._prob_land_on_placeable_own_tile(state, player),
                    token_window_score=token_window_score,
                    token_window_nearest_distance=float(token_window["nearest_distance"]),
                    token_window_revisit_prob=float(token_window["revisit_prob"]),
                    cleanup_pressure=float(survival_ctx.get("cleanup_pressure", 0.0)),
                    next_negative_cleanup_prob=float(survival_ctx.get("next_draw_negative_cleanup_prob", 0.0)),
                    two_negative_cleanup_prob=float(survival_ctx.get("two_draw_negative_cleanup_prob", 0.0)),
                    expected_cleanup_cost=float(survival_ctx.get("expected_cleanup_cost", 0.0)),
                    survival_cash_pressure=survival_cash_pressure,
                    burden_count=float(survival_ctx.get("own_burdens", 0.0)),
                    lap_cash_preference=cleanup_strategy.lap_cash_preference,
                    lap_shard_preference=cleanup_strategy.lap_shard_preference,
                    cleanup_growth_locked=cleanup_strategy.growth_locked,
                    cleanup_stage=cleanup_strategy.cleanup_stage,
                    cleanup_stage_score=cleanup_strategy.stage_score,
                    is_leader=bool(f_ctx["is_leader"]),
                    rich_pool=rich_pool,
                    is_baksu=is_baksu(current_char),
                    is_mansin=is_mansin(current_char),
                    is_shard_hunter=is_shard_hunter_character(current_char),
                    is_controller=is_controller_character(current_char),
                    is_gakju=is_gakju(current_char),
                ),
                plan_ctx=plan_ctx,
            )
            cash_unit, shard_unit, coin_unit, preferred = normalize_lap_reward_scores(
                cash_score=cash_score,
                shard_score=shard_score,
                coin_score=coin_score,
                lap_reward_cash=float(state.config.coins.lap_reward_cash),
                lap_reward_shards=float(state.config.shards.lap_reward_shards),
                lap_reward_coins=float(state.config.coins.lap_reward_coins),
                preferred_override=preferred,
            )
            decision = policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
            _record_lap_reward_debug(
                decision=decision,
                cash_score=cash_score,
                shard_score=shard_score,
                coin_score=coin_score,
                preferred=preferred,
                token_window_score=token_window_score,
                rich_pool=rich_pool,
                plan_ctx=plan_ctx,
            )
            return decision

        if profile in {"control", "growth", "avoid_control", "aggressive", "token_opt"}:
            denial_snapshot = policy._leader_denial_snapshot(state, player) if profile == "control" else {}
            liquidity = policy._liquidity_risk_metrics(state, player, current_char) if profile == "control" else {"cash_after_reserve": 0.0}
            rent_pressure, _ = policy._rent_pressure_breakdown(state, player, current_char or "") if profile == "control" else (0.0, [])
            burden_context = policy._burden_context(state, player) if profile == "control" else {}
            token_window = policy._token_placement_window_metrics(state, player) if profile == "token_opt" else {"window_score": 0.0, "placeable_count": 0.0, "nearest_distance": 999.0, "revisit_prob": 0.0}
            token_window_score = float(token_window["window_score"])
            cash_score, shard_score, coin_score, preferred_profile = apply_v2_profile_lap_reward_bias(
                cash_score,
                shard_score,
                coin_score,
                inputs=V2ProfileLapRewardInputs(
                    profile=profile,
                    cash=player.cash,
                    shards=player.shards,
                    hand_coins=player.hand_coins,
                    placeable=placeable,
                    buy_value=buy_value,
                    land_f=land_f,
                    land_f_value=float(f_ctx["land_f_value"]),
                    own_land=policy._prob_land_on_placeable_own_tile(state, player) if profile == "token_opt" else 0.0,
                    token_combo=policy._token_teleport_combo_score(player) if profile == "token_opt" else 0.0,
                    token_window_score=token_window_score,
                    token_window_placeable_count=float(token_window["placeable_count"]),
                    token_window_nearest_distance=float(token_window["nearest_distance"]),
                    token_window_revisit_prob=float(token_window["revisit_prob"]),
                    emergency=float(denial_snapshot.get("emergency", 0.0)),
                    finisher_window=policy._control_finisher_window(player)[0] if profile == "control" else 0.0,
                    low_cash=max(0.0, 7.0 - player.cash) if profile == "control" else 0.0,
                    cash_after_reserve=float(liquidity["cash_after_reserve"]),
                    rent_pressure=rent_pressure,
                    burden_count=float(count_burden_cards(player.trick_hand)),
                    cleanup_pressure=float(burden_context.get("cleanup_pressure", 0.0)),
                    solo_leader=bool(denial_snapshot.get("solo_leader", False)),
                    near_end=bool(denial_snapshot.get("near_end", False)),
                    is_controller_role=(
                        is_controller_character(current_char)
                        or is_bandit(current_char)
                        or is_tamgwanori(current_char)
                        or is_ajeon(current_char)
                        or is_eosa(current_char)
                        or is_swindler(current_char)
                    ),
                ),
            )
            preferred_override = preferred_override or preferred_profile

        cash_unit, shard_unit, coin_unit, preferred = normalize_lap_reward_scores(
            cash_score=cash_score,
            shard_score=shard_score,
            coin_score=coin_score,
            lap_reward_cash=float(state.config.coins.lap_reward_cash),
            lap_reward_shards=float(state.config.shards.lap_reward_shards),
            lap_reward_coins=float(state.config.coins.lap_reward_coins),
            preferred_override=preferred_override,
        )
        decision = policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
        _record_lap_reward_debug(
            decision=decision,
            cash_score=cash_score,
            shard_score=shard_score,
            coin_score=coin_score,
            preferred=preferred,
            token_window_score=token_window_score,
            rich_pool=rich_pool,
            plan_ctx=plan_ctx,
        )
        return decision

    if mode == "balanced":
        cash_unit, shard_unit, coin_unit, preferred = evaluate_basic_lap_reward(
            BasicLapRewardInputs(
                current_character=player.current_character,
                cash=player.cash,
                shards=player.shards,
                placeable=placeable and player.hand_coins < 2,
                survival_cash_pressure=survival_cash_pressure,
                is_shard_hunter=is_shard_hunter_character(player.current_character) or is_ajeon(player.current_character),
            ),
            balanced=True,
        )
        decision = policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
        _record_lap_reward_debug(
            decision=decision,
            cash_score=cash_unit,
            shard_score=shard_unit,
            coin_score=coin_unit,
            preferred=preferred,
        )
        return decision

    cash_unit, shard_unit, coin_unit, preferred = evaluate_basic_lap_reward(
        BasicLapRewardInputs(
            current_character=player.current_character,
            cash=player.cash,
            shards=player.shards,
            placeable=placeable,
            survival_cash_pressure=survival_cash_pressure,
            is_shard_hunter=is_shard_hunter_character(player.current_character) or is_ajeon(player.current_character),
        ),
        balanced=False,
    )
    decision = policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
    _record_lap_reward_debug(
        decision=decision,
        cash_score=cash_unit,
        shard_score=shard_unit,
        coin_score=coin_unit,
        preferred=preferred,
    )
    return decision
