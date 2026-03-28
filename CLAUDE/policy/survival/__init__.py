"""policy/survival — 생존 평가 서브패키지."""
from .thresholds import SurvivalThresholdSpec, _T
from .signals import SurvivalSignals
from .guards import (
    ActionGuardContext,
    SwindleGuardDecision,
    build_action_guard_context,
    is_action_survivable,
    swindle_operating_reserve,
    evaluate_swindle_guard,
)
from .orchestrator import (
    SurvivalOrchestratorState,
    build_survival_orchestrator,
    CharacterSurvivalAdvice,
    CleanupStrategyContext,
    evaluate_character_survival_advice,
    evaluate_character_survival_priority,
)
from .strategy import SurvivalStrategy, SurvivalAssessment, DefaultSurvivalStrategy, V3ClaudeSurvivalStrategy

__all__ = [
    "SurvivalThresholdSpec", "_T",
    "SurvivalSignals",
    "ActionGuardContext", "SwindleGuardDecision",
    "build_action_guard_context", "is_action_survivable",
    "swindle_operating_reserve", "evaluate_swindle_guard",
    "SurvivalOrchestratorState", "build_survival_orchestrator",
    "CharacterSurvivalAdvice", "CleanupStrategyContext",
    "evaluate_character_survival_advice", "evaluate_character_survival_priority",
    "SurvivalStrategy", "SurvivalAssessment",
    "DefaultSurvivalStrategy", "V3ClaudeSurvivalStrategy",
]
