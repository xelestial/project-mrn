from __future__ import annotations


def test_turn_frame_handler_registry_covers_native_turn_modules():
    from runtime_modules.handlers.turn import TURN_FRAME_HANDLERS

    assert {
        "TurnStartModule",
        "ScheduledStartActionsModule",
        "PendingMarkResolutionModule",
        "CharacterStartModule",
        "TrickWindowModule",
        "DiceRollModule",
    } <= set(TURN_FRAME_HANDLERS)
