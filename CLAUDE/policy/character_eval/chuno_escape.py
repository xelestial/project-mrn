from __future__ import annotations

"""policy/character_eval/chuno_escape — 추노꾼 / 탈출 노비 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class ChunoBondservantEvaluator(CharacterEvaluator):
    """추노꾼 / 탈출 노비 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"추노꾼", "탈출 노비"})

    def score(
        self,
        state: Any,
        player: Any,
        character_name: str,
        ectx: CharacterEvalContext,
        policy_ref: Any,
    ) -> tuple[float, float, float, float, float, float, list]:
        expansion = economy = disruption = meta = combo = survival = 0.0
        reasons: list = []

        # ── 추노꾼 ────────────────────────────────────────────────────────────
        if character_name == "추노꾼":
            disruption += 0.8
            if ectx.buy_value > 0:
                disruption += 2.6
                reasons.append("post_buy_rent_trap")
            if ectx.leader_pressure > 0 and ectx.top_threat and ectx.top_threat.tiles_owned >= 5:
                disruption += 1.0 + 0.45 * ectx.leader_pressure
                reasons.append("leader_position_punish")
            if ectx.has_marks and any(op.cash >= 8 for op in ectx.legal_marks):
                disruption += 1.1

        # ── 탈출 노비 ─────────────────────────────────────────────────────────
        if character_name == "탈출 노비":
            economy += 0.3 * policy_ref._reachable_specials_with_one_short(state, player)
            if ectx.cross_start > 0.2:
                combo += 0.8
                reasons.append("escape_runner")

        # ── 적 독점 저지 (그룹) ────────────────────────────────────────────────
        if character_name == "추노꾼" and ectx.enemy_near_complete > 0:
            disruption += 1.6 * ectx.enemy_near_complete + 0.35 * ectx.deny_now
            reasons.append("deny_enemy_monopoly")

        # ── 독점 위기 탈출 (탈출 노비) ────────────────────────────────────────
        if character_name == "탈출 노비" and ectx.deny_now > 0:
            survival += 0.55 * ectx.deny_now
            reasons.append("monopoly_danger_escape")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0:
                pass  # 추노꾼/탈출노비는 control_efficient_denial 대상 아님
            if ectx.finisher_window > 0.0 and character_name == "추노꾼":
                disruption -= 0.45 + 0.15 * ectx.finisher_window
                survival -= 0.10 * ectx.finisher_window
                reasons.append("control_finisher_avoids_redundant_denial")
            if ectx.leader_near_end and character_name == "탈출 노비":
                disruption += 0.55
                survival += 0.25
                reasons.append("control_endgame_lock")

        # ── aggressive ────────────────────────────────────────────────────────
        if ectx.profile == "aggressive" and character_name == "추노꾼":
            combo += 0.9
            reasons.append("aggressive_push")

        # ── v3_claude ─────────────────────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)

            my_tiles = player.tiles_owned
            max_enemy_tiles = max(
                (p.tiles_owned for p in state.players if p.alive and p.player_id != player.player_id),
                default=0,
            )
            tile_gap = max_enemy_tiles - my_tiles
            if tile_gap >= 2 and character_name == "추노꾼":
                disruption += 0.5 + 0.15 * tile_gap
                reasons.append(f"v3_catch_up_mode(gap={tile_gap})")

        # ── token_opt ─────────────────────────────────────────────────────────
        if ectx.profile == "token_opt":
            if character_name == "탈출 노비":
                economy += 1.2 * ectx.cross_start + 0.7 * ectx.land_f * ectx.land_f_value
                combo += ectx.token_combo_score
                reasons.append("token_route_mobility")
            if character_name == "추노꾼" and ectx.top_threat and ectx.leader_pressure >= 2.5:
                disruption += 0.8 + 0.25 * ectx.leader_pressure
                reasons.append("token_threshold_counter")
            if ectx.placeable and character_name == "탈출 노비":
                combo += 0.8 + 1.4 * ectx.own_land_prob + ectx.token_combo_score
                reasons.append("token_placeable_pressure")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
