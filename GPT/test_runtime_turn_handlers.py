from __future__ import annotations

from types import SimpleNamespace

from runtime_modules.contracts import ModifierRegistryState
from runtime_modules.handlers.turn import TurnFrameHandlerContext, handle_character_start, handle_dice_roll
from runtime_modules.modifiers import (
    BUILDER_FREE_PURCHASE_KIND,
    PABAL_DICE_MODIFIER_KIND,
)
from runtime_modules.runner import ModuleRunner
from runtime_modules.turn_modules import build_turn_frame


def test_turn_frame_handler_registry_covers_native_turn_modules():
    from runtime_modules.handlers.turn import TURN_FRAME_HANDLERS

    assert {
        "TurnStartModule",
        "ScheduledStartActionsModule",
        "PendingMarkResolutionModule",
        "CharacterStartModule",
        "TargetJudicatorModule",
        "ImmediateMarkerTransferModule",
        "TrickWindowModule",
        "DiceRollModule",
    } <= set(TURN_FRAME_HANDLERS)


def test_character_start_seeds_pabal_dice_modifier_without_legacy_mutation():
    class Engine:
        _vis_session_id = "test-session"

        def __init__(self):
            self.called_legacy = False
            self.policy = SimpleNamespace(choose_pabal_dice_mode=lambda _state, _player: "minus_one")
            self.logs = []

        def _apply_character_start(self, _state, _player):
            self.called_legacy = True

        def _log(self, event):
            self.logs.append(dict(event))

    state = SimpleNamespace(
        current_weather_effects=[],
        runtime_modifier_registry=ModifierRegistryState(),
        runtime_module_journal=[],
        rounds_completed=0,
    )
    player = SimpleNamespace(
        player_id=0,
        alive=True,
        current_character="파발꾼",
        shards=8,
        extra_dice_count_this_turn=0,
        trick_dice_delta_this_turn=0,
    )
    frame = build_turn_frame(1, 0, parent_module_id="round:1:p0")
    module = next(item for item in frame.module_queue if item.module_type == "CharacterStartModule")
    engine = Engine()

    result = handle_character_start(
        TurnFrameHandlerContext(
            runner=ModuleRunner(),
            engine=engine,
            state=state,
            frame=frame,
            module=module,
            player_id=0,
            player=player,
        )
    )

    assert result["module_type"] == "CharacterStartModule"
    assert engine.called_legacy is False
    assert player.extra_dice_count_this_turn == 0
    assert player.trick_dice_delta_this_turn == 0
    [modifier] = state.runtime_modifier_registry.modifiers
    assert modifier.payload["kind"] == PABAL_DICE_MODIFIER_KIND
    assert modifier.payload["dice_delta"] == -1
    assert modifier.target_module_type == "DiceRollModule"
    assert modifier.owner_player_id == 0


def test_dice_roll_consumes_pabal_dice_modifier_before_turn_resolution():
    class Engine:
        def _finish_turn_after_trick_phase(self, state, player, *, finisher_before, disruption_before):
            del state, finisher_before, disruption_before
            self.extra_seen = player.extra_dice_count_this_turn
            self.delta_seen = player.trick_dice_delta_this_turn

    state = SimpleNamespace(
        current_weather_effects=[],
        pending_actions=[],
        pending_turn_completion={},
        runtime_modifier_registry=ModifierRegistryState(),
        runtime_module_journal=[],
    )
    player = SimpleNamespace(
        player_id=0,
        alive=True,
        current_character="파발꾼",
        extra_dice_count_this_turn=0,
        trick_dice_delta_this_turn=0,
    )
    frame = build_turn_frame(1, 0, parent_module_id="round:1:p0")
    character_module = next(item for item in frame.module_queue if item.module_type == "CharacterStartModule")
    dice_module = next(item for item in frame.module_queue if item.module_type == "DiceRollModule")
    runner = ModuleRunner()
    engine = Engine()

    handle_character_start(
        TurnFrameHandlerContext(
            runner=runner,
            engine=SimpleNamespace(
                _vis_session_id="test-session",
                policy=SimpleNamespace(choose_pabal_dice_mode=lambda _state, _player: "plus_one"),
                _apply_character_start=lambda _state, _player: None,
                _log=lambda _event: None,
            ),
            state=state,
            frame=frame,
            module=character_module,
            player_id=0,
            player=player,
        )
    )

    result = handle_dice_roll(
        TurnFrameHandlerContext(
            runner=runner,
            engine=engine,
            state=state,
            frame=frame,
            module=dice_module,
            player_id=0,
            player=player,
        )
    )

    assert result["module_type"] == "DiceRollModule"
    assert engine.extra_seen == 1
    assert engine.delta_seen == 0
    assert all(modifier.consumed for modifier in state.runtime_modifier_registry.modifiers)


def test_character_start_seeds_builder_purchase_modifier_without_legacy_mutation():
    class Engine:
        _vis_session_id = "test-session"

        def __init__(self):
            self.called_legacy = False
            self.policy = SimpleNamespace()
            self.logs = []

        def _apply_character_start(self, _state, _player):
            self.called_legacy = True

        def _log(self, event):
            self.logs.append(dict(event))

    state = SimpleNamespace(
        current_weather_effects=[],
        runtime_modifier_registry=ModifierRegistryState(),
        runtime_module_journal=[],
        rounds_completed=0,
    )
    player = SimpleNamespace(
        player_id=0,
        alive=True,
        current_character="건설업자",
        shards=0,
        free_purchase_this_turn=False,
    )
    frame = build_turn_frame(1, 0, parent_module_id="round:1:p0")
    module = next(item for item in frame.module_queue if item.module_type == "CharacterStartModule")
    engine = Engine()

    handle_character_start(
        TurnFrameHandlerContext(
            runner=ModuleRunner(),
            engine=engine,
            state=state,
            frame=frame,
            module=module,
            player_id=0,
            player=player,
        )
    )

    assert engine.called_legacy is False
    assert player.free_purchase_this_turn is False
    [modifier] = state.runtime_modifier_registry.modifiers
    assert modifier.payload["kind"] == BUILDER_FREE_PURCHASE_KIND
    assert modifier.target_module_type == "PurchaseDecisionModule"
    assert "PurchaseCommitModule" in modifier.propagation
