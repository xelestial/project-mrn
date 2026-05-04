from __future__ import annotations

from ..context import ModuleContext
from ..contracts import ModuleResult


def handle_player_turn(ctx: ModuleContext) -> ModuleResult:
    result = ctx.runner._advance_player_turn_module(ctx.engine, ctx.state, ctx.frame, ctx.module)
    ctx.module.payload["last_player_turn_dispatch"] = {
        "status": result.get("status"),
        "player_id": result.get("player_id"),
        "skipped": bool(result.get("skipped", False)),
    }
    if ctx.module.status == "suspended":
        return ModuleResult(status="suspended")
    return ModuleResult(status="completed")
