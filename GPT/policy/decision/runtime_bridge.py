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
from policy.decision.hidden_trick import resolve_hidden_trick_choice_run
from policy.decision.active_flip import resolve_random_active_flip_choice, resolve_scored_active_flip_choice
from policy.decision.movement import resolve_movement_choice
from policy.decision.purchase import (
    PurchaseBenefitInputs,
    TraitPurchaseDecisionInputs,
    assess_purchase_decision_from_inputs,
    assess_v3_purchase_window_with_traits,
    build_immediate_win_purchase_result,
    build_purchase_benefit,
    build_purchase_debug_context,
    build_purchase_debug_payload,
    build_purchase_early_debug_payload,
    build_purchase_reserve_floor,
    count_owned_tiles_in_block,
    prepare_v3_purchase_benefit_with_traits,
    would_purchase_trigger_immediate_win,
)
from policy.decision.support_choices import count_burden_cards, choose_geo_bonus_kind, GeoBonusDecisionInputs
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
        ),
    )
    return result.decision


def choose_movement_runtime(policy: Any, state: Any, player: Any):
    from ai_policy import MovementDecision

    board_len = len(state.board)
    survival_ctx = policy._generic_survival_context(state, player, player.current_character)
    f_ctx = policy._f_progress_context(state, player)
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

    resolution = resolve_movement_choice(
        avg_no_cards=avg_no_cards,
        remaining_cards=tuple(policy._remaining_cards(player)),
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
        build_trick_use_debug_payload(
            score_map=resolution.score_map,
            chosen_name=None if resolution.choice is None else resolution.choice.name,
            generic_survival_score=survival_ctx["generic_survival_score"],
            survival_urgency=survival_ctx["survival_urgency"],
            strategic_mode=decisive_ctx["strategic_mode"],
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
    policy._set_debug("mark_target", player.player_id, choice_run.debug_payload)
    return choice_run.choice


def choose_hidden_trick_card_runtime(policy: Any, state: Any, player: Any, hand: list[Any]) -> Any:
    choice_run = resolve_hidden_trick_choice_run(hand, actor_name=player.current_character)
    policy._set_debug("hide_trick", player.player_id, choice_run.debug_payload)
    return choice_run.choice


def choose_draft_card_runtime(policy: Any, state: Any, player: Any, offered_cards: list[int]) -> int:
    if policy._is_random_mode():
        choice = policy._choice(offered_cards)
        policy._set_debug(
            "draft_card",
            player.player_id,
            build_uniform_random_character_choice_debug_payload(
                policy_name=policy.character_policy_mode,
                offered_cards=offered_cards,
                candidate_labels=[str(card) for card in offered_cards],
                chosen_key=choice,
                chosen_name=state.active_by_card[choice],
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
                or is_baksu(name)
                or is_mansin(name)
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
    policy._set_debug(
        "draft_card",
        player.player_id,
        build_character_choice_debug_payload(
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
        ),
    )
    return run.choice


def choose_final_character_runtime(policy: Any, state: Any, player: Any, card_choices: list[int]) -> str:
    options = [state.active_by_card[c] for c in card_choices]
    if policy._is_random_mode():
        choice = policy._choice(options)
        policy._set_debug(
            "final_character",
            player.player_id,
            build_uniform_random_character_choice_debug_payload(
                policy_name=policy.character_policy_mode,
                offered_cards=card_choices,
                candidate_labels=list(options),
                chosen_key=choice,
                chosen_name=choice,
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
                or is_baksu(name)
                or is_mansin(name)
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
    policy._set_debug(
        "final_character",
        player.player_id,
        build_character_choice_debug_payload(
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
    policy._set_debug("trick_reward", player.player_id, choice_run.debug_payload)
    return choice_run.choice


def choose_coin_placement_tile_runtime(policy: Any, state: Any, player: Any) -> Any:
    candidates = [
        i
        for i in player.visited_owned_tile_indices
        if state.tile_owner[i] == player.player_id and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
    ]
    if not candidates:
        return None
    return choose_coin_placement_tile_id(
        candidates,
        tile_coins=state.tile_coins,
        board=state.board,
        player_position=player.position,
        max_coins_per_tile=state.config.rules.token.max_coins_per_tile,
        token_opt_profile=policy._profile_from_mode() in {"token_opt", "v3_gpt"},
    )


def choose_active_flip_card_runtime(policy: Any, state: Any, player: Any, flippable_cards: list[int]) -> Any:
    if not flippable_cards:
        return None
    if policy._is_random_mode():
        resolution = resolve_random_active_flip_choice(
            flippable_cards,
            policy=policy.character_policy_mode,
            chooser=policy._choice,
        )
        policy._set_debug("marker_flip", player.player_id, resolution.debug_payload)
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
    policy._set_debug("marker_flip", player.player_id, resolution.debug_payload)
    return resolution.choice


def choose_burden_exchange_on_supply_runtime(policy: Any, state: Any, player: Any, card: Any) -> bool:
    if player.cash < card.burden_cost:
        return False
    if policy._is_random_mode():
        return True
    liquidity = policy._liquidity_risk_metrics(state, player, player.current_character)
    if policy._should_seek_escape_package(state, player):
        return False
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
    if remaining_cash <= max(5.0, 0.80 * reserve):
        return False
    hard_reason = policy._survival_hard_guard_reason(state, player, survival_ctx, post_action_cash=remaining_cash)
    if hard_reason is not None:
        return False
    return remaining_cash >= target_floor


def choose_doctrine_relief_target_runtime(policy: Any, state: Any, player: Any, candidates: list[Any]) -> Any:
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.player_id == player.player_id:
            return candidate.player_id
    return candidates[0].player_id


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

        return choose_geo_bonus_kind(
            GeoBonusDecisionInputs(
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
        )

    if player.cash < 8 or money_distress >= 0.95 or two_turn_lethal >= 0.16 or not bool(f_ctx["is_leader"]):
        return "cash"
    if is_bandit(actor_name) or is_baksu(actor_name) or is_mansin(actor_name):
        return "shards"
    return "coins"


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

    if mode.startswith("heuristic_v2_") or mode == "heuristic_v3_gpt":
        profile = policy._profile_from_mode(mode)
        current_char = player.current_character
        preferred_override: str | None = None

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
                    token_window_score=float(token_window["window_score"]),
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
                    rich_pool=float(lap_ctx["rich_pool"]),
                    is_baksu=is_baksu(current_char),
                    is_mansin=is_mansin(current_char),
                    is_shard_hunter=is_shard_hunter_character(current_char),
                    is_controller=is_controller_character(current_char),
                    is_gakju=is_gakju(current_char),
                ),
                plan_ctx=build_turn_plan_context(
                    policy._current_player_intent(state, player, current_char),
                    cleanup_strategy,
                    current_character=current_char,
                    cash=player.cash,
                    shards=player.shards,
                ),
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
            return policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)

        if profile in {"control", "growth", "avoid_control", "aggressive", "token_opt"}:
            denial_snapshot = policy._leader_denial_snapshot(state, player) if profile == "control" else {}
            liquidity = policy._liquidity_risk_metrics(state, player, current_char) if profile == "control" else {"cash_after_reserve": 0.0}
            rent_pressure, _ = policy._rent_pressure_breakdown(state, player, current_char or "") if profile == "control" else (0.0, [])
            burden_context = policy._burden_context(state, player) if profile == "control" else {}
            token_window = policy._token_placement_window_metrics(state, player) if profile == "token_opt" else {"window_score": 0.0, "placeable_count": 0.0, "nearest_distance": 999.0, "revisit_prob": 0.0}
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
                    token_window_score=float(token_window["window_score"]),
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
        return policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)

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
        return policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)

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
    return policy._lap_reward_bundle(state, cash_unit, shard_unit, coin_unit, preferred=preferred)
