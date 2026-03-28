from __future__ import annotations

"""policy/character_eval/context_builder — CharacterEvalContext 빌더.

_character_score_breakdown_v2의 shared setup block을 추출.
character_name-독립 값만 계산 → CharacterEvalContext 반환.
"""

from typing import Any

from .base import CharacterEvalContext


def build_char_eval_context(state: Any, player: Any, policy_ref: Any) -> CharacterEvalContext:
    """state + player → CharacterEvalContext 스냅샷.

    policy_ref는 HeuristicPolicy 인스턴스 (runtime only, 직렬화 금지).
    """
    p = policy_ref

    w = p._weights()
    profile = p._profile_from_mode()
    buy_value = p._expected_buy_value(state, player)
    cross_start = p._will_cross_start(state, player)
    land_f = p._will_land_on_f(state, player)
    f_ctx = p._f_progress_context(state, player)
    land_f_value = float(f_ctx["land_f_value"])

    burden_count = sum(1 for c in player.trick_hand if c.name in {"무거운 짐", "가벼운 짐"})
    combo_names = frozenset(c.name for c in player.trick_hand)

    legal_marks = p._allowed_mark_targets(state, player)
    has_marks = bool(legal_marks)

    burden_ctx = p._burden_context(state, player, legal_targets=legal_marks)
    monopoly = p._monopoly_block_metrics(state, player)
    scammer = p._scammer_takeover_metrics(state, player)

    threat_targets = sorted(
        p._alive_enemies(state, player),
        key=lambda op: p._estimated_threat(state, player, op),
        reverse=True,
    )
    top_threat = threat_targets[0] if threat_targets else None
    top_tags = frozenset(p._predicted_opponent_archetypes(state, player, top_threat)) if top_threat else frozenset()
    exclusive_blocks = p._exclusive_blocks_owned(state, player.player_id)
    placeable = any(
        state.tile_owner[i] == player.player_id
        and state.tile_coins[i] < state.config.rules.token.max_coins_per_tile
        for i in player.visited_owned_tile_indices
    )

    leader_pressure = p._leader_pressure(state, player, top_threat)
    denial_snapshot = p._leader_denial_snapshot(
        state, player, threat_targets=threat_targets, top_threat=top_threat
    )
    leader_emergency = float(denial_snapshot["emergency"])
    leader_is_solo = bool(denial_snapshot["solo_leader"])
    leader_near_end = bool(denial_snapshot["near_end"])
    top_threat_cross = p._will_cross_start(state, top_threat) if top_threat else 0.0
    top_threat_land_f = p._will_land_on_f(state, top_threat) if top_threat else 0.0

    enemies = p._alive_enemies(state, player)
    my_threat = p._estimated_threat(state, player, player)
    leading = all(my_threat >= p._estimated_threat(state, player, op) for op in enemies)

    # profile-specific precompute (eager, negligible overhead)
    own_land_prob = p._prob_land_on_placeable_own_tile(state, player)
    token_combo_score = p._token_teleport_combo_score(player)
    finisher_window, finisher_reason = p._control_finisher_window(player)
    marker_plan = p._leader_marker_flip_plan(state, player, top_threat)

    return CharacterEvalContext(
        w=w,
        profile=profile,
        buy_value=buy_value,
        cross_start=cross_start,
        land_f=land_f,
        land_f_value=land_f_value,
        burden_count=burden_count,
        combo_names=combo_names,
        has_marks=has_marks,
        legal_marks=tuple(legal_marks),
        cleanup_pressure=float(burden_ctx["cleanup_pressure"]),
        legal_visible_burden_total=float(burden_ctx["legal_visible_burden_total"]),
        legal_visible_burden_peak=float(burden_ctx["legal_visible_burden_peak"]),
        legal_low_cash_targets=float(burden_ctx["legal_low_cash_targets"]),
        own_near_complete=float(monopoly["own_near_complete"]),
        own_claimable_blocks=float(monopoly["own_claimable_blocks"]),
        deny_now=float(monopoly["deny_now"]),
        enemy_near_complete=float(monopoly["enemy_near_complete"]),
        contested_blocks=float(monopoly["contested_blocks"]),
        scammer=scammer,
        top_threat=top_threat,
        top_tags=top_tags,
        exclusive_blocks=exclusive_blocks,
        placeable=placeable,
        leader_pressure=leader_pressure,
        leader_emergency=leader_emergency,
        leader_is_solo=leader_is_solo,
        leader_near_end=leader_near_end,
        top_threat_cross=top_threat_cross,
        top_threat_land_f=top_threat_land_f,
        leading=leading,
        own_land_prob=own_land_prob,
        token_combo_score=token_combo_score,
        finisher_window=finisher_window,
        finisher_reason=finisher_reason,
        marker_plan=marker_plan,
    )
