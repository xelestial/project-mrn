"""policy/decision/marker_flip.py — choose_active_flip_card 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState


def choose_active_flip_card(
    state: "GameState",
    player: "PlayerState",
    flippable_cards: list,
    policy_ref: "HeuristicPolicy",
) -> Optional[int]:
    from characters import CARD_TO_NAMES
    from ai_policy import ACTIVE_MONEY_DRAIN_CHARACTERS

    p = policy_ref
    if not flippable_cards:
        return None
    if p._is_random_mode():
        choice = p._choice(flippable_cards)
        p._set_debug("marker_flip", player.player_id, {
            "policy": p.character_policy_mode,
            "candidate_scores": {str(c): 0.0 for c in flippable_cards},
            "chosen_card": choice,
            "reasons": ["uniform_random"],
        })
        return choice
    scored = {}
    reasons = {}
    denial_snapshot = p._leader_denial_snapshot(state, player) if p._is_v2_mode() else None
    marker_plan = p._leader_marker_flip_plan(state, player, denial_snapshot.get("top_threat") if denial_snapshot else None) if p._is_v2_mode() else None
    opportunities = marker_plan["opportunities"] if marker_plan else {}
    survival_ctx = p._generic_survival_context(state, player, player.current_character)
    controller_need = float(survival_ctx.get("controller_need", 0.0))
    money_distress = float(survival_ctx.get("money_distress", 0.0))
    own_burden_cost = float(survival_ctx.get("own_burden_cost", 0.0))
    for card_no in flippable_cards:
        current = state.active_by_card[card_no]
        a, b = CARD_TO_NAMES[card_no]
        flipped = b if current == a else a
        if p._is_v2_mode():
            current_score, _ = p._character_score_breakdown_v2(state, player, current)
            flipped_score, flipped_reasons = p._character_score_breakdown_v2(state, player, flipped)
            deny = 0.0
            for op in p._alive_enemies(state, player):
                tags = p._predicted_opponent_archetypes(state, player, op)
                if flipped in {"자객", "산적", "객주", "중매꾼", "건설업자"} and ("expansion" in tags or "geo" in tags or "cash_rich" in tags):
                    deny += 0.6
                if current in {"중매꾼", "건설업자", "객주", "자객"} and ("expansion" in tags or "geo" in tags):
                    deny += 0.6
            if denial_snapshot and denial_snapshot["emergency"] > 0.0:
                if flipped in {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}:
                    deny += 0.9 + 0.25 * float(denial_snapshot["emergency"])
                if flipped in {"교리 연구관", "교리 감독관"}:
                    deny += 0.8 + 0.3 * float(denial_snapshot["emergency"])
                if current in {"중매꾼", "건설업자", "객주", "파발꾼"} and denial_snapshot["near_end"]:
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
                if current in ACTIVE_MONEY_DRAIN_CHARACTERS and flipped not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                    relief = 0.95 + 0.75 * controller_need + 0.35 * money_distress
                    if current == "만신" and own_burden_cost > 0.0:
                        relief += 0.25 * own_burden_cost
                    deny += relief
                    flipped_reasons = [f"money_relief_flip={relief:.2f}", *flipped_reasons]
                elif flipped in ACTIVE_MONEY_DRAIN_CHARACTERS and current not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                    deny -= 0.80 + 0.55 * controller_need + 0.25 * money_distress
                    flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
            scored[card_no] = (flipped_score - current_score) + deny
            reasons[card_no] = [f"flip_to={flipped}", f"deny={deny:.1f}", *flipped_reasons]
        else:
            current_score, _ = p._character_score_breakdown(state, player, current)
            flipped_score, flipped_reasons = p._character_score_breakdown(state, player, flipped)
            score = flipped_score - current_score
            if (controller_need > 0.0 or money_distress > 0.0) and current in ACTIVE_MONEY_DRAIN_CHARACTERS and flipped not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                score += 0.90 + 0.70 * controller_need + 0.30 * money_distress
                flipped_reasons = ["money_relief_flip", *flipped_reasons]
            elif (controller_need > 0.0 or money_distress > 0.0) and flipped in ACTIVE_MONEY_DRAIN_CHARACTERS and current not in ACTIVE_MONEY_DRAIN_CHARACTERS:
                score -= 0.75 + 0.50 * controller_need + 0.20 * money_distress
                flipped_reasons = ["avoid_enable_money_drain", *flipped_reasons]
            scored[card_no] = score
            reasons[card_no] = [f"flip_to={flipped}", *flipped_reasons]
    choice = max(flippable_cards, key=lambda c: (scored[c], -c))
    p._set_debug("marker_flip", player.player_id, {
        "policy": p.character_policy_mode,
        "candidate_scores": {str(c): round(scored[c], 3) for c in flippable_cards},
        "chosen_card": choice,
        "chosen_to": (CARD_TO_NAMES[choice][1] if state.active_by_card[choice] == CARD_TO_NAMES[choice][0] else CARD_TO_NAMES[choice][0]),
        "reasons": reasons[choice],
        "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
        "money_distress": round(money_distress, 3),
        "controller_need": round(controller_need, 3),
    })
    return choice
