from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from ai_policy import HeuristicPolicy
from config import GameConfig
from engine import GameEngine
from runtime_modules.runner import ModuleRunner, ModuleRunnerError
from runtime_modules.prompts import PromptApi, PromptContinuationError
from runtime_modules.simultaneous import batch_is_ready_to_commit, build_resupply_frame
from trick_cards import TrickCard


def _resupply_module(frame):
    return next(module for module in frame.module_queue if module.module_type == "ResupplyModule")


def _focus_resupply_module(frame):
    target = _resupply_module(frame)
    for module in frame.module_queue:
        if module is target:
            module.status = "suspended"
            break
        module.status = "completed"
    frame.status = "suspended"
    frame.active_module_id = target.module_id
    return target


def _advance_until_waiting_or_committed(engine, state, decision_resume=None):
    runner = ModuleRunner()
    result = runner.advance_engine(engine, state, decision_resume=decision_resume)
    while result["status"] == "committed" and state.runtime_frame_stack[-1].frame_type == "simultaneous":
        if state.runtime_frame_stack[-1].status == "completed":
            break
        result = runner.advance_engine(engine, state)
    return result


def test_resupply_frame_contains_batch_commit_and_complete_modules() -> None:
    frame = build_resupply_frame(
        1,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="s1",
        participants=[0, 1, 2],
    )

    assert frame.frame_type == "simultaneous"
    assert [module.module_type for module in frame.module_queue] == [
        "SimultaneousProcessingModule",
        "SimultaneousPromptBatchModule",
        "ResupplyModule",
        "SimultaneousCommitModule",
        "CompleteSimultaneousResolutionModule",
    ]
    assert _resupply_module(frame).payload["participants"] == [0, 1, 2]


def test_resupply_batch_waits_for_all_required_players() -> None:
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0, 1],
    )
    module = _resupply_module(frame)
    batch = PromptApi().create_batch(
        batch_id="batch_resupply_1",
        frame=frame,
        module=module,
        participant_player_ids=[0, 1],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "skip"}], 1: [{"choice_id": "skip"}]},
        eligibility_snapshot={"burdens": {"0": [1], "1": [2]}},
    )

    complete = PromptApi().record_batch_response(
        batch,
        player_id=0,
        request_id=batch.prompts_by_player_id[0].request_id,
        resume_token=batch.prompts_by_player_id[0].resume_token,
        choice_id="skip",
    )

    assert complete is False
    assert batch_is_ready_to_commit(batch) is False
    assert batch.missing_player_ids == [1]


def test_partial_resupply_response_does_not_mutate_start_snapshot() -> None:
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0, 1],
    )
    snapshot = {"burdens": {"0": ["a"], "1": ["b"]}}
    batch = PromptApi().create_batch(
        batch_id="batch_resupply_1",
        frame=frame,
        module=_resupply_module(frame),
        participant_player_ids=[0, 1],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "skip"}], 1: [{"choice_id": "skip"}]},
        eligibility_snapshot=snapshot,
    )

    PromptApi().record_batch_response(
        batch,
        player_id=0,
        request_id=batch.prompts_by_player_id[0].request_id,
        resume_token=batch.prompts_by_player_id[0].resume_token,
        choice_id="skip",
    )

    assert batch.eligibility_snapshot == snapshot
    assert batch.responses_by_player_id == {0: {"choice_id": "skip"}}


def test_stale_resupply_batch_response_rejected() -> None:
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0],
    )
    batch = PromptApi().create_batch(
        batch_id="batch_resupply_1",
        frame=frame,
        module=_resupply_module(frame),
        participant_player_ids=[0],
        request_type="resupply_choice",
        legal_choices_by_player_id={0: [{"choice_id": "skip"}]},
    )

    with pytest.raises(PromptContinuationError, match="resume token"):
        PromptApi().record_batch_response(
            batch,
            player_id=0,
            request_id=batch.prompts_by_player_id[0].request_id,
            resume_token="old-token",
            choice_id="skip",
        )


