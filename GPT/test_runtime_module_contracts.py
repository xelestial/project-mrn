from __future__ import annotations

import ast
import json
import random
from pathlib import Path

import pytest

from ai_policy import HeuristicPolicy
from config import GameConfig
from engine import GameEngine
from runtime_modules.contracts import (
    FrameState,
    Modifier,
    ModifierRegistryState,
    ModuleRef,
    ModuleResult,
    PromptContinuation,
)
from runtime_modules.context import ModuleContext
from runtime_modules.handlers import ModuleHandlerRegistry, build_default_handler_registry
from runtime_modules.modifiers import ModifierRegistry
from runtime_modules.prompts import PromptApi, PromptContinuationError, validate_resume
from runtime_modules.queue import FrameQueueApi, QueueValidationError
from runtime_modules.runner import ModuleRunner, ModuleRunnerError
from state import GameState


def _is_pending_actions_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "pending_actions"


def _target_writes_pending_actions(node: ast.AST) -> bool:
    if _is_pending_actions_attr(node):
        return True
    if isinstance(node, ast.Subscript):
        return _is_pending_actions_attr(node.value)
    return False


def test_production_pending_actions_are_mutated_only_by_game_state_queue_api() -> None:
    root = Path(__file__).resolve().parent
    production_paths = [
        root / "engine.py",
        root / "effect_handlers.py",
        *sorted((root / "runtime_modules").rglob("*.py")),
    ]
    mutators = {"append", "extend", "insert", "pop", "clear", "remove"}
    violations: list[str] = []

    for path in production_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in mutators and _is_pending_actions_attr(node.func.value):
                    violations.append(f"{path.relative_to(root)}:{node.lineno} direct pending_actions.{node.func.attr}()")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if _target_writes_pending_actions(target):
                        violations.append(f"{path.relative_to(root)}:{node.lineno} direct pending_actions assignment")
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                if _target_writes_pending_actions(node.target):
                    violations.append(f"{path.relative_to(root)}:{node.lineno} direct pending_actions assignment")

    assert violations == []


def test_production_runtime_modules_do_not_mutate_economy_or_tile_ownership_inline() -> None:
    root = Path(__file__).resolve().parent
    production_paths = sorted((root / "runtime_modules").rglob("*.py"))
    player_resource_attrs = {
        "cash",
        "shards",
        "hand_coins",
        "placed_coins",
        "score",
        "total_score",
    }
    tile_owner_attrs = {"tile_owner", "tile_owners"}
    violations: list[str] = []

    def target_name(target: ast.AST) -> str | None:
        if isinstance(target, ast.Attribute):
            if target.attr in player_resource_attrs:
                return target.attr
            if target.attr in tile_owner_attrs:
                return target.attr
        if isinstance(target, ast.Subscript):
            return target_name(target.value)
        return None

    for path in production_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = target_name(target)
                    if name is not None:
                        violations.append(f"{path.relative_to(root)}:{node.lineno} direct {name} assignment")
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                name = target_name(node.target)
                if name is not None:
                    violations.append(f"{path.relative_to(root)}:{node.lineno} direct {name} assignment")

    assert violations == []


def _module(module_type: str, module_id: str = "mod:test", idempotency_key: str = "idem:test") -> ModuleRef:
    return ModuleRef(
        module_id=module_id,
        module_type=module_type,
        phase="test",
        owner_player_id=0,
        idempotency_key=idempotency_key,
    )


def test_draft_module_rejected_in_turn_frame() -> None:
    frame = FrameState(frame_id="turn:0:p0", frame_type="turn", owner_player_id=0, parent_frame_id=None)

    with pytest.raises(QueueValidationError, match="DraftModule"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("DraftModule")}
        ])


def test_round_end_card_flip_rejected_in_turn_frame() -> None:
    frame = FrameState(frame_id="turn:0:p0", frame_type="turn", owner_player_id=0, parent_frame_id=None)

    with pytest.raises(QueueValidationError, match="RoundEndCardFlipModule"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("RoundEndCardFlipModule")}
        ])


def test_resupply_module_rejected_in_action_sequence_frame() -> None:
    frame = FrameState(
        frame_id="seq:action:0:p0:0",
        frame_type="sequence",
        owner_player_id=0,
        parent_frame_id="turn:0:p0",
    )

    with pytest.raises(QueueValidationError, match="ResupplyModule"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("ResupplyModule")}
        ])


def test_completed_frame_rejects_queue_insertion() -> None:
    frame = FrameState(
        frame_id="round:0",
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        status="completed",
    )

    with pytest.raises(QueueValidationError, match="completed frame"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("WeatherModule")}
        ])


