"""policy/decision/draft.py — choose_draft_card / choose_final_character 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState


def choose_draft_card(
    state: "GameState",
    player: "PlayerState",
    offered_cards: list,
    policy_ref: "HeuristicPolicy",
) -> int:
    from ai_policy import (
        LOW_CASH_INCOME_CHARACTERS,
        LOW_CASH_ESCAPE_CHARACTERS,
        LOW_CASH_CONTROLLER_CHARACTERS,
    )
    p = policy_ref
    if p._is_random_mode():
        choice = p._choice(offered_cards)
        p._set_debug("draft_card", player.player_id, {
            "policy": p.character_policy_mode,
            "offered_cards": offered_cards,
            "candidate_scores": {str(c): 0.0 for c in offered_cards},
            "chosen_card": choice,
            "reasons": ["uniform_random"],
        })
        return choice
    scored = {}
    reasons = {}
    survival_ctx, survival_orchestrator = p._build_survival_orchestrator(state, player, player.current_character)
    marker_bonus = p._distress_marker_bonus(state, player, [state.active_by_card[c] for c in offered_cards])
    for card_no in offered_cards:
        active_name = state.active_by_card[card_no]
        score, why = (p._character_score_breakdown_v2(state, player, active_name) if p._is_v2_mode() else p._character_score_breakdown(state, player, active_name))
        survival_policy_bonus, survival_policy_why, survival_hard_block, survival_detail = p._survival_policy_character_advice(state, player, active_name, survival_orchestrator)
        if survival_policy_bonus != 0.0:
            score += survival_policy_bonus
            why = [*why, *survival_policy_why]
        bonus = marker_bonus.get(active_name, 0.0)
        if bonus > 0.0:
            bonus *= max(1.0, survival_orchestrator.weight_multiplier if survival_orchestrator.survival_first and active_name in LOW_CASH_INCOME_CHARACTERS | LOW_CASH_ESCAPE_CHARACTERS | LOW_CASH_CONTROLLER_CHARACTERS | {"박수", "만신"} else 1.0)
            score += bonus
            why = [*why, f"distress_marker_bonus={bonus:.2f}"]
        survival_bonus, survival_why = p._character_survival_adjustment(state, player, active_name, survival_ctx)
        if survival_bonus != 0.0:
            score += survival_bonus
            why = [*why, *survival_why]
        scored[card_no] = score
        reasons[card_no] = why
    choice = max(offered_cards, key=lambda c: (scored[c], -c))
    p._set_debug("draft_card", player.player_id, {
        "policy": p.character_policy_mode,
        "offered_cards": offered_cards,
        "candidate_scores": {str(c): round(scored[c], 3) for c in offered_cards},
        "candidate_characters": {str(c): state.active_by_card[c] for c in offered_cards},
        "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
        "survival_urgency": round(survival_ctx["survival_urgency"], 3),
        "survival_first": survival_orchestrator.survival_first,
        "survival_weight_multiplier": round(survival_orchestrator.weight_multiplier, 3),
        "survival_severity_by_candidate": {state.active_by_card[c]: p._survival_policy_character_advice(state, player, state.active_by_card[c], survival_orchestrator)[3] for c in offered_cards},
        "chosen_card": choice,
        "chosen_character": state.active_by_card[choice],
        "reasons": reasons[choice],
    })
    return choice


def choose_final_character(
    state: "GameState",
    player: "PlayerState",
    card_choices: list,
    policy_ref: "HeuristicPolicy",
) -> str:
    from ai_policy import (
        LOW_CASH_INCOME_CHARACTERS,
        LOW_CASH_ESCAPE_CHARACTERS,
        LOW_CASH_CONTROLLER_CHARACTERS,
    )
    p = policy_ref
    options = [state.active_by_card[c] for c in card_choices]
    if p._is_random_mode():
        choice = p._choice(options)
        p._set_debug("final_character", player.player_id, {
            "policy": p.character_policy_mode,
            "offered_cards": card_choices,
            "candidate_scores": {name: 0.0 for name in options},
            "chosen_character": choice,
            "reasons": ["uniform_random"],
        })
        return choice
    scored = {}
    reasons = {}
    survival_ctx, survival_orchestrator = p._build_survival_orchestrator(state, player, player.current_character)
    marker_bonus = p._distress_marker_bonus(state, player, options)
    for name in options:
        score, why = (p._character_score_breakdown_v2(state, player, name) if p._is_v2_mode() else p._character_score_breakdown(state, player, name))
        survival_policy_bonus, survival_policy_why, survival_hard_block, survival_detail = p._survival_policy_character_advice(state, player, name, survival_orchestrator)
        if survival_policy_bonus != 0.0:
            score += survival_policy_bonus
            why = [*why, *survival_policy_why]
        bonus = marker_bonus.get(name, 0.0)
        if bonus > 0.0:
            bonus *= max(1.0, survival_orchestrator.weight_multiplier if survival_orchestrator.survival_first and name in LOW_CASH_INCOME_CHARACTERS | LOW_CASH_ESCAPE_CHARACTERS | LOW_CASH_CONTROLLER_CHARACTERS | {"박수", "만신"} else 1.0)
            score += bonus
            why = [*why, f"distress_marker_bonus={bonus:.2f}"]
        survival_bonus, survival_why = p._character_survival_adjustment(state, player, name, survival_ctx)
        if survival_bonus != 0.0:
            score += survival_bonus
            why = [*why, *survival_why]
        scored[name] = score
        reasons[name] = why
    choice = max(options, key=lambda n: (scored[n], n))
    p._set_debug("final_character", player.player_id, {
        "policy": p.character_policy_mode,
        "offered_cards": card_choices,
        "candidate_scores": {name: round(scored[name], 3) for name in options},
        "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
        "survival_urgency": round(survival_ctx["survival_urgency"], 3),
        "survival_first": survival_orchestrator.survival_first,
        "survival_weight_multiplier": round(survival_orchestrator.weight_multiplier, 3),
        "survival_severity_by_candidate": {name: p._survival_policy_character_advice(state, player, name, survival_orchestrator)[3] for name in options},
        "chosen_character": choice,
        "reasons": reasons[choice],
    })
    return choice
