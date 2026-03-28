from __future__ import annotations

"""policy/character_eval/asa_tamgwan — 어사 / 탐관오리 평가."""

from typing import Any

from .base import CharacterEvalContext, CharacterEvaluator, apply_leader_emergency, apply_v3_priority, apply_survival_risk


class AsaTamgwanEvaluator(CharacterEvaluator):
    """어사 / 탐관오리 pair 평가."""

    @property
    def characters(self) -> frozenset:
        return frozenset({"어사", "탐관오리"})

    def score(
        self,
        state: Any,
        player: Any,
        character_name: str,
        ectx: CharacterEvalContext,
        policy_ref: Any,
    ) -> tuple[float, float, float, float, float, float, list]:
        from characters import CHARACTERS

        expansion = economy = disruption = meta = combo = survival = 0.0
        reasons: list = []

        # ── 조각 경제 (shard group: 산적/아전/탐관오리) ───────────────────────
        if character_name == "탐관오리":
            economy += 0.35 * player.shards
            if "성물 수집가" in ectx.combo_names:
                combo += 1.3
                reasons.append("shard_combo")

        # ── 어사 ──────────────────────────────────────────────────────────────
        if character_name == "어사":
            if ectx.top_threat and (
                "shard_attack" in ectx.top_tags
                or ectx.top_threat.current_character in {"산적", "자객", "탐관오리", "사기꾼"}
            ):
                disruption += 1.8
                reasons.append("muroe_counter")
            # v3_claude: 어사 우선권 1 → 구매 기회 시 가산
            if ectx.profile == "v3_claude" and ectx.buy_value > 0.0:
                expansion += 0.8 + 0.3 * ectx.buy_value
                survival += 0.6
                reasons.append("v3_uhsa_first_mover")

        # ── 탐관오리 ──────────────────────────────────────────────────────────
        if character_name == "탐관오리" and ectx.profile == "v3_claude":
            # 우선권 1: 먼저 이동 → 빈 땅 선점
            if ectx.buy_value > 0.0:
                expansion += 0.7 + 0.2 * ectx.buy_value
                reasons.append("v3_tangwan_first_mover")
            survival += 0.5  # 지목 위협 없음
            # 세금 수입: 관원/상민 상대
            alive_enemies = policy_ref._alive_enemies(state, player)
            taxable = [
                p for p in alive_enemies
                if p.current_character
                and CHARACTERS.get(p.current_character)
                and CHARACTERS[p.current_character].attribute in {"관원", "상민"}
            ]
            if taxable:
                total_tax = sum(p.shards // 2 for p in taxable)
                net_tax = total_tax * 0.65
                if net_tax >= 0.5:
                    economy += 0.3 + 0.12 * net_tax
                    reasons.append(f"v3_tangwan_net_tax({total_tax}냥×0.65={net_tax:.1f})")

        # ── 리더 긴급상황 ──────────────────────────────────────────────────────
        expansion, economy, disruption, meta, combo, survival = apply_leader_emergency(
            character_name, player, ectx, expansion, economy, disruption, meta, combo, survival, reasons
        )

        # ── control ───────────────────────────────────────────────────────────
        if ectx.profile == "control":
            if ectx.leader_emergency > 0.0 and character_name == "어사":
                disruption += 0.55 + 0.30 * ectx.leader_emergency
                meta += 0.15 * ectx.leader_emergency
                reasons.append("control_efficient_denial")
                if ectx.leader_near_end:
                    disruption += 0.55
                    survival += 0.25
                    reasons.append("control_endgame_lock")

        # ── v3_claude general priority ─────────────────────────────────────────
        if ectx.profile == "v3_claude":
            v3_surv, v3_disr, v3_reasons = apply_v3_priority(character_name, player, state)
            survival += v3_surv
            disruption += v3_disr
            reasons.extend(v3_reasons)

        # ── token_opt ─────────────────────────────────────────────────────────
        # 어사/탐관오리는 token_opt 주요 대상 아님

        # ── survival / risk 공통 패널티 ───────────────────────────────────────
        expansion, economy, survival = apply_survival_risk(
            state, player, character_name, ectx, policy_ref,
            expansion, economy, survival, reasons,
        )

        return expansion, economy, disruption, meta, combo, survival, reasons
