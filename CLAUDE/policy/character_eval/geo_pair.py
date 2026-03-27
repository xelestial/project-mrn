from __future__ import annotations

"""policy/character_eval/geo_pair — 객주 / 중매꾼 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class GeoPairEvaluator(CharacterEvaluator):
    """객주 / 중매꾼 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"객주", "중매꾼"})

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

        # ── 객주 ──────────────────────────────────────────────────────────────
        if character_name == "객주":
            economy += (
                2.0 * ectx.cross_start
                + 1.2 * ectx.land_f * ectx.land_f_value
                + 0.25 * len(player.visited_owned_tile_indices)
            )
            if ectx.leader_pressure > 0 and ectx.top_threat and (
                ectx.top_threat_cross > 0.3
                or ectx.top_threat_land_f > 0.2
                or "geo" in ectx.top_tags
            ):
                disruption += 1.0 + 0.3 * ectx.leader_pressure
                reasons.append("deny_leader_lap_engine")
            if ectx.cross_start > 0.3:
                reasons.append("near_start_cross")
            if ectx.land_f > 0.2:
                reasons.append("f_tile_bonus")
            if any(n in ectx.combo_names for n in {"뇌절왕", "극심한 분리불안", "도움 닫기"}):
                combo += 1.6
                reasons.append("lap_token_combo")

        # ── 중매꾼 ────────────────────────────────────────────────────────────
        if character_name == "중매꾼":
            adjacent_value = policy_ref._matchmaker_adjacent_value(state, player)
            expansion += 1.15 + 0.75 * ectx.buy_value + adjacent_value
            if ectx.leader_pressure > 0 and ectx.top_threat and (
                "expansion" in ectx.top_tags or ectx.top_threat.tiles_owned >= 5
            ):
                disruption += (
                    1.0
                    + 0.35 * ectx.leader_pressure
                    + 0.35 * max(0.0, ectx.buy_value)
                    + 0.20 * adjacent_value
                )
                reasons.append("deny_leader_expansion")
            if "무료 증정" in ectx.combo_names or "마당발" in ectx.combo_names:
                combo += 1.6 + 0.35 * adjacent_value
                reasons.append("expansion_trick_combo")
            if player.shards <= 0:
                expansion -= 0.55
                reasons.append("matchmaker_adjacent_shard_gate")

        # ── 현금 경제 (공통) ──────────────────────────────────────────────────
        if character_name == "객주":
            economy += 0.15 * player.cash
        elif character_name == "중매꾼":
            economy += 0.10 * player.cash + 0.20 * policy_ref._matchmaker_adjacent_value(state, player)

        # ── 배치 가능 타일 경제 ──────────────────────────────────────────────
        if ectx.placeable:
            economy += 0.8

        # ── 독점 완성 ─────────────────────────────────────────────────────────
        if character_name == "중매꾼" and ectx.own_near_complete > 0:
            expansion += (
                2.25 * ectx.own_near_complete
                + 0.65 * ectx.own_claimable_blocks
                + 0.35 * policy_ref._matchmaker_adjacent_value(state, player)
            )
            reasons.append("monopoly_finish_value")

        # ── 독점 경로 ─────────────────────────────────────────────────────────
        if character_name == "객주" and ectx.own_claimable_blocks > 0:
            economy += 0.65 * ectx.own_claimable_blocks
            reasons.append("monopoly_route_value")
        if character_name == "중매꾼" and ectx.own_claimable_blocks > 0:
            economy += 0.55 * ectx.own_claimable_blocks + 0.20 * policy_ref._matchmaker_adjacent_value(state, player)
            reasons.append("monopoly_route_value")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── 선두 여부 / avoid_control ─────────────────────────────────────────
        if ectx.profile == "avoid_control":
            if character_name == "객주":
                survival += 1.1
            if character_name == "중매꾼" and (ectx.leading or ectx.top_threat and ectx.has_marks):
                survival -= 1.4
                reasons.append("avoid_being_targeted")

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0:
                pass  # 객주/중매꾼은 control_efficient_denial 대상 아님
            elif ectx.buy_value > 0.0:
                if character_name in {"중매꾼", "객주"}:
                    expansion += 0.45 + 0.20 * ectx.buy_value
                    economy += 0.20
                    if character_name == "중매꾼":
                        expansion += 0.22 + 0.10 * policy_ref._matchmaker_adjacent_value(state, player)
                    reasons.append("control_keeps_pace")
            if ectx.finisher_window > 0.0:
                if character_name in {"중매꾼", "객주"}:
                    expansion += 0.85 + 0.35 * ectx.finisher_window + 0.18 * ectx.buy_value
                    economy += 0.35 + 0.18 * ectx.finisher_window
                    combo += 0.18 * ectx.finisher_window
                    reasons.append(f"control_finisher_window={ectx.finisher_reason}")

        # ── aggressive ────────────────────────────────────────────────────────
        if ectx.profile == "aggressive":
            pass  # 객주/중매꾼은 aggressive_push 대상 아님

        # ── v3_claude ────────────────────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)

            if character_name == "중매꾼":
                if player.shards >= 1 and ectx.buy_value > 0.0:
                    expansion += 1.0 + 0.3 * ectx.buy_value
                    reasons.append("v3_matchmaker_expansion")
                elif player.shards == 0:
                    expansion -= 0.6
                    reasons.append("v3_matchmaker_no_shards")

            # 상황 인식: 상대 타일 격차
            my_tiles = player.tiles_owned
            max_enemy_tiles = max(
                (p.tiles_owned for p in state.players if p.alive and p.player_id != player.player_id),
                default=0,
            )
            tile_gap = max_enemy_tiles - my_tiles
            if tile_gap >= 2 and character_name in {"중매꾼", "객주"} and ectx.buy_value > 0.0:
                expansion += 0.4 + 0.1 * tile_gap
                reasons.append("v3_catch_up_buy")

        # ── token_opt ─────────────────────────────────────────────────────────
        if ectx.profile == "token_opt":
            if character_name == "객주":
                economy += 1.2 * ectx.cross_start + 0.7 * ectx.land_f * ectx.land_f_value
                combo += ectx.token_combo_score
                reasons.append("token_route_mobility")
            if character_name in {"객주", "중매꾼"}:
                economy += 1.4 * ectx.own_land_prob
                reasons.append("own_tile_token_arrival")
            if ectx.placeable:
                combo += 0.8 + 1.4 * ectx.own_land_prob + ectx.token_combo_score
                reasons.append("token_placeable_pressure")

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