def test_resupply_module_commits_only_after_all_batch_responses() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"
    state.trick_draw_pile = [
        TrickCard(
            deck_index=200 + index,
            name="무료 증정" if index % 2 == 0 else "건강 검진",
            description="drawn card",
        )
        for index in range(12)
    ]
    state.players[0].cash = 10
    state.players[1].cash = 10
    state.players[0].trick_hand = [TrickCard(deck_index=101, name="무거운 짐", description="heavy")]
    state.players[1].trick_hand = [TrickCard(deck_index=102, name="가벼운 짐", description="light")]
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0, 1],
    )
    resupply_module = _resupply_module(frame)
    resupply_module.payload["action"] = {
        "type": "resolve_supply_threshold",
        "actor_player_id": 0,
        "source": "supply_threshold",
        "payload": {"threshold": 3},
    }
    state.runtime_frame_stack = [frame]

    result = _advance_until_waiting_or_committed(engine, state)

    assert result["status"] == "waiting_input"
    assert state.runtime_active_prompt_batch is not None
    assert state.runtime_active_prompt_batch.request_type == "burden_exchange"
    assert [card.deck_index for card in state.players[0].trick_hand] == [101]
    assert [card.deck_index for card in state.players[1].trick_hand] == [102]
    assert state.players[0].cash == 10
    assert state.players[1].cash == 10

    batch = state.runtime_active_prompt_batch
    prompt0 = batch.prompts_by_player_id[0]
    result = _advance_until_waiting_or_committed(
        engine,
        state,
        decision_resume=SimpleNamespace(
            request_id=prompt0.request_id,
            player_id=1,
            request_type=prompt0.request_type,
            choice_id="yes",
            choice_payload={},
            resume_token=prompt0.resume_token,
            frame_id=prompt0.frame_id,
            module_id=prompt0.module_id,
            module_type=prompt0.module_type,
            module_cursor=prompt0.module_cursor,
            batch_id=batch.batch_id,
        ),
    )

    assert result["status"] == "waiting_input"
    assert state.runtime_active_prompt_batch is batch
    assert state.runtime_active_prompt_batch.missing_player_ids == [1]
    assert [card.deck_index for card in state.players[0].trick_hand] == [101]
    assert state.players[0].cash == 10

    duplicate = _advance_until_waiting_or_committed(
        engine,
        state,
        decision_resume=SimpleNamespace(
            request_id=prompt0.request_id,
            player_id=1,
            request_type=prompt0.request_type,
            choice_id="yes",
            choice_payload={},
            resume_token=prompt0.resume_token,
            frame_id=prompt0.frame_id,
            module_id=prompt0.module_id,
            module_type=prompt0.module_type,
            module_cursor=prompt0.module_cursor,
            batch_id=batch.batch_id,
        ),
    )

    assert duplicate["status"] == "waiting_input"
    assert state.runtime_active_prompt_batch is batch
    assert state.runtime_active_prompt_batch.missing_player_ids == [1]
    assert [card.deck_index for card in state.players[0].trick_hand] == [101]
    assert state.players[0].cash == 10

    prompt1 = batch.prompts_by_player_id[1]
    result = _advance_until_waiting_or_committed(
        engine,
        state,
        decision_resume=SimpleNamespace(
            request_id=prompt1.request_id,
            player_id=2,
            request_type=prompt1.request_type,
            choice_id="yes",
            choice_payload={},
            resume_token=prompt1.resume_token,
            frame_id=prompt1.frame_id,
            module_id=prompt1.module_id,
            module_type=prompt1.module_type,
            module_cursor=prompt1.module_cursor,
            batch_id=batch.batch_id,
        ),
    )

    assert result["status"] == "committed"
    assert state.runtime_active_prompt_batch is None
    assert state.players[0].cash == 6
    assert state.players[1].cash == 8
    assert 101 not in {card.deck_index for card in state.players[0].trick_hand}
    assert 102 not in {card.deck_index for card in state.players[1].trick_hand}
    assert resupply_module.status == "completed"


