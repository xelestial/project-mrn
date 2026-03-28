from __future__ import annotations

"""policy/character_eval/doctrine_pair — 교리 연구관 / 교리 감독관 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class DoctrinePairEvaluator(CharacterEvaluator):
    """교리 연구관 / 교리 감독관 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"교리 연구관", "교리 감독관"})

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

        # ── 교리 계열 핵심 로직 ───────────────────────────────────────────────
        meta += 1.2
        # 짐 제거 가치
        own_burden_cost = float(sum(c.burden_cost for c in player.trick_hand if c.is_burden))
        own_burden_count = sum(1 for c in player.trick_hand if c.is_burden)
        if own_burden_count >= 1:
            meta += 1.0 + 0.55 * own_burden_cost
            reasons.append("doctrine_burden_relief_value")
        # 징표 뒤집기 가치
        if ectx.top_threat and (
            "expansion" in ectx.top_tags
            or "geo" in ectx.top_tags
            or ectx.top_threat.tiles_owned >= 5
        ):
            meta += 1.6 + 0.35 * ectx.leader_pressure
            reasons.append("flip_meta_denial")
        if float(ectx.marker_plan.get("best_score", 0.0)) > 0.0:
            best = float(ectx.marker_plan["best_score"])
            meta += 0.95 + 0.85 * best
            disruption += 0.30 * best
            reasons.append("marker_strips_needed_leader_face")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── avoid_control ──────────────────────────────────────────────────────
        if ectx.profile == "avoid_control":
            survival += 1.1

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0:
                disruption += 0.55 + 0.30 * ectx.leader_emergency
                meta += 0.15 * ectx.leader_emergency
                reasons.append("control_efficient_denial")
                if ectx.leader_near_end:
                    disruption += 0.55
                    survival += 0.25
                    reasons.append("control_endgame_lock")

        # ── v3_claude ─────────────────────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)
            # 교리 계열: 리더 종속 + 징표 제어 가치
            if ectx.top_threat:
                meta += 0.6 + 0.4 * ectx.leader_pressure
                reasons.append("v3_marker_control_value")

            my_tiles = player.tiles_owned
            max_enemy_tiles = max(
                (p.tiles_owned for p in state.players if p.alive and p.player_id != player.player_id),
                default=0,
            )
            tile_gap = max_enemy_tiles - my_tiles
            if tile_gap >= 2:
                disruption += 0.5 + 0.15 * tile_gap
                reasons.append(f"v3_catch_up_mode(gap={tile_gap})")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
