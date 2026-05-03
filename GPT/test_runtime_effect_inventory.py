from __future__ import annotations


def test_hostile_mark_characters_are_declared_as_target_judicator_effects():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, hostile_mark_effects

    by_name = {entry.source_name: entry for entry in hostile_mark_effects(EFFECT_INVENTORY)}

    assert {"자객", "산적", "추노꾼", "박수", "만신"} <= set(by_name)
    for entry in by_name.values():
        assert entry.producer_module == "CharacterStartModule"
        assert "TargetJudicatorModule" in entry.consumer_modules
        assert "TargetJudicatorModule" in entry.runtime_boundary_modules
        assert entry.prompt_contract == "mark_target"
        assert "PromptContinuation" in entry.redis_resume_contracts
    assert "ImmediateMarkerTransferModule" in by_name["자객"].runtime_boundary_modules
    assert "PendingMarkResolutionModule" in by_name["산적"].runtime_boundary_modules


def test_eosa_declares_muroe_suppression_as_character_start_modifier():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, effect_by_id
    from runtime_modules.modifiers import MUROE_SKILL_SUPPRESSION_KIND

    entry = effect_by_id(EFFECT_INVENTORY, "character:eosa:suppress_muroe")

    assert entry.source_name == "어사"
    assert entry.producer_module == "CharacterModifierSeedModule"
    assert "CharacterStartModule" in entry.consumer_modules
    assert "TargetJudicatorModule" in entry.consumer_modules
    assert entry.modifier_kind == MUROE_SKILL_SUPPRESSION_KIND


def test_native_character_modifiers_are_declared_in_effect_inventory():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, effect_by_id
    from runtime_modules.modifiers import BUILDER_FREE_PURCHASE_KIND, PABAL_DICE_MODIFIER_KIND

    pabal = effect_by_id(EFFECT_INVENTORY, "character:pabalggun:dice_modifier")
    assert pabal.producer_module == "CharacterStartModule"
    assert pabal.consumer_modules == ("DiceRollModule",)
    assert pabal.modifier_kind == PABAL_DICE_MODIFIER_KIND
    assert pabal.frame_kind == "turn"

    builder = effect_by_id(EFFECT_INVENTORY, "character:builder:free_purchase")
    assert builder.producer_module == "CharacterStartModule"
    assert builder.consumer_modules == ("PurchaseDecisionModule", "PurchaseCommitModule")
    assert builder.modifier_kind == BUILDER_FREE_PURCHASE_KIND
    assert builder.frame_kind == "sequence"


def test_character_ability_inventory_covers_all_character_cards():
    from characters import CHARACTERS
    from runtime_modules.effect_inventory import EFFECT_INVENTORY

    declared_sources = {
        entry.source_name
        for entry in EFFECT_INVENTORY
        if entry.effect_id.startswith("character:")
    }

    assert set(CHARACTERS) <= declared_sources


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


def test_effect_inventory_validation_rejects_prompt_without_resume_boundary():
    from runtime_modules.effect_inventory import EffectInventoryEntry, validate_effect_inventory

    errors = validate_effect_inventory(
        (
            EffectInventoryEntry(
                effect_id="test:prompt_without_resume",
                source_name="테스트",
                producer_module="CharacterStartModule",
                consumer_modules=("CharacterStartModule",),
                frame_kind="turn",
                prompt_contract="choose_test",
                runtime_boundary_modules=("CharacterStartModule",),
            ),
        )
    )

    assert "test:prompt_without_resume: prompt contract requires a Redis resume contract" in errors


def test_effect_inventory_validation_rejects_legacy_adapter_boundaries():
    from runtime_modules.effect_inventory import EffectInventoryEntry, validate_effect_inventory

    errors = validate_effect_inventory(
        (
            EffectInventoryEntry(
                effect_id="test:legacy_adapter",
                source_name="테스트",
                producer_module="CharacterStartModule",
                consumer_modules=("CharacterStartModule",),
                frame_kind="turn",
                runtime_boundary_modules=("LegacyActionAdapterModule",),
            ),
        )
    )

    assert "test:legacy_adapter: native effect inventory must not use LegacyActionAdapterModule" in errors


def test_prompt_effect_inventory_entries_are_resumable_module_boundaries():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY

    prompt_entries = [entry for entry in EFFECT_INVENTORY if entry.prompt_contract]
    assert prompt_entries
    for entry in prompt_entries:
        assert entry.redis_resume_contracts
        assert entry.runtime_boundary_modules
        assert "LegacyActionAdapterModule" not in entry.runtime_boundary_modules


def test_native_runtime_effects_do_not_depend_on_legacy_action_adapter_boundaries():
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, effect_by_id

    native_effect_ids = (
        "character:bandit:mark_target",
        "character:eosa:suppress_muroe",
        "character:pabalggun:dice_modifier",
        "character:builder:free_purchase",
        "trick:sequence",
        "fortune:extra_arrival",
        "simultaneous:resupply",
    )

    for effect_id in native_effect_ids:
        entry = effect_by_id(EFFECT_INVENTORY, effect_id)
        assert "LegacyActionAdapterModule" not in entry.runtime_boundary_modules
