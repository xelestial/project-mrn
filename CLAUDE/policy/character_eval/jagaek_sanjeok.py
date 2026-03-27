from __future__ import annotations

"""policy/character_eval/jagaek_sanjeok — 자객 / 산적 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class JagaekSanjeokEvaluator(CharacterEvaluator):
    """자객 / 산적 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"자객", "산적"})

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

        # ── 조각 경제 (shard group: 산적/아전/탐관오리) ───────────────────────
        if character_name == "산적":
            economy += 0.35 * player.shards
            if "성물 수집가" in ectx.combo_names:
                combo += 1.3
                reasons.append("shard_combo")

        # ── 자객 ──────────────────────────────────────────────────────────────
        if character_name == "자객":
            if ectx.has_marks and ectx.top_threat and (
                "expansion" in ectx.top_tags
                or "geo" in ectx.top_tags
                or "combo_ready" in ectx.top_tags
                or ectx.top_threat.tiles_owned >= 5
            ):
                disruption += 2.4 + 0.45 * ectx.leader_pressure
                reasons.append("prevent_big_turn")

        # ── 산적 ──────────────────────────────────────────────────────────────
        if character_name == "산적":
            if ectx.has_marks and ectx.top_threat and (
                ectx.top_threat.cash >= 12 or ectx.top_threat.tiles_owned >= 5
            ):
                disruption += 1.8 + 0.15 * player.shards + 0.35 * ectx.leader_pressure
                reasons.append("cash_damage_value")

        # ── 적 독점 저지 (그룹: 추노꾼/자객/산적) ────────────────────────────
        if ectx.enemy_near_complete > 0:
            disruption += 1.6 * ectx.enemy_near_complete + 0.35 * ectx.deny_now
            reasons.append("deny_enemy_monopoly")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.finisher_window > 0.0:
                disruption -= 0.45 + 0.15 * ectx.finisher_window
                survival -= 0.10 * ectx.finisher_window
                reasons.append("control_finisher_avoids_redundant_denial")

        # ── aggressive ────────────────────────────────────────────────────────
        if ectx.profile == "aggressive" and character_name == "자객":
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
