"""policy/decision/trick_use.py — choose_trick_to_use 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState
    from game_cards import TrickCard


def choose_trick_to_use(
    state: "GameState",
    player: "PlayerState",
    hand: list,
    policy_ref: "HeuristicPolicy",
):
    p = policy_ref
    supported = {
        "성물 수집가": 1.8, "건강 검진": 1.2, "우대권": 1.4, "무료 증정": 1.6,
        "신의뜻": 1.0, "가벼운 분리불안": 0.9, "극심한 분리불안": 1.2, "마당발": 1.4, "뇌고왕": 1.1, "뇌절왕": 1.3,
        "재뿌리기": 1.2, "긴장감 조성": 1.3, "무역의 선물": 1.0, "도움 닫기": 1.1, "번뜩임": 0.8,
        "느슨함 혐오자": 0.9, "극도의 느슨함 혐오자": 1.5,
        "과속": 0.8, "저속": 0.3, "이럇!": 0.7, "아주 큰 화목 난로": 1.0, "거대한 산불": 1.3,
        "무거운 짐": -0.6, "가벼운 짐": -0.3,
    }
    survival_ctx = p._generic_survival_context(state, player, player.current_character)
    best = None
    best_score = 0.0
    details = {}
    for card in hand:
        immediate_cost = p._predict_trick_cash_cost(card)
        if immediate_cost > 0.0 and not p._is_action_survivable(state, player, immediate_cost=immediate_cost, survival_ctx=survival_ctx, buffer=0.5):
            details[card.name] = -999.0
            continue
        score = supported.get(card.name, -99.0)
        if card.name == "무료 증정" and player.cash >= 3:
            score += 0.6
        if card.name == "과속" and player.cash >= 2:
            score += 0.4
        if card.name == "저속":
            score += 0.2 if player.cash < 6 else -0.5
        if card.name == "재뿌리기":
            score += 0.4 if any(state.tile_owner[i] not in {None, player.player_id} for i in range(len(state.board)) if state.tile_at(i).purchase_cost is not None) else -1.0
        if card.name == "긴장감 조성":
            score += 0.5 if player.tiles_owned > 0 else -1.0
        if card.name == "무역의 선물":
            score += 0.4 if player.tiles_owned > 0 and any(own is not None and own != player.player_id for own in state.tile_owner) else -1.0
        if card.name in {"무거운 짐", "가벼운 짐"}:
            score = -1.0
        score += p._trick_survival_adjustment(state, player, card, survival_ctx)
        details[card.name] = round(score, 3)
        if score > best_score:
            best = card
            best_score = score
    p._set_debug("trick_use", player.player_id, {
        "scores": details,
        "chosen": None if best is None else best.name,
        "generic_survival_score": round(survival_ctx["generic_survival_score"], 3),
        "survival_urgency": round(survival_ctx["survival_urgency"], 3),
    })
    return best
