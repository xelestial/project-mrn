from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import FrameState, ModuleRef
from ..round_modules import ROUND_MODULE_TYPES, assert_round_end_card_flip_ready


@dataclass(slots=True)
class RoundFrameHandlerContext:
    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef


RoundFrameHandler = Callable[[RoundFrameHandlerContext], dict[str, Any]]


def handle_round_step(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_player_turn(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    return ctx.runner._advance_player_turn_module(ctx.engine, ctx.state, ctx.frame, ctx.module)


def handle_round_end_card_flip(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    assert_round_end_card_flip_ready(ctx.frame, frame_stack=ctx.state.runtime_frame_stack)
    ctx.engine._apply_round_end_marker_management(ctx.state)
    ctx.engine._resolve_marker_flip(ctx.state)
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_round_cleanup_and_next_round(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    ctx.state.rounds_completed += 1
    ctx.frame.status = "completed"
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    ctx.state.current_round_order = []
    ctx.state.runtime_frame_stack = []
    return {"status": "committed", "module_type": ctx.module.module_type}


ROUND_FRAME_HANDLERS: dict[str, RoundFrameHandler] = {
    module_type: handle_round_step for module_type in ROUND_MODULE_TYPES
}
ROUND_FRAME_HANDLERS.update(
    {
        "PlayerTurnModule": handle_player_turn,
        "RoundEndCardFlipModule": handle_round_end_card_flip,
        "RoundCleanupAndNextRoundModule": handle_round_cleanup_and_next_round,
    }
)
