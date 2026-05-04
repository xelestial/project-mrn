from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import FrameState, ModuleRef
from ..simultaneous import SIMULTANEOUS_MODULE_TYPES


@dataclass(slots=True)
class SimultaneousFrameHandlerContext:
    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef
    decision_resume: Any | None = None


SimultaneousFrameHandler = Callable[[SimultaneousFrameHandlerContext], dict[str, Any]]


def handle_resupply(ctx: SimultaneousFrameHandlerContext) -> dict[str, Any]:
    return ctx.runner._advance_resupply_module(
        ctx.engine,
        ctx.state,
        ctx.frame,
        ctx.module,
        decision_resume=ctx.decision_resume,
    )


def handle_simultaneous_step(ctx: SimultaneousFrameHandlerContext) -> dict[str, Any]:
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type, "frame_id": ctx.frame.frame_id}


def handle_complete_simultaneous(ctx: SimultaneousFrameHandlerContext) -> dict[str, Any]:
    result = handle_simultaneous_step(ctx)
    ctx.frame.status = "completed"
    return result


SIMULTANEOUS_FRAME_HANDLERS: dict[str, SimultaneousFrameHandler] = {
    module_type: handle_simultaneous_step for module_type in SIMULTANEOUS_MODULE_TYPES
}
SIMULTANEOUS_FRAME_HANDLERS["ResupplyModule"] = handle_resupply
SIMULTANEOUS_FRAME_HANDLERS["CompleteSimultaneousResolutionModule"] = handle_complete_simultaneous

