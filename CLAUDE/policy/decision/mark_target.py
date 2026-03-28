"""policy/decision/mark_target.py — choose_mark_target 결정 모듈 + mark 유틸리티 함수."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState


# ── Pure utility functions (policy_mark_utils.py에서 이전) ──────────────────

def public_mark_guess_candidates(state: "GameState", player: "PlayerState") -> list[str]:
    """히든 배정 없이 공개 정보만으로 지목 가능한 후보 목록 반환."""
    public_pool = {name for name in state.active_by_card.values() if name}
    if player.current_character:
        public_pool.discard(player.current_character)
    try:
        my_order_idx = state.current_round_order.index(player.player_id)
    except ValueError:
        return sorted(public_pool)
    prior_pids = set(state.current_round_order[:my_order_idx])
    for other in state.players:
        if not other.current_character:
            continue
        if other.player_id in prior_pids or other.revealed_this_round:
            public_pool.discard(other.current_character)
    return sorted(public_pool)


def mark_guess_policy_params(profile: str, character_policy_mode: str) -> tuple[float, float]:
    """프로파일별 지목 추측 파라미터 반환."""
    from policy_groups import MARK_GUESS_CONFIDENCE_THRESHOLDS, MARK_GUESS_MARGIN_THRESHOLDS
    confidence = MARK_GUESS_CONFIDENCE_THRESHOLDS.get(profile, 0.42)
    margin = MARK_GUESS_MARGIN_THRESHOLDS.get(profile, 0.08)
    if character_policy_mode == "heuristic_v1":
        return 0.40, 0.08
    return confidence, margin


def mark_guess_distribution(
    candidate_scores: dict[str, float],
    legal_target_count: int,
) -> tuple[dict[str, float], dict]:
    """softmax 혼합 확률 분포 계산."""
    from policy_groups import (
        MARK_GUESS_TEMPERATURE,
        MARK_GUESS_UNIFORM_MIX_BASE,
        MARK_GUESS_UNIFORM_MIX_AMBIGUITY,
        MARK_GUESS_UNIFORM_MIX_EXTRA_CANDIDATE,
    )
    if not candidate_scores:
        return {}, {"uniform_mix": 0.0, "ambiguity": 0.0, "top_probability": 0.0, "second_probability": 0.0}
    candidates = list(candidate_scores.keys())
    raw_scores = [candidate_scores[name] for name in candidates]
    max_score = max(raw_scores)
    soft_weights = [math.exp((score - max_score) / MARK_GUESS_TEMPERATURE) for score in raw_scores]
    soft_total = sum(soft_weights) or 1.0
    soft_probs = {name: weight / soft_total for name, weight in zip(candidates, soft_weights)}
    candidate_count = len(candidates)
    ambiguity = max(0.0, 1.0 - (legal_target_count / max(1, candidate_count)))
    extra_candidates = max(0, candidate_count - max(legal_target_count, 1) - 1)
    uniform_mix = min(
        0.80,
        MARK_GUESS_UNIFORM_MIX_BASE
        + MARK_GUESS_UNIFORM_MIX_AMBIGUITY * ambiguity
        + MARK_GUESS_UNIFORM_MIX_EXTRA_CANDIDATE * extra_candidates,
    )
    uniform_prob = 1.0 / candidate_count
    mixed_probs = {name: (1.0 - uniform_mix) * soft_probs[name] + uniform_mix * uniform_prob for name in candidates}
    ordered = sorted(mixed_probs.values(), reverse=True)
    details = {
        "uniform_mix": uniform_mix,
        "ambiguity": ambiguity,
        "top_probability": ordered[0],
        "second_probability": ordered[1] if len(ordered) > 1 else 0.0,
    }
    return mixed_probs, details


def mark_priority_exposure_factor(actor_name: str, target_name: str) -> float:
    """우선권 기반 노출 팩터 (지목자 우선권 < 대상 우선권 → 1.0)."""
    from characters import CHARACTERS
    from policy_groups import MARK_PRIORITY_SAME_FACTOR
    actor_priority = CHARACTERS[actor_name].priority
    target_priority = CHARACTERS[target_name].priority
    if actor_priority < target_priority:
        return 1.0
    if actor_priority == target_priority:
        return MARK_PRIORITY_SAME_FACTOR
    return 0.0


def mark_target_profile_factor(actor_name: str, target_name: str) -> float:
    """인물별 지목 선호도 팩터."""
    from characters import CHARACTERS
    from policy_groups import (
        DISRUPTION_LIKE_CHARACTERS,
        ECONOMY_LIKE_CHARACTERS,
        GROWTH_LIKE_CHARACTERS,
    )
    target_attr = CHARACTERS[target_name].attribute
    if actor_name == "자객":
        if target_attr == "무뢰":
            return 1.35
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 1.15
        return 0.7
    if actor_name == "산적":
        if target_name in ECONOMY_LIKE_CHARACTERS:
            return 1.2
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 0.95
        return 0.65
    if actor_name == "추노꾼":
        if target_name in GROWTH_LIKE_CHARACTERS or target_name in ECONOMY_LIKE_CHARACTERS:
            return 1.0
        return 0.7
    if actor_name == "박수":
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 0.95
        return 0.6
    if actor_name == "만신":
        if target_name in DISRUPTION_LIKE_CHARACTERS or target_name == "중매꾼":
            return 0.9
        return 0.55
    return 0.0


# ── Decision function ───────────────────────────────────────────────────────

def choose_mark_target(
    state: "GameState",
    player: "PlayerState",
    actor_name: str,
    policy_ref: "HeuristicPolicy",
) -> Optional[str]:
    p = policy_ref
    legal_targets = p._allowed_mark_targets(state, player)
    candidates = p._public_mark_guess_candidates(state, player)
    if not legal_targets or not candidates:
        p._set_debug("mark_target", player.player_id, {
            "policy": p.character_policy_mode,
            "actor_name": actor_name,
            "candidate_scores": {},
            "candidate_probabilities": {},
            "chosen_target": None,
            "reasons": ["no_public_guess_candidates" if legal_targets else "no_legal_targets"],
        })
        return None
    if p._is_random_mode():
        choice = p._choice(candidates)
        p._set_debug("mark_target", player.player_id, {
            "policy": p.character_policy_mode,
            "actor_name": actor_name,
            "candidate_scores": {c: 0.0 for c in candidates},
            "candidate_probabilities": {c: round(1.0 / len(candidates), 3) for c in candidates},
            "chosen_target": choice,
            "reasons": ["uniform_random_public_guess"],
        })
        return choice
    scored = {}
    reasons = {}
    for target_name in candidates:
        score, why = p._public_target_name_score_breakdown(state, player, actor_name, target_name)
        scored[target_name] = score
        reasons[target_name] = why
    probabilities, dist_meta = p._mark_guess_distribution(scored, len(legal_targets))
    ordered = sorted(candidates, key=lambda name: (probabilities[name], scored[name], name), reverse=True)
    top_name = ordered[0]
    top_probability = dist_meta["top_probability"]
    choice = p._weighted_choice(candidates, [probabilities[name] for name in candidates])
    p._set_debug("mark_target", player.player_id, {
        "policy": p.character_policy_mode,
        "actor_name": actor_name,
        "candidate_scores": {name: round(val, 3) for name, val in scored.items()},
        "candidate_probabilities": {name: round(probabilities[name], 3) for name in candidates},
        "chosen_target": choice,
        "top_candidate": top_name,
        "uniform_mix": round(dist_meta["uniform_mix"], 3),
        "ambiguity": round(dist_meta["ambiguity"], 3),
        "top_probability": round(top_probability, 3),
        "second_probability": round(dist_meta["second_probability"], 3),
        "reasons": reasons[choice],
    })
    return choice
