from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .modifiers import MUROE_SKILL_SUPPRESSION_KIND


@dataclass(frozen=True, slots=True)
class EffectInventoryEntry:
    effect_id: str
    source_name: str
    producer_module: str
    consumer_modules: tuple[str, ...]
    frame_kind: str
    prompt_contract: str | None = None
    redis_resume_contracts: tuple[str, ...] = ()
    modifier_kind: str | None = None
    runtime_boundary_modules: tuple[str, ...] = ()
    notes: str = ""


EFFECT_INVENTORY: tuple[EffectInventoryEntry, ...] = (
    EffectInventoryEntry(
        effect_id="character:assassin:mark_target",
        source_name="자객",
        producer_module="CharacterStartModule",
        consumer_modules=("TargetJudicatorModule", "ImmediateMarkerTransferModule"),
        frame_kind="turn",
        prompt_contract="mark_target",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("CharacterStartModule", "TargetJudicatorModule", "ImmediateMarkerTransferModule"),
        notes="인물 시작 능력이 지목 판정자로 넘어가고, 지목 결과는 즉시 마커 이전 큐로 물질화된다.",
    ),
    EffectInventoryEntry(
        effect_id="character:bandit:mark_target",
        source_name="산적",
        producer_module="CharacterStartModule",
        consumer_modules=("TargetJudicatorModule", "PendingMarkResolutionModule"),
        frame_kind="turn",
        prompt_contract="mark_target",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("CharacterStartModule", "TargetJudicatorModule", "PendingMarkResolutionModule"),
        notes="잔꾀 재개 이후에도 CharacterStartModule이 다시 실행되지 않고 기존 지목 결과만 소비되어야 한다.",
    ),
    EffectInventoryEntry(
        effect_id="character:chuno:mark_target",
        source_name="추노꾼",
        producer_module="CharacterStartModule",
        consumer_modules=("TargetJudicatorModule", "PendingMarkResolutionModule"),
        frame_kind="turn",
        prompt_contract="mark_target",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("CharacterStartModule", "TargetJudicatorModule", "PendingMarkResolutionModule"),
    ),
    EffectInventoryEntry(
        effect_id="character:baksu:mark_target",
        source_name="박수",
        producer_module="CharacterStartModule",
        consumer_modules=("TargetJudicatorModule", "PendingMarkResolutionModule"),
        frame_kind="turn",
        prompt_contract="mark_target",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("CharacterStartModule", "TargetJudicatorModule", "PendingMarkResolutionModule"),
    ),
    EffectInventoryEntry(
        effect_id="character:mansin:mark_target",
        source_name="만신",
        producer_module="CharacterStartModule",
        consumer_modules=("TargetJudicatorModule", "PendingMarkResolutionModule"),
        frame_kind="turn",
        prompt_contract="mark_target",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("CharacterStartModule", "TargetJudicatorModule", "PendingMarkResolutionModule"),
    ),
    EffectInventoryEntry(
        effect_id="character:eosa:suppress_muroe",
        source_name="어사",
        producer_module="CharacterModifierSeedModule",
        consumer_modules=("CharacterStartModule", "TargetJudicatorModule"),
        frame_kind="turn",
        modifier_kind=MUROE_SKILL_SUPPRESSION_KIND,
        runtime_boundary_modules=("CharacterModifierSeedModule", "CharacterStartModule", "TargetJudicatorModule"),
        notes="무뢰 계열 인물 시작 모듈에 능력 억제 modifier를 심어 비교문 분기 대신 효과 흐름으로 차단한다.",
    ),
    EffectInventoryEntry(
        effect_id="trick:sequence",
        source_name="잔꾀",
        producer_module="TrickWindowModule",
        consumer_modules=("TrickChoiceModule", "TrickResolveModule"),
        frame_kind="sequence",
        prompt_contract="trick_choice",
        redis_resume_contracts=("PromptContinuation",),
        runtime_boundary_modules=("TrickWindowModule", "TrickChoiceModule", "TrickResolveModule"),
        notes="턴 프레임의 자식 시퀀스에서만 선택/해결/후속 선택이 반복된다.",
    ),
    EffectInventoryEntry(
        effect_id="fortune:extra_arrival",
        source_name="운수",
        producer_module="FortuneResolveModule",
        consumer_modules=("MapMoveModule", "ArrivalTileModule"),
        frame_kind="sequence",
        redis_resume_contracts=("ActionSequenceFrame",),
        runtime_boundary_modules=("FortuneResolveModule", "MapMoveModule", "ArrivalTileModule"),
        notes="운수 결과가 추가 이동/도착 액션을 생성해도 새 턴이 아니라 현재 액션 시퀀스에 붙는다.",
    ),
    EffectInventoryEntry(
        effect_id="simultaneous:resupply",
        source_name="재보급",
        producer_module="ConcurrentResolutionSchedulerModule",
        consumer_modules=("ResupplyModule",),
        frame_kind="simultaneous",
        prompt_contract="burden_exchange",
        redis_resume_contracts=("SimultaneousPromptBatchContinuation",),
        runtime_boundary_modules=("ConcurrentResolutionSchedulerModule", "ResupplyModule"),
        notes="모든 대상 플레이어의 응답이 모일 때까지 동일 batch continuation을 유지한다.",
    ),
)


