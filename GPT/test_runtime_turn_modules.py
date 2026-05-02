from __future__ import annotations

from runtime_modules.turn_modules import TURN_MODULE_TYPES, build_turn_frame, build_turn_module


def test_turn_frame_default_order() -> None:
    frame = build_turn_frame(1, 0, parent_module_id="mod:round:1:player_turn_p0_0")

    assert frame.frame_type == "turn"
    assert [module.module_type for module in frame.module_queue] == [
        module_type for module_type in TURN_MODULE_TYPES if module_type != "ImmediateMarkerTransferModule"
    ]
    assert frame.module_queue[-1].module_type == "TurnEndSnapshotModule"


def test_immediate_marker_transfer_is_separate_turn_module() -> None:
    module = build_turn_module(2, 1, "ImmediateMarkerTransferModule")

    assert module.module_type == "ImmediateMarkerTransferModule"
    assert module.phase == "immediatemarkertransfer"
    assert "turn" in module.module_id


def test_card_flip_not_reachable_from_turn_frame_modules() -> None:
    frame = build_turn_frame(1, 0, parent_module_id="mod:round:1:player_turn_p0_0")

    assert "RoundEndCardFlipModule" not in {module.module_type for module in frame.module_queue}
