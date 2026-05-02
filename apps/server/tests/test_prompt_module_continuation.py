from __future__ import annotations

import pytest

from apps.server.src.services.prompt_service import PromptService


def _module_prompt() -> dict:
    return {
        "runner_kind": "module",
        "request_id": "req_1",
        "player_id": 1,
        "request_type": "movement",
        "timeout_ms": 30000,
        "resume_token": "token_1",
        "frame_id": "turn:1:p0",
        "module_id": "mod:turn:1:p0:movement",
        "module_type": "MapMoveModule",
        "legal_choices": [{"choice_id": "roll"}],
    }


def test_prompt_payload_contains_module_continuation() -> None:
    service = PromptService()
    pending = service.create_prompt("s1", _module_prompt())

    assert pending.payload["resume_token"] == "token_1"
    assert pending.payload["frame_id"] == "turn:1:p0"
    assert pending.payload["module_id"] == "mod:turn:1:p0:movement"


def test_module_prompt_missing_continuation_rejected() -> None:
    service = PromptService()
    prompt = _module_prompt()
    prompt.pop("resume_token")

    with pytest.raises(ValueError, match="missing_module_continuation"):
        service.create_prompt("s1", prompt)


def test_duplicate_decision_ack_rejected_without_runtime_wake() -> None:
    service = PromptService()
    service.create_prompt("s1", _module_prompt())
    accepted = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "MapMoveModule",
        }
    )
    duplicate = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "MapMoveModule",
        }
    )

    assert accepted["status"] == "accepted"
    assert duplicate["status"] == "stale"


def test_stale_module_token_rejected() -> None:
    service = PromptService()
    service.create_prompt("s1", _module_prompt())

    result = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "old",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "MapMoveModule",
        }
    )

    assert result == {"status": "rejected", "reason": "token_mismatch"}


def test_module_type_mismatch_rejected() -> None:
    service = PromptService()
    service.create_prompt("s1", _module_prompt())

    result = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "DiceRollModule",
        }
    )

    assert result == {"status": "rejected", "reason": "module_mismatch"}


def test_choice_not_legal_rejected() -> None:
    service = PromptService()
    service.create_prompt("s1", _module_prompt())

    result = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "teleport",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "MapMoveModule",
        }
    )

    assert result == {"status": "rejected", "reason": "choice_not_legal"}


def test_batch_prompt_payload_contains_batch_and_module_ids() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "batch_1:p1",
        "request_type": "resupply_choice",
        "batch_id": "batch_1",
        "module_id": "mod:simul:resupply:1:1:resupply",
        "module_type": "ResupplyModule",
    }
    pending = service.create_prompt("s1", prompt)

    assert pending.payload["batch_id"] == "batch_1"
    assert pending.payload["module_type"] == "ResupplyModule"


def test_simultaneous_module_prompt_requires_batch_id() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "resupply_1:p1",
        "request_type": "resupply_choice",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:resupply",
        "module_type": "ResupplyModule",
    }

    with pytest.raises(ValueError, match="missing_batch_id"):
        service.create_prompt("s1", prompt)
