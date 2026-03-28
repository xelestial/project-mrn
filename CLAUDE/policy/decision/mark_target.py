"""policy/decision/mark_target.py — choose_mark_target 결정 모듈."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_policy import HeuristicPolicy
    from game_state import GameState, PlayerState


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
