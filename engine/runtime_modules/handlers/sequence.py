from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import FrameState, ModuleRef
from ..sequence_modules import ACTION_SEQUENCE_MODULE_TYPES, TRICK_SEQUENCE_MODULE_TYPES


@dataclass(slots=True)
class SequenceFrameHandlerContext:
    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef


SequenceFrameHandler = Callable[[SequenceFrameHandlerContext], dict[str, Any]]


def handle_trick_sequence(ctx: SequenceFrameHandlerContext) -> dict[str, Any]:
    if isinstance(ctx.module.payload.get("action"), dict):
        return ctx.runner._advance_native_action_module(ctx.engine, ctx.state, ctx.frame, ctx.module)
    return ctx.runner._advance_trick_sequence_module(ctx.engine, ctx.state, ctx.frame, ctx.module)


def handle_native_action(ctx: SequenceFrameHandlerContext) -> dict[str, Any]:
    return ctx.runner._advance_native_action_module(ctx.engine, ctx.state, ctx.frame, ctx.module)


def handle_fortune_resolve(ctx: SequenceFrameHandlerContext) -> dict[str, Any]:
    return handle_native_action(ctx)


def handle_default_sequence(ctx: SequenceFrameHandlerContext) -> dict[str, Any]:
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    ctx.runner._complete_sequence_frame_if_drained(ctx.frame)
    return {"status": "committed", "module_type": ctx.module.module_type, "frame_id": ctx.frame.frame_id}


SEQUENCE_FRAME_HANDLERS: dict[str, SequenceFrameHandler] = {
    module_type: handle_trick_sequence for module_type in TRICK_SEQUENCE_MODULE_TYPES
}
SEQUENCE_FRAME_HANDLERS.update({module_type: handle_native_action for module_type in ACTION_SEQUENCE_MODULE_TYPES})
SEQUENCE_FRAME_HANDLERS["FortuneResolveModule"] = handle_fortune_resolve

SEQUENCE_PAYLOAD_HANDLERS: dict[str, SequenceFrameHandler] = {}
