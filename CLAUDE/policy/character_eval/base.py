from __future__ import annotations

"""policy/character_eval/base — CharacterEvalContext + CharacterEvaluator ABC + 공유 helpers.

설계 원칙:
- CharacterEvalContext: _character_score_breakdown_v2 공유 setup block에서 캐릭터-독립 값만 추출.
- CharacterEvaluator: pair별 평가 인터페이스.
- 공유 helpers: 리더 긴급상황, survival/risk 계산은 모든 evaluator가 공유하므로 여기서 제공.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class CharacterEvalContext:
    """_character_score_breakdown_v2 공유 setup 값 스냅샷.

    character_name-독립 값만 포함. 캐릭터별 값(liquidity, mark_risk 등)은
    evaluator가 policy_ref를 통해 직접 계산한다.
    """

    # ── 프로파일 ──────────────────────────────────────────────────────────────
    w: dict                # profile weights
    profile: str           # _profile_from_mode()

    # ── 이동 / 경제 ───────────────────────────────────────────────────────────
    buy_value: float
    cross_start: float
    land_f: float
    land_f_value: float

    # ── 트릭 패 ───────────────────────────────────────────────────────────────
    burden_count: int            # 짐 카드 수 (이름 기준)
    combo_names: frozenset       # trick card 이름 집합

    # ── 지목 ──────────────────────────────────────────────────────────────────
    has_marks: bool
    legal_marks: tuple           # list[PlayerState] → tuple for frozen compat

    # ── 짐/청소 context ───────────────────────────────────────────────────────
    cleanup_pressure: float
    legal_visible_burden_total: float
    legal_visible_burden_peak: float
    legal_low_cash_targets: float

    # ── 독점 context ─────────────────────────────────────────────────────────
    own_near_complete: float
    own_claimable_blocks: float
    deny_now: float
    enemy_near_complete: float
    contested_blocks: float

    # ── 사기꾼 탈취 metrics ────────────────────────────────────────────────────
    scammer: dict

    # ── 위협 평가 ─────────────────────────────────────────────────────────────
    top_threat: Any              # PlayerState | None
    top_tags: frozenset          # 예측 상대 archetypes
    exclusive_blocks: int
    placeable: bool
    leader_pressure: float
    leader_emergency: float
    leader_is_solo: bool
    leader_near_end: bool
    top_threat_cross: float
    top_threat_land_f: float
    leading: bool                # 플레이어가 선두인가

    # ── 프로파일 보조 (eager precompute) ─────────────────────────────────────
    own_land_prob: float         # _prob_land_on_placeable_own_tile (token_opt)
    token_combo_score: float     # _token_teleport_combo_score (token_opt)
    finisher_window: float       # _control_finisher_window (control)
    finisher_reason: str
    marker_plan: dict            # _leader_marker_flip_plan (doctrine)


class CharacterEvaluator(ABC):
    """캐릭터 pair 평가 인터페이스."""

    @property
    @abstractmethod
    def characters(self) -> frozenset:
        """이 evaluator가 담당하는 캐릭터 이름 집합."""
        ...

    @abstractmethod
    def score(
        self,
        state: Any,
        player: Any,
        character_name: str,
        ectx: CharacterEvalContext,
        policy_ref: Any,
    ) -> tuple[float, float, float, float, float, float, list]:
        """캐릭터 점수 컴포넌트를 반환한다.

        Returns
        -------
        (expansion, economy, disruption, meta, combo, survival, reasons)
        """
        ...


# ── 공유 헬퍼 함수 ────────────────────────────────────────────────────────────

def apply_leader_emergency(
    character_name: str,
    player: Any,
    ectx: CharacterEvalContext,
    expansion: float,
    economy: float,
    disruption: float,
    meta: float,
    combo: float,
    survival: float,
    reasons: list,
) -> tuple[float, float, float, float, float, float]:
    """리더 긴급상황 가산 공통 로직 (lines 369-386 in original)."""
    if ectx.leader_emergency > 0.0 and ectx.top_threat and ectx.top_threat.player_id != player.player_id:
        if character_name in {"자객", "산적", "추노꾼", "사기꾼", "박수", "만신", "어사"}:
            disruption += 1.55 + 0.55 * ectx.leader_emergency
            if ectx.leader_is_solo:
                disruption += 0.45
            if ectx.leader_near_end:
                disruption += 0.55
            reasons.append("emergency_leader_denial")
        if character_name in {"교리 연구관", "교리 감독관"}:
            meta += 1.45 + 0.50 * ectx.leader_emergency
            disruption += 0.35 * ectx.leader_emergency
            reasons.append("emergency_marker_denial")
        if ectx.leader_near_end and character_name in {"중매꾼", "건설업자", "객주", "파발꾼"}:
            expansion -= 0.85 + 0.25 * ectx.leader_emergency
            economy -= 0.35 * ectx.leader_emergency
            if character_name == "건설업자" and player.shards > 0:
                expansion += 0.20
            reasons.append("leader_race_deprioritized")
    return expansion, economy, disruption, meta, combo, survival


def apply_v3_priority(
    character_name: str,
    player: Any,
    state: Any,
) -> tuple[float, list]:
    """v3_claude 우선권 기반 생존 가산/감산 — 모든 캐릭터에 공통 (lines 432-463)."""
    char_priority = {
        "어사": 1, "탐관오리": 1, "자객": 2, "산적": 2, "추노꾼": 3, "탈출 노비": 3,
        "파발꾼": 4, "아전": 4, "교리 연구관": 5, "교리 감독관": 5,
        "박수": 6, "만신": 6, "객주": 7, "중매꾼": 7, "건설업자": 8, "사기꾼": 8,
    }
    my_priority = char_priority.get(character_name, 5)
    alive_lower = sum(
        1 for p in state.players
        if p.alive and p.player_id != player.player_id
        and char_priority.get(p.current_character or "", 5) > my_priority
    )
    survival = 0.0
    reasons: list = []
    if my_priority <= 3:
        survival += 0.6 + 0.10 * alive_lower
        reasons.append(f"v3_high_priority_safe(p={my_priority})")
    elif my_priority >= 7:
        survival -= 0.4 + 0.08 * alive_lower
        reasons.append(f"v3_low_priority_exposed(p={my_priority})")
    # 지목형 인물 대상 수 실측
    if character_name in {"자객", "산적", "추노꾼", "박수", "만신"}:
        mark_targets = sum(
            1 for p in state.players
            if p.alive and p.player_id != player.player_id
            and char_priority.get(p.current_character or "", 5) > my_priority
        )
        disruption_adj = 0.0
        if mark_targets >= 2:
            disruption_adj += 0.7 + 0.2 * mark_targets
            reasons.append(f"v3_mark_targets={mark_targets}")
        elif mark_targets == 1:
            disruption_adj += 0.3
            reasons.append("v3_mark_target_limited")
        else:
            disruption_adj -= 0.8
            reasons.append("v3_mark_target_none")
        return survival, disruption_adj, reasons
    return survival, 0.0, reasons


def apply_survival_risk(
    state: Any,
    player: Any,
    character_name: str,
    ectx: CharacterEvalContext,
    policy_ref: Any,
    expansion: float,
    economy: float,
    survival: float,
    reasons: list,
) -> tuple[float, float, float]:
    """어사 봉쇄/reserve_gap/liquidity/mark_risk/rent_pressure 공통 패널티 (lines 527-565).

    Returns
    -------
    (expansion, economy, survival)  — 나머지 컴포넌트는 변경 없음
    """
    from characters import CHARACTERS
    from policy_groups import RENT_ESCAPE_CHARACTERS, RENT_EXPANSION_CHARACTERS

    # 어사 봉쇄
    if policy_ref._has_uhsa_alive(state, exclude_player_id=player.player_id):
        char_info = CHARACTERS.get(character_name)
        if char_info and getattr(char_info, "attribute", None) == "무뢰":
            survival -= 1.8
            reasons.append("uhsa_blocks_muroe")

    # 유동성 리스크
    liquidity = policy_ref._liquidity_risk_metrics(state, player, character_name)
    reserve_gap = max(0.0, liquidity["reserve"] - player.cash)
    if reserve_gap > 0.0:
        survival -= 0.55 * reserve_gap
        reasons.append(f"cash_dry={reserve_gap:.2f}")

    if ectx.profile == "control":
        if reserve_gap > 0.0 and character_name in {"자객", "산적", "추노꾼"}:
            # disruption은 호출자가 조정 불가 (immutable return scope 밖) → 여기서 반영 안 함
            # 대신 survival만 (disruption 조정은 각 evaluator에서 profile==control 블록으로 처리)
            survival -= 0.20 * reserve_gap
        if reserve_gap <= 1.0 and character_name in {"사기꾼", "객주", "파발꾼", "탈출 노비"}:
            survival += 0.20
            economy += 0.15
            reasons.append("control_low_cost_stability")

    if character_name in RENT_ESCAPE_CHARACTERS:
        survival += 0.22 * liquidity["expected_loss"] + 0.10 * liquidity["worst_loss"]
        reasons.append("liquidity_escape_value")

    if character_name in RENT_EXPANSION_CHARACTERS and reserve_gap > 0.0:
        expansion -= 0.45 * reserve_gap
        survival -= 0.25 * reserve_gap
        reasons.append("expansion_cash_drag")

    if character_name in {"박수", "만신", "객주"} and liquidity["own_burden_cost"] > 0.0:
        survival += 0.25 * liquidity["own_burden_cost"]
        reasons.append("burden_liquidity_cover")

    # 지목 리스크
    mark_risk, mark_reasons = policy_ref._public_mark_risk_breakdown(state, player, character_name)
    if mark_risk > 0.0:
        survival -= mark_risk
        reasons.append(f"mark_risk={mark_risk:.2f}")
        reasons.extend(mark_reasons)

    # 임대료 압박
    rent_pressure, rent_reasons = policy_ref._rent_pressure_breakdown(state, player, character_name)
    if rent_pressure > 0.0:
        rent_economy, rent_combo, rent_survival = policy_ref._apply_rent_pressure_adjustment_v2(
            state, player, character_name, ectx.cross_start, ectx.land_f, rent_pressure, reasons
        )
        economy += rent_economy
        survival += rent_survival
        reasons.append(f"rent_pressure={rent_pressure:.2f}")
        reasons.extend(rent_reasons)

    return expansion, economy, survival