def test_module_context_dispatch_applies_queue_ops_and_journals_events() -> None:
    frame = FrameState(
        frame_id="round:1",
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[_module("ContractTestModule", module_id="mod:contract", idempotency_key="idem:contract")],
    )
    state = type(
        "RuntimeState",
        (),
        {
            "runtime_frame_stack": [frame],
            "runtime_module_journal": [],
            "runtime_modifier_registry": ModifierRegistryState(),
        },
    )()

    def handler(ctx: ModuleContext) -> ModuleResult:
        ctx.emit("contract.event", value=1)
        ctx.push_back(_module("WeatherModule", module_id="mod:weather", idempotency_key="idem:weather"))
        return ModuleResult(status="completed", events=ctx.events, queue_ops=ctx.queue_ops)

    registry = ModuleHandlerRegistry()
    registry.register("ContractTestModule", handler)
    module = frame.module_queue[0]

    result = ModuleRunner(handler_registry=registry)._dispatch_module(object(), state, frame, module)

    assert result.status == "completed"
    assert module.status == "completed"
    assert [item.module_type for item in frame.module_queue] == ["ContractTestModule", "WeatherModule"]
    assert state.runtime_module_journal[-1].event_types == ["contract.event"]


def test_module_registry_missing_handler_fails_loudly() -> None:
    frame = FrameState(
        frame_id="round:1",
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[_module("UnknownContractModule")],
    )
    state = type(
        "RuntimeState",
        (),
        {
            "runtime_frame_stack": [frame],
            "runtime_module_journal": [],
            "runtime_modifier_registry": ModifierRegistryState(),
        },
    )()

    with pytest.raises(ModuleRunnerError, match="no module handler"):
        ModuleRunner(handler_registry=ModuleHandlerRegistry())._dispatch_module(
            object(),
            state,
            frame,
            frame.module_queue[0],
        )


def test_round_frame_uses_module_handler_registry_for_uncatalogued_module() -> None:
    frame = FrameState(
        frame_id="round:1",
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[_module("ContractRoundModule", module_id="mod:round:contract")],
    )
    state = type(
        "RuntimeState",
        (),
        {
            "runtime_frame_stack": [frame],
            "runtime_module_journal": [],
            "runtime_modifier_registry": ModifierRegistryState(),
            "rounds_completed": 0,
            "current_round_order": [0],
            "pending_actions": [],
        },
    )()

    def handler(ctx: ModuleContext) -> ModuleResult:
        ctx.emit("contract.round")
        return ModuleResult(status="completed", events=ctx.events)

    registry = ModuleHandlerRegistry()
    registry.register("ContractRoundModule", handler)

    result = ModuleRunner(handler_registry=registry).advance_engine(object(), state)

    assert result["runner_kind"] == "module"
    assert result["module_type"] == "ContractRoundModule"
    assert result["events"] == ["contract.round"]
    assert frame.module_queue[0].status == "completed"


def test_player_turn_module_registered_as_native_handler() -> None:
    from runtime_modules.handlers.round import ROUND_FRAME_HANDLERS

    registry = build_default_handler_registry()

    assert registry.has("PlayerTurnModule")
    assert "PlayerTurnModule" not in ROUND_FRAME_HANDLERS


def test_duplicate_module_id_rejects_different_idempotency_key() -> None:
    frame = FrameState(
        frame_id="round:0",
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[_module("WeatherModule", module_id="mod:weather", idempotency_key="idem:one")],
    )

    with pytest.raises(QueueValidationError, match="different idempotency_key"):
        FrameQueueApi([frame]).apply([
            {
                "op": "push_back",
                "target_frame_id": frame.frame_id,
                "module": _module("WeatherModule", module_id="mod:weather", idempotency_key="idem:two"),
            }
        ])


def test_prompt_resume_token_mismatch_rejected() -> None:
    continuation = PromptContinuation(
        request_id="req_1",
        prompt_instance_id=1,
        resume_token="token_ok",
        frame_id="turn:0:p0",
        module_id="mod:move",
        module_type="MapMoveModule",
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )

    with pytest.raises(PromptContinuationError, match="resume token"):
        validate_resume(
            continuation,
            request_id="req_1",
            resume_token="wrong",
            frame_id="turn:0:p0",
            module_id="mod:move",
            player_id=0,
            choice_id="roll",
        )


def test_modifier_single_use_consumed_once() -> None:
    registry = ModifierRegistry(ModifierRegistryState())
    registry.add(
        Modifier(
            modifier_id="modif:reroll",
            source_module_id="mod:trick",
            target_module_type="DiceRollModule",
            scope="single_use",
            owner_player_id=1,
            priority=10,
        )
    )

    assert [item.modifier_id for item in registry.applicable("DiceRollModule", 1)] == ["modif:reroll"]
    registry.consume("modif:reroll")
    assert registry.applicable("DiceRollModule", 1) == []


