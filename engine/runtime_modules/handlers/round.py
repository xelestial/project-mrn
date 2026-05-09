from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import FrameState, ModuleRef
from ..round_modules import assert_round_end_card_flip_ready, install_player_turn_modules


@dataclass(slots=True)
class RoundFrameHandlerContext:
    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef


RoundFrameHandler = Callable[[RoundFrameHandlerContext], dict[str, Any]]


def handle_round_start(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    ctx.engine._prepare_round_start_state(ctx.state, _module_initial(ctx.module))
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_initial_reward(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    if not _module_initial(ctx.module):
        ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
        return {"status": "skipped", "module_type": ctx.module.module_type}
    try:
        index = int(ctx.module.payload.get("player_index", 0) or 0)
        while index < len(ctx.state.players):
            player = ctx.state.players[index]
            ctx.module.cursor = f"initial_reward:p{index}"
            if player.alive:
                ctx.engine._apply_start_reward(ctx.state, player)
            index += 1
            ctx.module.payload["player_index"] = index
    except Exception:
        ctx.module.status = "suspended"
        ctx.module.suspension_id = ctx.frame.frame_id
        ctx.frame.status = "suspended"
        raise
    ctx.module.cursor = "completed"
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_weather(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    ctx.engine._reveal_round_weather(ctx.state)
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_draft(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    try:
        _advance_draft_module(ctx)
    except Exception:
        ctx.module.status = "suspended"
        ctx.module.suspension_id = ctx.frame.frame_id
        ctx.frame.status = "suspended"
        raise
    ctx.module.payload.pop("draft_state", None)
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


def handle_turn_scheduler(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    ctx.engine._schedule_round_turn_order(ctx.state, _module_initial(ctx.module))
    install_player_turn_modules(
        ctx.frame,
        int(getattr(ctx.state, "rounds_completed", 0) or 0) + 1,
        list(getattr(ctx.state, "current_round_order", []) or []),
        session_id=str(getattr(ctx.engine, "_vis_session_id", "") or ""),
    )
    ctx.runner._complete_module(ctx.state, ctx.frame, ctx.module)
    return {"status": "committed", "module_type": ctx.module.module_type}


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
    "RoundStartModule": handle_round_start,
    "InitialRewardModule": handle_initial_reward,
    "WeatherModule": handle_weather,
    "DraftModule": handle_draft,
    "TurnSchedulerModule": handle_turn_scheduler,
}
ROUND_FRAME_HANDLERS.update(
    {
        "RoundEndCardFlipModule": handle_round_end_card_flip,
        "RoundCleanupAndNextRoundModule": handle_round_cleanup_and_next_round,
    }
)


def _module_initial(module: ModuleRef) -> bool:
    return bool((module.payload or {}).get("initial"))


def _advance_draft_module(ctx: RoundFrameHandlerContext) -> None:
    draft_state = _ensure_draft_state(ctx)

    while int(draft_state.get("step_index", 0) or 0) < len(draft_state.get("steps", []) or []):
        _ensure_three_player_second_phase(draft_state)
        step_index = int(draft_state.get("step_index", 0) or 0)
        steps = list(draft_state.get("steps", []) or [])
        if step_index >= len(steps):
            break
        step = dict(steps[step_index] or {})
        pool_key = str(step.get("pool_key") or "")
        pools = draft_state.setdefault("pools", {})
        pool = [int(card) for card in list(pools.get(pool_key, []) or [])]
        if not pool:
            draft_state["step_index"] = step_index + 1
            pools[pool_key] = []
            continue
        pid = int(step.get("pid", 0) or 0)
        player = ctx.state.players[pid]
        ctx.module.cursor = f"draft:pick:{step_index}"
        offered_cards = ctx.engine._draft_offered_cards(pool)
        pick, draft_debug, record_debug = ctx.engine._choose_draft_pick(ctx.state, player, offered_cards)
        ctx.engine._apply_draft_pick(
            ctx.state,
            player,
            pool,
            pick,
            int(step.get("phase", 1) or 1),
            draft_debug,
            record_debug,
        )
        pools[pool_key] = pool
        draft_state["step_index"] = step_index + 1

    _ensure_three_player_second_phase(draft_state)
    final_order = [int(pid) for pid in list(draft_state.get("final_order", []) or [])]
    while int(draft_state.get("final_index", 0) or 0) < len(final_order):
        final_index = int(draft_state.get("final_index", 0) or 0)
        pid = final_order[final_index]
        ctx.module.cursor = f"draft:final:{final_index}"
        ctx.engine._complete_final_character_choice(ctx.state, ctx.state.players[pid])
        draft_state["final_index"] = final_index + 1

    if getattr(ctx.state, "runtime_runner_kind", "module") == "module":
        ctx.engine._seed_character_start_modifiers(ctx.state)
    ctx.engine._suppress_hidden_trick_selection = False
    ctx.engine._refresh_hidden_trick_slots(ctx.state)
    ctx.module.cursor = "completed"


def _ensure_draft_state(ctx: RoundFrameHandlerContext) -> dict[str, Any]:
    payload = ctx.module.payload
    existing = payload.get("draft_state")
    if isinstance(existing, dict) and existing.get("initialized"):
        return existing

    initial = _module_initial(ctx.module)
    if initial and not payload.get("initial_tricks_dealt"):
        ctx.engine._deal_initial_tricks(ctx.state)
        payload["initial_tricks_dealt"] = True

    cards = ctx.engine._new_shuffled_draft_cards()
    clockwise = ctx.engine._alive_ids_from_marker_direction(ctx.state)
    reverse = list(reversed(clockwise))
    alive_count = len(clockwise)
    final_order = [int(player.player_id) for player in ctx.state.players]

    if alive_count == 3:
        hidden_card = int(cards[0])
        phase1_pool = [int(card) for card in cards[1:5]]
        reserve_pool = [int(card) for card in cards[5:8]]
        ctx.engine._log({"event": "draft_hidden_card", "player_count": 3, "hidden_card": hidden_card})
        draft_state = {
            "initialized": True,
            "mode": "three",
            "clockwise": list(clockwise),
            "reverse": list(reverse),
            "pools": {"phase1": phase1_pool},
            "reserve_pool": reserve_pool,
            "steps": [
                {"pid": int(pid), "phase": 1, "pool_key": "phase1"}
                for pid in clockwise
            ],
            "step_index": 0,
            "phase2_initialized": False,
            "final_order": final_order,
            "final_index": 0,
        }
    else:
        first_pack_size = alive_count
        second_pack_size = alive_count
        first_pool = [int(card) for card in cards[:first_pack_size]]
        second_pool = [int(card) for card in cards[first_pack_size:first_pack_size + second_pack_size]]
        hidden = [int(card) for card in cards[first_pack_size + second_pack_size:]]
        if hidden:
            ctx.engine._log({"event": "draft_hidden_cards", "player_count": alive_count, "hidden_cards": list(hidden)})
        draft_state = {
            "initialized": True,
            "mode": "standard",
            "clockwise": list(clockwise),
            "reverse": list(reverse),
            "pools": {"phase1": first_pool, "phase2": second_pool},
            "steps": [
                *[
                    {"pid": int(pid), "phase": 1, "pool_key": "phase1"}
                    for pid in clockwise
                ],
                *[
                    {"pid": int(pid), "phase": 2, "pool_key": "phase2"}
                    for pid in reverse
                ],
            ],
            "step_index": 0,
            "phase2_initialized": True,
            "final_order": final_order,
            "final_index": 0,
        }
    payload["draft_state"] = draft_state
    return draft_state


def _ensure_three_player_second_phase(draft_state: dict[str, Any]) -> None:
    if draft_state.get("mode") != "three" or draft_state.get("phase2_initialized"):
        return
    clockwise = [int(pid) for pid in list(draft_state.get("clockwise", []) or [])]
    if int(draft_state.get("step_index", 0) or 0) < len(clockwise):
        return
    pools = draft_state.setdefault("pools", {})
    phase1_remaining = [int(card) for card in list(pools.get("phase1", []) or [])]
    reserve_pool = [int(card) for card in list(draft_state.get("reserve_pool", []) or [])]
    pools["phase2"] = [*reserve_pool, *phase1_remaining]
    reverse = [int(pid) for pid in list(draft_state.get("reverse", []) or [])]
    second_steps = []
    if clockwise:
        second_steps.append({"pid": int(clockwise[-1]), "phase": 2, "pool_key": "phase2"})
    second_steps.extend(
        {"pid": int(pid), "phase": 2, "pool_key": "phase2"}
        for pid in reverse[1:]
    )
    draft_state["steps"] = [*list(draft_state.get("steps", []) or []), *second_steps]
    draft_state["phase2_initialized"] = True
