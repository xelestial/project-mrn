from __future__ import annotations


def test_sequence_handler_registry_covers_trick_modules_and_payload_boundaries() -> None:
    from runtime_modules.handlers.sequence import SEQUENCE_FRAME_HANDLERS, SEQUENCE_PAYLOAD_HANDLERS
    from runtime_modules.catalog import MODULE_RULES
    from runtime_modules.sequence_modules import ACTION_SEQUENCE_MODULE_TYPES, TRICK_SEQUENCE_MODULE_TYPES

    forbidden_adapter_module = "".join(("Leg", "acy", "ActionAdapterModule"))
    assert set(TRICK_SEQUENCE_MODULE_TYPES) <= set(SEQUENCE_FRAME_HANDLERS)
    assert set(ACTION_SEQUENCE_MODULE_TYPES) <= set(SEQUENCE_FRAME_HANDLERS)
    assert forbidden_adapter_module not in MODULE_RULES
    assert forbidden_adapter_module not in ACTION_SEQUENCE_MODULE_TYPES
    assert forbidden_adapter_module not in SEQUENCE_FRAME_HANDLERS
    assert "action" not in SEQUENCE_PAYLOAD_HANDLERS
    assert "pending_turn_completion" not in SEQUENCE_PAYLOAD_HANDLERS


def test_native_action_sequence_handler_uses_native_module_boundary() -> None:
    from runtime_modules.contracts import FrameState, ModuleRef
    from runtime_modules.handlers.sequence import SEQUENCE_FRAME_HANDLERS, SequenceFrameHandlerContext

    calls: list[tuple[str, str]] = []

    class Runner:
        def _advance_native_action_module(self, engine, state, frame, module):
            calls.append(("native", module.module_type))
            return {"status": "committed", "module_type": module.module_type}

        def _advance_action_adapter_module(self, engine, state, frame, module):
            raise AssertionError("native action module must not use adapter boundary")

    frame = FrameState(frame_id="seq:action:1:p0", frame_type="sequence", owner_player_id=0, parent_frame_id=None)
    module = ModuleRef(
        module_id="mod:seq:action:1:p0:move",
        module_type="MapMoveModule",
        phase="turn_action",
        owner_player_id=0,
        payload={"action": {"type": "apply_move"}},
    )

    result = SEQUENCE_FRAME_HANDLERS["MapMoveModule"](
        SequenceFrameHandlerContext(runner=Runner(), engine=object(), state=object(), frame=frame, module=module)
    )

    assert result == {"status": "committed", "module_type": "MapMoveModule"}
    assert calls == [("native", "MapMoveModule")]