def test_resupply_module_uses_action_eligibility_snapshot_when_resuming() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"
    state.trick_draw_pile = [
        TrickCard(deck_index=200 + index, name="무료 증정", description="drawn card")
        for index in range(4)
    ]
    state.players[0].cash = 10
    state.players[0].trick_hand = [
        TrickCard(deck_index=103, name="가벼운 짐", description="new burden"),
        TrickCard(deck_index=101, name="무거운 짐", description="original burden"),
    ]
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0],
    )
    resupply_module = _resupply_module(frame)
    resupply_module.payload["action"] = {
        "type": "resolve_supply_threshold",
        "actor_player_id": 0,
        "source": "supply_threshold",
        "payload": {
            "threshold": 3,
            "participants": [0],
            "eligible_burden_deck_indices_by_player": {"0": [101]},
            "processed_burden_deck_indices_by_player": {},
        },
    }
    state.runtime_frame_stack = [frame]

    result = _advance_until_waiting_or_committed(engine, state)

    assert result["status"] == "waiting_input"
    assert state.runtime_active_prompt_batch is not None
    assert state.runtime_active_prompt_batch.eligibility_snapshot["targets_by_player"] == {"0": 101}
    assert resupply_module.payload["resupply_state"][
        "eligible_burden_deck_indices_by_player"
    ] == {"0": [101]}


def test_resupply_module_does_not_treat_hidden_trick_resume_as_batch_response(monkeypatch) -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0],
    )
    module = _focus_resupply_module(frame)
    module.payload["resupply_state"] = {
        "initialized": True,
        "threshold": 3,
        "participants": [0],
        "eligible_burden_deck_indices_by_player": {"0": []},
        "processed_burden_deck_indices_by_player": {},
        "exchanged_by_player": {},
        "batch_ordinal": 1,
        "current_batch_targets_by_player": {},
    }
    state.runtime_frame_stack = [frame]
    state.runtime_active_prompt_batch = None
    state.runtime_active_prompt = SimpleNamespace(
        request_id="sess:r1:t1:p1:hidden_trick_card:7",
        request_type="hidden_trick_card",
        player_id=0,
        resume_token="resume_hidden",
        frame_id=frame.frame_id,
        module_id=module.module_id,
        module_type=module.module_type,
        module_cursor=module.cursor,
    )
    completed = {"called": False}

    def fake_complete(self, engine_arg, state_arg, frame_arg, module_arg):
        completed["called"] = True
        return {"status": "committed", "module_type": module_arg.module_type, "frame_id": frame_arg.frame_id}

    monkeypatch.setattr(ModuleRunner, "_complete_resupply_module", fake_complete)

    result = ModuleRunner().advance_engine(
        engine,
        state,
        decision_resume=SimpleNamespace(
            request_id="sess:r1:t1:p1:hidden_trick_card:7",
            player_id=1,
            request_type="hidden_trick_card",
            choice_id="200",
            choice_payload={},
            resume_token="resume_hidden",
            frame_id=frame.frame_id,
            module_id=module.module_id,
            module_type=module.module_type,
            module_cursor=module.cursor,
            batch_id="",
        ),
    )

    assert result["status"] == "committed"
    assert completed["called"] is True


def test_resupply_module_still_rejects_batch_resume_without_active_batch() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0],
    )
    module = _focus_resupply_module(frame)
    module.cursor = "await_resupply_batch:1"
    module.payload["resupply_state"] = {
        "initialized": True,
        "threshold": 3,
        "participants": [0],
        "eligible_burden_deck_indices_by_player": {"0": [101]},
        "processed_burden_deck_indices_by_player": {},
        "exchanged_by_player": {},
        "batch_ordinal": 1,
        "current_batch_targets_by_player": {"0": 101},
    }
    state.runtime_frame_stack = [frame]
    state.runtime_active_prompt_batch = None

    with pytest.raises(ModuleRunnerError, match="resupply decision resume without active batch"):
        ModuleRunner().advance_engine(
            engine,
            state,
            decision_resume=SimpleNamespace(
                request_id=f"batch:{frame.frame_id}:{module.module_id}:1:p0",
                player_id=1,
                request_type="burden_exchange",
                choice_id="yes",
                choice_payload={},
                resume_token="resume_batch",
                frame_id=frame.frame_id,
                module_id=module.module_id,
                module_type=module.module_type,
                module_cursor=module.cursor,
                batch_id=f"batch:{frame.frame_id}:{module.module_id}:1",
            ),
        )
