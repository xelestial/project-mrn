from __future__ import annotations

"""PolicyProfileSpec — 프로파일 설정 데이터 객체.

설계 원칙:
- 해석 로직(overlap kill 판단, lap engine 등)은 포함하지 않는다.
- 값(weights, character_values, strategy keys)만 담는다.
- strategy 참조는 registry key 문자열로만 한다.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PolicyProfileSpec:
    """프로파일 설정 전용 데이터 객체. 해석 로직 없음."""

    name: str
    """canonical profile 이름. 로그/summary에 기록되는 공식 식별자."""

    aliases: tuple[str, ...] = ()
    """하위 호환용 alias 목록. registry에서만 해석한다."""

    weights: dict[str, float] = field(default_factory=dict)
    """6축 가중치: expansion, economy, disruption, meta, combo, survival."""

    character_values: dict[str, float] = field(default_factory=dict)
    """16인물 base score."""

    options: dict[str, Any] = field(default_factory=dict)
    """프로파일별 추가 옵션 (예: v3_claude 전용 임계값 오버라이드)."""

    # strategy registry key 참조 — 클래스명 직접 참조 금지
    survival_strategy_key: str = "survival/default_v1"
    lap_reward_strategy_key: str = "lap_reward/base_v1"
    purchase_gate_strategy_key: str = "purchase_gate/base_v1"
    draft_strategy_key: str = "draft/base_v1"
