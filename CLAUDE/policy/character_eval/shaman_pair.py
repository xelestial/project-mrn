from __future__ import annotations

"""policy/character_eval/shaman_pair — 박수 / 만신 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class ShamanPairEvaluator(CharacterEvaluator):
    """박수 / 만신 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"박수", "만신"})

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

        # ── 만신 ──────────────────────────────────────────────────────────────
        if character_name == "만신":
            if ectx.top_threat and "burden" in ectx.top_tags:
                disruption += 2.0
                reasons.append("burden_purge")
            if ectx.legal_visible_burden_total > 0:
                disruption += (
                    1.4
                    + 1.2 * ectx.legal_visible_burden_total
                    + 0.45 * ectx.legal_visible_burden_peak
                )
                reasons.append("public_burden_cleanup_value")
            if ectx.cleanup_pressure >= 2.5:
                survival += 0.45 * ectx.cleanup_pressure
                reasons.append("future_fire_insurance")
            if ectx.legal_visible_burden_total > 0 and ectx.legal_low_cash_targets > 0:
                disruption += 0.35 * ectx.legal_low_cash_targets
                reasons.append("cash_fragile_cleanup")

        # ── 박수 ──────────────────────────────────────────────────────────────
        if character_name == "박수":
            if ectx.burden_count >= 1:
                combo += 1.0 + 0.45 * ectx.burden_count
                survival += 1.4 + 1.05 * ectx.burden_count + 0.55 * ectx.cleanup_pressure
                reasons.append("future_burden_escape")
                # 조각 5개 이상 + 짐 보유 = 폴백 확정
                if player.shards >= 5:
                    removed, payout = policy_ref._failed_mark_fallback_metrics(player, 5)
                    survival += 0.8 + 0.15 * payout
                    economy += 0.5
                    reasons.append(f"baksu_fallback_guaranteed(+{payout}냥)")
                    if ectx.burden_count >= 2 and player.shards >= 10:
                        survival += 0.6
                        reasons.append("baksu_double_fallback_possible")
            else:
                if ectx.has_marks and ectx.legal_visible_burden_total > 0:
                    survival -= 0.5
                    reasons.append("baksu_no_burden_mark_ok")
                else:
                    survival -= 1.2
                    reasons.append("baksu_no_own_burden_waste")
            if ectx.burden_count >= 1 and ectx.has_marks and ectx.legal_low_cash_targets > 0:
                disruption += 0.35 * ectx.legal_low_cash_targets
                reasons.append("burden_dump_fragile_target")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

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
            if tile_gap >= 2:
                disruption += 0.5 + 0.15 * tile_gap
                reasons.append(f"v3_catch_up_mode(gap={tile_gap})")

        # ── token_opt ─────────────────────────────────────────────────────────
        if ectx.profile == "token_opt" and ectx.top_threat and ectx.leader_pressure >= 2.5:
            disruption += 0.8 + 0.25 * ectx.leader_pressure
            reasons.append("token_threshold_counter")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