VIRTUAL_EFFECT_MODULE_FRAME_KINDS: dict[str, frozenset[str]] = {
    "CharacterModifierSeedModule": frozenset({"turn"}),
    "ConcurrentResolutionSchedulerModule": frozenset({"simultaneous"}),
}

MODIFIER_EFFECT_MODULES = frozenset({"CharacterModifierSeedModule"})
SCHEDULER_EFFECT_MODULES = frozenset({"ConcurrentResolutionSchedulerModule"})


def effect_by_id(inventory: Iterable[EffectInventoryEntry], effect_id: str) -> EffectInventoryEntry:
    for entry in inventory:
        if entry.effect_id == effect_id:
            return entry
    raise KeyError(effect_id)


def hostile_mark_effects(inventory: Iterable[EffectInventoryEntry]) -> tuple[EffectInventoryEntry, ...]:
    return tuple(entry for entry in inventory if entry.prompt_contract == "mark_target")


def validate_effect_inventory(inventory: Iterable[EffectInventoryEntry]) -> list[str]:
    from .catalog import MODULE_RULES

    errors: list[str] = []
    for entry in inventory:
        if entry.frame_kind not in {"round", "turn", "sequence", "simultaneous"}:
            errors.append(f"{entry.effect_id}: unknown frame_kind {entry.frame_kind!r}")
        for role, module_type in _declared_modules(entry):
            frame_kinds = _declared_frame_kinds(module_type, MODULE_RULES)
            if frame_kinds is None:
                errors.append(f"{entry.effect_id}: unknown {role} module {module_type}")
                continue
            if role == "consumer" and entry.frame_kind not in frame_kinds:
                allowed = ", ".join(sorted(frame_kinds))
                errors.append(
                    f"{entry.effect_id}: {role} module {module_type} is not valid in "
                    f"{entry.frame_kind} frame; allowed: {allowed}"
                )
    return errors


def runtime_handler_coverage_errors(inventory: Iterable[EffectInventoryEntry]) -> list[str]:
    from .handlers.sequence import SEQUENCE_FRAME_HANDLERS
    from .handlers.simultaneous import SIMULTANEOUS_FRAME_HANDLERS
    from .handlers.turn import TURN_FRAME_HANDLERS
    from .sequence_modules import ACTION_SEQUENCE_MODULE_TYPES, TURN_COMPLETION_MODULE_TYPES

    errors: list[str] = []
    for entry in inventory:
        for module_type in entry.runtime_boundary_modules:
            if module_type in MODIFIER_EFFECT_MODULES or module_type in SCHEDULER_EFFECT_MODULES:
                continue
            covered = (
                module_type in TURN_FRAME_HANDLERS
                or module_type in SEQUENCE_FRAME_HANDLERS
                or module_type in SIMULTANEOUS_FRAME_HANDLERS
                or module_type in ACTION_SEQUENCE_MODULE_TYPES
                or module_type in TURN_COMPLETION_MODULE_TYPES
            )
            if not covered:
                errors.append(f"{entry.effect_id}: runtime boundary {module_type} has no handler or adapter")
    return errors


def _declared_modules(entry: EffectInventoryEntry) -> tuple[tuple[str, str], ...]:
    return (
        ("producer", entry.producer_module),
        *tuple(("consumer", module_type) for module_type in entry.consumer_modules),
        *tuple(("runtime_boundary", module_type) for module_type in entry.runtime_boundary_modules),
    )


def _declared_frame_kinds(module_type: str, module_rules: dict) -> frozenset[str] | None:
    if module_type in VIRTUAL_EFFECT_MODULE_FRAME_KINDS:
        return VIRTUAL_EFFECT_MODULE_FRAME_KINDS[module_type]
    rule = module_rules.get(module_type)
    if rule is None:
        return None
    return frozenset(str(frame_type) for frame_type in rule.frame_types)
