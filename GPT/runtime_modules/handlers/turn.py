from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from policy.environment_traits import WEATHER_FATTENED_HORSES_ID, has_weather_id
from viewer.events import Phase
from viewer.public_state import build_turn_end_snapshot

from policy.character_traits import is_builder, is_pabalggun

from ..contracts import FrameState, ModuleRef
from ..modifiers import (
    MUROE_SKILL_SUPPRESSION_KIND,
    PABAL_DICE_MODIFIER_KIND,
    ModifierRegistry,
    consume_pabal_dice_modifier,
    seed_builder_purchase_modifier,
    seed_pabal_dice_modifier,
)
from ..sequence_modules import build_trick_sequence_frame


@dataclass(slots=True)
class TurnFrameHandlerContext:
    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef
    player_id: int
    player: Any


TurnFrameHandler = Callable[[TurnFrameHandlerContext], dict[str, Any]]


def handle_turn_start(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    player = ctx.player
    context = runner._turn_context(frame)
    if not context:
        module.payload["finisher_before"] = int(getattr(player, "control_finisher_turns", 0) or 0)
        module.payload["disruption_before"] = dict(engine._leader_disruption_snapshot(state, player))
        player.turns_taken += 1
    if player.skipped_turn:
        player.skipped_turn = False
        engine._log(
            {
                "event": "turn_start",
                "player": player.player_id + 1,
                "character": player.current_character,
                "skipped": True,
            }
        )
        engine._emit_vis("turn_start", Phase.TURN_START, player.player_id + 1, state, character=player.current_character, skipped=True)
        engine._emit_vis("turn_end_snapshot", Phase.TURN_END, player.player_id + 1, state, snapshot=build_turn_end_snapshot(state))
        runner._complete_module(state, frame, module)
        runner._skip_remaining_modules(frame)
        state.turn_index += 1
        runner._complete_turn_frame_and_parent(state, frame)
        return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1, "skipped": True}
    runner._complete_module(state, frame, module)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def handle_scheduled_start_actions(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    if engine._materialize_scheduled_actions(state, phase="turn_start", player_id=player_id):
        module.status = "suspended"
        module.cursor = "pending_start_actions"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        runner._promote_pending_work_to_sequence_frames(engine, state, parent_frame=frame, parent_module=module)
        return {
            "status": "committed",
            "module_type": module.module_type,
            "player_id": player_id + 1,
            "pending_actions": len(state.pending_actions),
            "pending_modules": runner._pending_sequence_module_count(state),
        }
    runner._complete_module(state, frame, module)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def handle_pending_mark_resolution(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    player = ctx.player
    engine._resolve_pending_marks(state, player)
    runner._complete_module(state, frame, module)
    if not player.alive:
        runner._skip_remaining_modules(frame)
        state.turn_index += 1
        runner._complete_turn_frame_and_parent(state, frame)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def handle_character_start(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    player = ctx.player
    if has_weather_id(state.current_weather_effects, WEATHER_FATTENED_HORSES_ID):
        player.extra_dice_count_this_turn += 1
    module.cursor = "await_character_prompt"
    try:
        if not _seed_native_character_start_modifier(ctx):
            engine._apply_character_start(state, player)
    except Exception:
        module.status = "suspended"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        raise
    runner._complete_module(state, frame, module)
    if not player.alive:
        runner._skip_remaining_modules(frame)
        state.turn_index += 1
        runner._complete_turn_frame_and_parent(state, frame)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def _seed_native_character_start_modifier(ctx: TurnFrameHandlerContext) -> bool:
    player = ctx.player
    char = str(getattr(player, "current_character", "") or "")
    if is_pabalggun(char):
        dice_mode = "plus_one"
        ability_tier = 1
        if int(getattr(player, "shards", 0) or 0) >= 8:
            ability_tier = 2
            chooser = getattr(getattr(ctx.engine, "policy", None), "choose_pabal_dice_mode", None)
            requested_mode = chooser(ctx.state, player) if callable(chooser) else None
            if requested_mode in {"plus_one", "minus_one"}:
                dice_mode = requested_mode
        seed_pabal_dice_modifier(
            ctx.state,
            player_id=ctx.player_id,
            dice_mode=dice_mode,
            source_module_id=ctx.module.module_id,
        )
        ctx.module.payload["native_character_ability"] = {
            "kind": PABAL_DICE_MODIFIER_KIND,
            "dice_mode": dice_mode,
            "ability_tier": ability_tier,
        }
        ctx.engine._log(
            {
                "event": "character_ability_modifier_seeded",
                "player": player.player_id + 1,
                "character": char,
                "kind": PABAL_DICE_MODIFIER_KIND,
                "dice_mode": dice_mode,
                "ability_tier": ability_tier,
                "shards": getattr(player, "shards", 0),
            }
        )
        return True
    if is_builder(char):
        seed_builder_purchase_modifier(ctx.state, player_id=ctx.player_id, source_module_id=ctx.module.module_id)
        ctx.module.payload["native_character_ability"] = {"kind": "builder_free_purchase"}
        ctx.engine._log(
            {
                "event": "character_ability_modifier_seeded",
                "player": player.player_id + 1,
                "character": char,
                "kind": "builder_free_purchase",
            }
        )
        return True
    return False


def handle_target_judicator(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    if _has_suppression_modifier(state, module, player_id):
        runner._complete_module(state, frame, module)
        return {
            "status": "committed",
            "module_type": module.module_type,
            "player_id": player_id + 1,
            "suppressed": True,
        }
    module.cursor = "await_mark_target"
    try:
        adjudication = engine._adjudicate_character_mark(state, ctx.player)
    except Exception:
        module.status = "suspended"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        raise
    if isinstance(adjudication, dict) and adjudication.get("mode") == "immediate":
        _insert_immediate_marker_transfer(frame, module, adjudication)
    runner._complete_module(state, frame, module)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def handle_immediate_marker_transfer(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    engine._apply_immediate_marker_transfer(state, ctx.player, dict(module.payload or {}))
    runner._complete_module(state, frame, module)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def _has_suppression_modifier(state: Any, module: ModuleRef, player_id: int) -> bool:
    registry = ModifierRegistry(state.runtime_modifier_registry)
    modifier_ids = set(module.modifiers)
    candidates = registry.applicable(module.module_type, owner_player_id=player_id)
    for modifier in candidates:
        if modifier_ids and modifier.modifier_id not in modifier_ids:
            continue
        if modifier.payload.get("kind") == MUROE_SKILL_SUPPRESSION_KIND:
            registry.consume(modifier.modifier_id)
            return True
    return False


def _insert_immediate_marker_transfer(frame: FrameState, current: ModuleRef, payload: dict[str, Any]) -> None:
    module_id = f"{current.module_id}:immediate_marker_transfer"
    if any(module.module_id == module_id for module in frame.module_queue):
        return
    inserted = ModuleRef(
        module_id=module_id,
        module_type="ImmediateMarkerTransferModule",
        phase="immediate_marker_transfer",
        owner_player_id=current.owner_player_id,
        payload=dict(payload),
        idempotency_key=f"{current.idempotency_key}:immediate_marker_transfer",
    )
    try:
        index = frame.module_queue.index(current)
    except ValueError:
        frame.module_queue.append(inserted)
        return
    frame.module_queue.insert(index + 1, inserted)


def handle_trick_window(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    player = ctx.player
    context = runner._turn_context(frame)
    child = runner._child_frame_for_module(state, module)
    if child is not None and child.status != "completed":
        module.status = "suspended"
        module.cursor = "child_trick_sequence"
        module.suspension_id = child.frame_id
        frame.status = "suspended"
    else:
        if not module.payload.get("window_opened"):
            engine._emit_vis(
                "turn_start",
                Phase.TURN_START,
                player.player_id + 1,
                state,
                character=player.current_character,
                position=player.position,
            )
            engine._emit_vis(
                "trick_window_open",
                Phase.TRICK_WINDOW,
                player.player_id + 1,
                state,
                hand_size=len(player.trick_hand),
                public_tricks=player.public_trick_names(),
                hidden_trick_count=player.hidden_trick_count(),
            )
            module.payload["window_opened"] = True
        if child is None:
            child = build_trick_sequence_frame(
                int(getattr(state, "rounds_completed", 0) or 0) + 1,
                player_id,
                runner._next_sequence_ordinal(state),
                parent_frame_id=frame.frame_id,
                parent_module_id=module.module_id,
                session_id=getattr(engine, "_vis_session_id", ""),
            )
            for child_module in child.module_queue:
                child_module.payload["turn_context"] = dict(context)
            state.runtime_frame_stack.append(child)
            module.status = "suspended"
            module.cursor = "child_trick_sequence"
            module.suspension_id = child.frame_id
            frame.status = "suspended"
        else:
            runner._complete_module(state, frame, module)
    return {
        "status": "committed",
        "module_type": module.module_type,
        "player_id": player_id + 1,
        "pending_actions": len(state.pending_actions),
        "pending_modules": runner._pending_sequence_module_count(state),
    }


def handle_dice_roll(ctx: TurnFrameHandlerContext) -> dict[str, Any]:
    runner = ctx.runner
    engine = ctx.engine
    state = ctx.state
    frame = ctx.frame
    module = ctx.module
    player_id = ctx.player_id
    player = ctx.player
    context = runner._turn_context(frame)
    module.cursor = "await_turn_prompt"
    _apply_dice_roll_modifiers(state, player_id, player)
    try:
        engine._finish_turn_after_trick_phase(
            state,
            player,
            finisher_before=int(context.get("finisher_before", 0) or 0),
            disruption_before=dict(context.get("disruption_before") or {}),
        )
    except Exception:
        module.status = "suspended"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        raise
    if state.pending_actions or state.pending_turn_completion:
        module.status = "suspended"
        module.cursor = "pending_turn_resolution"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        runner._promote_pending_work_to_sequence_frames(engine, state, parent_frame=frame, parent_module=module)
        return {
            "status": "committed",
            "module_type": module.module_type,
            "player_id": player_id + 1,
            "pending_actions": len(state.pending_actions),
            "pending_modules": runner._pending_sequence_module_count(state),
        }
    runner._complete_module(state, frame, module)
    return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}


def _apply_dice_roll_modifiers(state: Any, player_id: int, player: Any) -> None:
    modifier = consume_pabal_dice_modifier(state, player_id=player_id)
    if modifier is None:
        return
    dice_delta = int(modifier.payload.get("dice_delta", 0) or 0)
    if dice_delta >= 0:
        player.extra_dice_count_this_turn += dice_delta
    else:
        player.trick_dice_delta_this_turn += dice_delta


TURN_FRAME_HANDLERS: dict[str, TurnFrameHandler] = {
    "TurnStartModule": handle_turn_start,
    "ScheduledStartActionsModule": handle_scheduled_start_actions,
    "PendingMarkResolutionModule": handle_pending_mark_resolution,
    "CharacterStartModule": handle_character_start,
    "TargetJudicatorModule": handle_target_judicator,
    "ImmediateMarkerTransferModule": handle_immediate_marker_transfer,
    "TrickWindowModule": handle_trick_window,
    "DiceRollModule": handle_dice_roll,
}
