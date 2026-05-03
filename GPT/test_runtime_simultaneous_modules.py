from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from ai_policy import HeuristicPolicy
from config import GameConfig
from engine import GameEngine
from runtime_modules.runner import ModuleRunner
from runtime_modules.prompts import PromptApi, PromptContinuationError
from runtime_modules.simultaneous import batch_is_ready_to_commit, build_resupply_frame
from trick_cards import TrickCard


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
        "ResupplyModule",
        "SimultaneousCommitModule",
        "CompleteSimultaneousResolutionModule",
    ]
    assert frame.module_queue[0].payload["participants"] == [0, 1, 2]


def test_resupply_batch_waits_for_all_required_players() -> None:
    frame = build_resupply_frame(
        1,
        1,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        participants=[0, 1],
    )
    module = frame.module_queue[0]
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
        module=frame.module_queue[0],
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
        module=frame.module_queue[0],
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
    frame.module_queue[0].payload["action"] = {
        "type": "resolve_supply_threshold",
        "actor_player_id": 0,
        "source": "supply_threshold",
        "payload": {"threshold": 3},
    }
    state.runtime_frame_stack = [frame]

    result = ModuleRunner().advance_engine(engine, state)

    assert result["status"] == "waiting_input"
    assert state.runtime_active_prompt_batch is not None
    assert state.runtime_active_prompt_batch.request_type == "burden_exchange"
    assert [card.deck_index for card in state.players[0].trick_hand] == [101]
    assert [card.deck_index for card in state.players[1].trick_hand] == [102]
    assert state.players[0].cash == 10
    assert state.players[1].cash == 10

    batch = state.runtime_active_prompt_batch
    prompt0 = batch.prompts_by_player_id[0]
    result = ModuleRunner().advance_engine(
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

    prompt1 = batch.prompts_by_player_id[1]
    result = ModuleRunner().advance_engine(
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
    assert frame.module_queue[0].status == "completed"
