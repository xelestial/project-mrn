from __future__ import annotations

"""policy/character_eval/builder_swindler — 건설업자 / 사기꾼 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class BuilderSwindlerEvaluator(CharacterEvaluator):
    """건설업자 / 사기꾼 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"건설업자", "사기꾼"})

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

        # ── 건설업자 ──────────────────────────────────────────────────────────
        if character_name == "건설업자":
            build_value = policy_ref._builder_free_purchase_value(state, player)
            expansion += 1.18 + 0.68 * ectx.buy_value + 0.90 * build_value
            if ectx.leader_pressure > 0 and ectx.top_threat and (
                "expansion" in ectx.top_tags or ectx.top_threat.tiles_owned >= 5
            ):
                disruption += 1.0 + 0.35 * ectx.leader_pressure + 0.30 * max(0.0, ectx.buy_value)
                reasons.append("deny_leader_expansion")
            if "무료 증정" in ectx.combo_names or "마당발" in ectx.combo_names:
                combo += 1.2 + 0.45 * build_value
                reasons.append("expansion_trick_combo")

        # ── 사기꾼 ────────────────────────────────────────────────────────────
        if character_name == "사기꾼":
            enemy_tiles = sum(p.tiles_owned for p in policy_ref._alive_enemies(state, player))
            expansion += 1.2 + 0.25 * enemy_tiles
            if ectx.leader_pressure > 0 and ectx.top_threat and ectx.top_threat.tiles_owned >= 4:
                disruption += 1.0 + 0.35 * ectx.leader_pressure
                reasons.append("deny_leader_takeover_lines")
            if ectx.land_f > 0.15 or "극심한 분리불안" in ectx.combo_names:
                combo += 1.8
                reasons.append("arrival_takeover_combo")
            if ectx.exclusive_blocks >= 2:
                expansion -= 0.9
                reasons.append("monopoly_blocks_takeover")
            if ectx.scammer["coin_value"] > 0.0:
                expansion += 0.75 * ectx.scammer["coin_value"]
                disruption += 0.55 * ectx.scammer["coin_value"]
                reasons.append("takeover_coin_swing")
            if ectx.scammer["best_tile_coins"] >= 2:
                combo += 0.9 + 0.25 * ectx.scammer["best_tile_coins"]
                reasons.append("rich_tile_takeover")
            if ectx.scammer["blocks_enemy_monopoly"] > 0.0:
                disruption += 1.4 * ectx.scammer["blocks_enemy_monopoly"]
                reasons.append("blocks_monopoly_with_coin_swing")
            if ectx.scammer["finishes_own_monopoly"] > 0.0:
                expansion += 1.2 * ectx.scammer["finishes_own_monopoly"]
                reasons.append("finishes_monopoly_via_takeover")

        # ── 현금 경제 (공통) ──────────────────────────────────────────────────
        if character_name == "사기꾼":
            economy += 0.15 * player.cash
        elif character_name == "건설업자":
            economy += 0.09 * player.cash + 0.28 * policy_ref._builder_free_purchase_value(state, player)

        # ── 독점 완성 ─────────────────────────────────────────────────────────
        if character_name == "건설업자" and ectx.own_near_complete > 0:
            build_value = policy_ref._builder_free_purchase_value(state, player)
            expansion += (
                2.05 * ectx.own_near_complete
                + 0.45 * ectx.own_claimable_blocks
                + 0.45 * build_value
            )
            reasons.append("monopoly_finish_value")

        # ── 독점 경로 ─────────────────────────────────────────────────────────
        if character_name == "건설업자" and ectx.own_claimable_blocks > 0:
            expansion += 0.45 * ectx.own_claimable_blocks + 0.25 * policy_ref._builder_free_purchase_value(state, player)
            reasons.append("monopoly_route_value")

        # ── 적 독점 탈취 (사기꾼) ─────────────────────────────────────────────
        if character_name == "사기꾼" and ectx.enemy_near_complete > 0:
            disruption += 2.2 * ectx.enemy_near_complete + 0.45 * ectx.contested_blocks
            reasons.append("preempt_monopoly_takeover")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── avoid_control ──────────────────────────────────────────────────────
        if ectx.profile == "avoid_control":
            if (ectx.leading or ectx.top_threat and ectx.has_marks):
                survival -= 1.4
                reasons.append("avoid_being_targeted")

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0:
                if character_name == "사기꾼":
                    disruption += 0.55 + 0.30 * ectx.leader_emergency
                    meta += 0.15 * ectx.leader_emergency
                    reasons.append("control_efficient_denial")
                if ectx.leader_near_end and character_name == "사기꾼":
                    disruption += 0.55
                    survival += 0.25
                    reasons.append("control_endgame_lock")
            elif ectx.buy_value > 0.0:
                expansion += 0.45 + 0.20 * ectx.buy_value
                economy += 0.20
                if character_name == "건설업자":
                    expansion += 0.18 + 0.12 * policy_ref._builder_free_purchase_value(state, player)
                reasons.append("control_keeps_pace")
            if ectx.finisher_window > 0.0:
                expansion += 0.85 + 0.35 * ectx.finisher_window + 0.18 * ectx.buy_value
                economy += 0.35 + 0.18 * ectx.finisher_window
                combo += 0.18 * ectx.finisher_window
                reasons.append(f"control_finisher_window={ectx.finisher_reason}")

        # ── aggressive ────────────────────────────────────────────────────────
        if ectx.profile == "aggressive":
            if character_name in {"건설업자", "사기꾼"}:
                combo += 0.9
                reasons.append("aggressive_push")

        # ── v3_claude ─────────────────────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)

            if character_name == "건설업자" and ectx.buy_value > 0.0:
                expansion += 0.8 + 0.4 * ectx.buy_value
                reasons.append("v3_builder_buy_window")
            if character_name == "사기꾼" and ectx.buy_value > 0.0:
                expansion += 0.6 + 0.3 * ectx.buy_value
                reasons.append("v3_swindler_buy_window")

            my_tiles = player.tiles_owned
            max_enemy_tiles = max(
                (p.tiles_owned for p in state.players if p.alive and p.player_id != player.player_id),
                default=0,
            )
            tile_gap = max_enemy_tiles - my_tiles
            if tile_gap >= 2 and ectx.buy_value > 0.0:
                expansion += 0.4 + 0.1 * tile_gap
                reasons.append("v3_catch_up_buy")

        # ── token_opt ─────────────────────────────────────────────────────────
        if ectx.profile == "token_opt":
            if character_name in {"건설업자", "사기꾼"}:
                economy += 1.4 * ectx.own_land_prob
                reasons.append("own_tile_token_arrival")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
