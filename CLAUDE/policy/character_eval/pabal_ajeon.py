from __future__ import annotations

"""policy/character_eval/pabal_ajeon — 파발꾼 / 아전 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class PabalAjeonEvaluator(CharacterEvaluator):
    """파발꾼 / 아전 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"파발꾼", "아전"})

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

        # ── 파발꾼 ────────────────────────────────────────────────────────────
        if character_name == "파발꾼":
            economy += 1.0 * ectx.cross_start + 0.55 * ectx.land_f * ectx.land_f_value
            speed_combo = sum(1 for n in ectx.combo_names if n in {"과속", "이럇!", "도움 닫기"})
            combo += 0.6 * speed_combo
            if speed_combo > 0:
                reasons.append("speed_combo")

        # ── 아전: 조각 경제 (shard group: 산적/아전/탐관오리) ─────────────────
        if character_name == "아전":
            economy += 0.35 * player.shards
            if "성물 수집가" in ectx.combo_names:
                combo += 1.3
                reasons.append("shard_combo")

        # ── 파발꾼 현금 경제 ──────────────────────────────────────────────────
        if character_name == "파발꾼":
            economy += 0.15 * player.cash

        # ── 배치 가능 타일 경제 (파발꾼) ─────────────────────────────────────
        if character_name == "파발꾼" and ectx.placeable:
            economy += 0.8

        # ── 독점 경로 (파발꾼) ────────────────────────────────────────────────
        if character_name == "파발꾼" and ectx.own_claimable_blocks > 0:
            economy += 0.65 * ectx.own_claimable_blocks
            reasons.append("monopoly_route_value")

        # ── 독점 위기 탈출 (파발꾼) ───────────────────────────────────────────
        if character_name == "파발꾼" and ectx.deny_now > 0:
            survival += 0.55 * ectx.deny_now
            reasons.append("monopoly_danger_escape")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── avoid_control ──────────────────────────────────────────────────────
        if ectx.profile == "avoid_control":
            if character_name == "아전":
                survival += 1.1

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0:
                pass  # 파발꾼/아전은 control_efficient_denial 대상 아님
            elif ectx.buy_value > 0.0 and character_name == "파발꾼":
                expansion += 0.45 + 0.20 * ectx.buy_value
                economy += 0.20
                reasons.append("control_keeps_pace")
            if ectx.finisher_window > 0.0 and character_name == "파발꾼":
                expansion += 0.85 + 0.35 * ectx.finisher_window + 0.18 * ectx.buy_value
                economy += 0.35 + 0.18 * ectx.finisher_window
                combo += 0.18 * ectx.finisher_window
                reasons.append(f"control_finisher_window={ectx.finisher_reason}")

        # ── v3_claude ─────────────────────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)

            # 파발꾼 과집중 억제
            if character_name == "파발꾼":
                rounds_done = getattr(state, "rounds_completed", 0)
                if rounds_done >= 6 and ectx.buy_value > 0.5:
                    expansion -= 0.4
                    reasons.append("v3_pabalkun_overuse_penalty")

        # ── token_opt ─────────────────────────────────────────────────────────
        if ectx.profile == "token_opt" and character_name == "파발꾼":
            economy += 1.2 * ectx.cross_start + 0.7 * ectx.land_f * ectx.land_f_value
            combo += ectx.token_combo_score
            reasons.append("token_route_mobility")
            if ectx.placeable:
                combo += 0.8 + 1.4 * ectx.own_land_prob + ectx.token_combo_score
                reasons.append("token_placeable_pressure")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
