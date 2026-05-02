from __future__ import annotations

import pytest

from runtime_modules.prompts import PromptApi, PromptContinuationError
from runtime_modules.simultaneous import batch_is_ready_to_commit, build_resupply_frame


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
