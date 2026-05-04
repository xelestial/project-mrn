from __future__ import annotations

import pytest

from runtime_modules.contracts import FrameState, ModuleRef
from runtime_modules.prompts import PromptApi, PromptContinuationError, validate_resume


def _frame() -> FrameState:
    return FrameState(frame_id="turn:1:p0", frame_type="turn", owner_player_id=0, parent_frame_id="round:1")


def _module() -> ModuleRef:
    return ModuleRef(
        module_id="mod:turn:1:p0:movement",
        module_type="MapMoveModule",
        phase="movement",
        owner_player_id=0,
        idempotency_key="idem:movement",
        cursor="await_roll",
    )


def test_prompt_suspends_current_module_with_continuation_identity() -> None:
    continuation = PromptApi().create_continuation(
        request_id="req_1",
        prompt_instance_id=4,
        frame=_frame(),
        module=_module(),
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )

    assert continuation.frame_id == "turn:1:p0"
    assert continuation.module_id == "mod:turn:1:p0:movement"
    assert continuation.module_cursor == "await_roll"
    assert continuation.resume_token


def test_valid_decision_resumes_same_module() -> None:
    continuation = PromptApi().create_continuation(
        request_id="req_1",
        prompt_instance_id=4,
        frame=_frame(),
        module=_module(),
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )

    validate_resume(
        continuation,
        request_id="req_1",
        resume_token=continuation.resume_token,
        frame_id=continuation.frame_id,
        module_id=continuation.module_id,
        player_id=0,
        choice_id="roll",
    )


def test_resume_rejects_same_module_with_stale_cursor() -> None:
    continuation = PromptApi().create_continuation(
        request_id="req_1",
        prompt_instance_id=4,
        frame=_frame(),
        module=_module(),
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )

    with pytest.raises(PromptContinuationError, match="module cursor"):
        validate_resume(
            continuation,
            request_id="req_1",
            resume_token=continuation.resume_token,
            frame_id=continuation.frame_id,
            module_id=continuation.module_id,
            module_cursor="completed",
            player_id=0,
            choice_id="roll",
        )


def test_stale_resume_token_rejected() -> None:
    continuation = PromptApi().create_continuation(
        request_id="req_1",
        prompt_instance_id=4,
        frame=_frame(),
        module=_module(),
        player_id=0,
        request_type="movement",
        legal_choices=[{"choice_id": "roll"}],
    )

    with pytest.raises(PromptContinuationError, match="resume token"):
        validate_resume(
            continuation,
            request_id="req_1",
            resume_token="stale",
            frame_id=continuation.frame_id,
            module_id=continuation.module_id,
            player_id=0,
            choice_id="roll",
        )
