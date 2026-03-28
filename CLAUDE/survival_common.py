"""survival_common — 하위 호환 re-export shim.

모든 심볼은 policy/survival/ 서브패키지로 이전됨.
기존 임포트(from survival_common import ...)는 그대로 동작한다.
"""
from policy.survival.thresholds import SurvivalThresholdSpec, _load_default_thresholds, _T
from policy.survival.signals import SurvivalSignals
from policy.survival.guards import (
    ActionGuardContext,
    SwindleGuardDecision,
    build_action_guard_context,
    is_action_survivable,
    swindle_operating_reserve,
    evaluate_swindle_guard,
)
from policy.survival.orchestrator import (
    SurvivalOrchestratorState,
    build_survival_orchestrator,
    CharacterSurvivalAdvice,
    CleanupStrategyContext,
    evaluate_character_survival_advice,
    evaluate_character_survival_priority,
)

__all__ = [
    "SurvivalThresholdSpec", "_load_default_thresholds", "_T",
    "SurvivalSignals",
    "ActionGuardContext", "SwindleGuardDecision",
    "build_action_guard_context", "is_action_survivable",
    "swindle_operating_reserve", "evaluate_swindle_guard",
    "SurvivalOrchestratorState", "build_survival_orchestrator",
    "CharacterSurvivalAdvice", "CleanupStrategyContext",
    "evaluate_character_survival_advice", "evaluate_character_survival_priority",
]