def test_module_muroe_suppression_requires_seeded_modifier() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    state = GameState.create(config)
    state.runtime_runner_kind = "module"
    actor = state.players[0]
    eosa = state.players[1]
    actor.current_character = "자객"
    eosa.current_character = "어사"

    assert engine._is_muroe_skill_blocked(state, actor) is False

    engine._seed_character_start_modifiers(state)

    assert engine._is_muroe_skill_blocked(state, actor) is True
    modifier = state.runtime_modifier_registry.modifiers[0]
    assert modifier.payload["kind"] == "suppress_character_skill"
    assert modifier.payload["reason"] == "muroe_blocked_by_eosa"
    assert modifier.owner_player_id == actor.player_id
    assert modifier.target_module_type == "CharacterStartModule"


def test_simultaneous_frame_rejects_turn_only_module() -> None:
    frame = FrameState(frame_id="simul:resupply:0:0", frame_type="simultaneous", owner_player_id=None, parent_frame_id=None)

    with pytest.raises(QueueValidationError, match="SimultaneousResolutionFrame"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("TurnEndSnapshotModule")}
        ])


def test_prompt_batch_partial_response_does_not_complete() -> None:
    frame = FrameState(frame_id="simul:resupply:0:0", frame_type="simultaneous", owner_player_id=None, parent_frame_id=None)
    module = _module("SimultaneousPromptBatchModule", module_id="mod:batch")
    api = PromptApi()
    batch = api.create_batch(
        batch_id="batch_1",
        frame=frame,
        module=module,
        participant_player_ids=[0, 1],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "cash"}], 1: [{"choice_id": "shard"}]},
    )

    complete = api.record_batch_response(
        batch,
        player_id=0,
        request_id=batch.prompts_by_player_id[0].request_id,
        resume_token=batch.prompts_by_player_id[0].resume_token,
        choice_id="cash",
    )

    assert complete is False
    assert batch.missing_player_ids == [1]


def test_prompt_batch_completes_after_all_required_responses() -> None:
    frame = FrameState(frame_id="simul:resupply:0:0", frame_type="simultaneous", owner_player_id=None, parent_frame_id=None)
    module = _module("SimultaneousPromptBatchModule", module_id="mod:batch")
    api = PromptApi()
    batch = api.create_batch(
        batch_id="batch_1",
        frame=frame,
        module=module,
        participant_player_ids=[0, 1],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "cash"}], 1: [{"choice_id": "shard"}]},
    )

    for player_id, choice_id in [(0, "cash"), (1, "shard")]:
        api.record_batch_response(
            batch,
            player_id=player_id,
            request_id=batch.prompts_by_player_id[player_id].request_id,
            resume_token=batch.prompts_by_player_id[player_id].resume_token,
            choice_id=choice_id,
        )

    assert batch.missing_player_ids == []


def test_checkpoint_round_trips_runtime_state() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    frame = FrameState(
        frame_id="simul:resupply:0:0",
        frame_type="simultaneous",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[
            _module("SimultaneousPromptBatchModule", module_id="mod:batch", idempotency_key="idem:batch")
        ],
        active_module_id="mod:batch",
    )
    frame.module_queue[0].cursor = "await_all_resupply_choices"
    batch = PromptApi().create_batch(
        batch_id="batch_1",
        frame=frame,
        module=frame.module_queue[0],
        participant_player_ids=[0, 1],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "cash"}], 1: [{"choice_id": "shard"}]},
    )
    state.runtime_runner_kind = "module"
    state.runtime_frame_stack = [frame]
    state.runtime_active_prompt = PromptApi().create_continuation(
        request_id="req_move_1",
        prompt_instance_id=3,
        frame=frame,
        module=frame.module_queue[0],
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )
    state.runtime_active_prompt_batch = batch
    state.runtime_modifier_registry.modifiers.append(
        Modifier(
            modifier_id="modif:test",
            source_module_id="mod:trick",
            target_module_type="DiceRollModule",
            scope="turn",
            owner_player_id=None,
            priority=20,
        )
    )

    payload = json.loads(json.dumps(state.to_checkpoint_payload(), ensure_ascii=False))
    restored = GameState.from_checkpoint_payload(config, payload)

    assert restored.runtime_runner_kind == "module"
    assert restored.runtime_frame_stack[0].frame_type == "simultaneous"
    assert restored.runtime_active_prompt is not None
    assert restored.runtime_active_prompt.module_cursor == "await_all_resupply_choices"
    assert restored.runtime_active_prompt_batch is not None
    assert restored.runtime_active_prompt_batch.missing_player_ids == [0, 1]
    assert restored.runtime_modifier_registry.modifiers[0].modifier_id == "modif:test"
