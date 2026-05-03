from __future__ import annotations


def test_hostile_mark_characters_are_declared_as_target_judicator_effects():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, hostile_mark_effects

    by_name = {entry.source_name: entry for entry in hostile_mark_effects(EFFECT_INVENTORY)}

    assert {"자객", "산적", "추노꾼", "박수", "만신"} <= set(by_name)
    for entry in by_name.values():
        assert entry.producer_module == "CharacterStartModule"
        assert "TargetJudicatorModule" in entry.consumer_modules
        assert entry.prompt_contract == "mark_target"
        assert "PromptContinuation" in entry.redis_resume_contracts


def test_eosa_declares_muroe_suppression_as_character_start_modifier():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, effect_by_id
    from runtime_modules.modifiers import MUROE_SKILL_SUPPRESSION_KIND

    entry = effect_by_id(EFFECT_INVENTORY, "character:eosa:suppress_muroe")

    assert entry.source_name == "어사"
    assert entry.producer_module == "CharacterModifierSeedModule"
    assert "CharacterStartModule" in entry.consumer_modules
    assert entry.modifier_kind == MUROE_SKILL_SUPPRESSION_KIND


def test_trick_fortune_and_resupply_effects_have_explicit_frame_contracts():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, effect_by_id

    trick = effect_by_id(EFFECT_INVENTORY, "trick:sequence")
    assert trick.frame_kind == "sequence"
    assert trick.producer_module == "TrickWindowModule"
    assert {"TrickChoiceModule", "TrickResolveModule"} <= set(trick.consumer_modules)
    assert "PromptContinuation" in trick.redis_resume_contracts

    fortune = effect_by_id(EFFECT_INVENTORY, "fortune:extra_arrival")
    assert fortune.frame_kind == "sequence"
    assert fortune.producer_module == "FortuneResolveModule"
    assert {"MapMoveModule", "ArrivalTileModule"} <= set(fortune.consumer_modules)

    resupply = effect_by_id(EFFECT_INVENTORY, "simultaneous:resupply")
    assert resupply.frame_kind == "simultaneous"
    assert resupply.producer_module == "ConcurrentResolutionSchedulerModule"
    assert resupply.consumer_modules == ("ResupplyModule",)
    assert resupply.prompt_contract == "burden_exchange"
    assert "SimultaneousPromptBatchContinuation" in resupply.redis_resume_contracts


def test_effect_inventory_resolves_to_known_module_boundaries():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, validate_effect_inventory

    assert validate_effect_inventory(EFFECT_INVENTORY) == []


def test_effect_inventory_runtime_boundaries_have_handlers_or_adapters():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, runtime_handler_coverage_errors

    assert runtime_handler_coverage_errors(EFFECT_INVENTORY) == []
