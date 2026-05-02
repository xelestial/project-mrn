from __future__ import annotations

import json

import pytest

from config import GameConfig
from runtime_modules.contracts import (
    FrameState,
    Modifier,
    ModifierRegistryState,
    ModuleRef,
    PromptContinuation,
)
from runtime_modules.modifiers import ModifierRegistry
from runtime_modules.prompts import PromptApi, PromptContinuationError, validate_resume
from runtime_modules.queue import FrameQueueApi, QueueValidationError
from state import GameState


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
        module_queue=[_module("SimultaneousPromptBatchModule", module_id="mod:batch")],
        active_module_id="mod:batch",
    )
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
    assert restored.runtime_active_prompt_batch is not None
    assert restored.runtime_active_prompt_batch.missing_player_ids == [0, 1]
    assert restored.runtime_modifier_registry.modifiers[0].modifier_id == "modif:test"
