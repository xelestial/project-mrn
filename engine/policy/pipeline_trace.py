from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DetectorHit:
    key: str
    kind: str
    severity: float
    confidence: float
    reason: str
    tags: tuple[str, ...] = ()
    score_delta: float = 0.0


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    decision_type: str
    features: dict[str, object]
    detector_hits: tuple[DetectorHit, ...]
    effect_adjustments: tuple[dict[str, object], ...]
    final_choice: object


def build_detector_hit(
    key: str,
    *,
    kind: str,
    severity: float,
    confidence: float,
    reason: str,
    tags: tuple[str, ...] = (),
    score_delta: float = 0.0,
) -> DetectorHit:
    return DetectorHit(
        key=key,
        kind=kind,
        severity=float(severity),
        confidence=float(confidence),
        reason=reason,
        tags=tuple(tags),
        score_delta=float(score_delta),
    )


def _normalize_trace_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, DetectorHit):
        return {
            "key": value.key,
            "kind": value.kind,
            "severity": round(value.severity, 3),
            "confidence": round(value.confidence, 3),
            "reason": value.reason,
            "tags": list(value.tags),
            "score_delta": round(value.score_delta, 3),
        }
    if isinstance(value, DecisionTrace):
        return build_decision_trace_payload(value)
    if isinstance(value, dict):
        return {str(key): _normalize_trace_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_trace_value(inner) for inner in value]
    return value


def build_decision_trace_payload(trace: DecisionTrace) -> dict[str, object]:
    return {
        "decision_type": trace.decision_type,
        "features": _normalize_trace_value(trace.features),
        "detector_hits": _normalize_trace_value(trace.detector_hits),
        "effect_adjustments": _normalize_trace_value(trace.effect_adjustments),
        "final_choice": _normalize_trace_value(trace.final_choice),
    }
