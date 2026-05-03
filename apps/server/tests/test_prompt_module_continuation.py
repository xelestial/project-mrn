from __future__ import annotations

from types import SimpleNamespace

import pytest

from GPT.runtime_modules.contracts import FrameState, ModuleRef
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import _LocalHumanDecisionClient


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
        "module_cursor": "move:await_choice",
        "legal_choices": [{"choice_id": "roll"}],
    }


def test_prompt_payload_contains_module_continuation() -> None:
    service = PromptService()
    pending = service.create_prompt("s1", _module_prompt())

    assert pending.payload["resume_token"] == "token_1"
    assert pending.payload["frame_id"] == "turn:1:p0"
    assert pending.payload["module_id"] == "mod:turn:1:p0:movement"
    assert pending.payload["module_cursor"] == "move:await_choice"


def test_module_prompt_missing_continuation_rejected() -> None:
    service = PromptService()
    prompt = _module_prompt()
    prompt.pop("resume_token")

    with pytest.raises(ValueError, match="missing_module_continuation"):
        service.create_prompt("s1", prompt)


def test_module_prompt_missing_cursor_rejected() -> None:
    service = PromptService()
    prompt = _module_prompt()
    prompt.pop("module_cursor")

    with pytest.raises(ValueError, match="missing_module_continuation:module_cursor"):
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
            "module_cursor": "move:await_choice",
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
            "module_cursor": "move:await_choice",
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
            "module_cursor": "move:await_choice",
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
            "module_cursor": "move:await_choice",
        }
    )

    assert result == {"status": "rejected", "reason": "module_mismatch"}


def test_module_cursor_mismatch_rejected() -> None:
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
            "module_type": "MapMoveModule",
            "module_cursor": "move:old",
        }
    )

    assert result == {"status": "rejected", "reason": "module_cursor_mismatch"}


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
            "module_cursor": "move:await_choice",
        }
    )

    assert result == {"status": "rejected", "reason": "choice_not_legal"}


def test_module_decision_command_payload_carries_continuation() -> None:
    commands: list[dict] = []

    class _CommandStore:
        def append_command(self, session_id, command_type, payload, **kwargs):  # noqa: ANN001
            commands.append(
                {
                    "session_id": session_id,
                    "type": command_type,
                    "payload": dict(payload),
                    "kwargs": dict(kwargs),
                }
            )

    service = PromptService(command_store=_CommandStore())
    service.create_prompt("s1", _module_prompt())

    result = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "MapMoveModule",
            "module_cursor": "move:await_choice",
        }
    )

    assert result["status"] == "accepted"
    payload = commands[0]["payload"]
    assert payload["resume_token"] == "token_1"
    assert payload["frame_id"] == "turn:1:p0"
    assert payload["module_id"] == "mod:turn:1:p0:movement"
    assert payload["module_type"] == "MapMoveModule"
    assert payload["module_cursor"] == "move:await_choice"
    assert payload["request_type"] == "movement"


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


def test_local_human_prompt_created_inside_module_attaches_active_continuation() -> None:
    captured: dict = {}

    class _Gateway:
        def _stable_prompt_request_id(self, envelope, public_context):  # noqa: ANN001
            return "s1:r1:t2:p1:trick:4"

        def resolve_human_prompt(self, envelope, parser, fallback_fn):  # noqa: ANN001
            captured.update(envelope)
            return "defer"

    active_module = ModuleRef(
        module_id="mod:trick_sequence:1:p0:choice",
        module_type="TrickChoiceModule",
        phase="trick_choice",
        owner_player_id=0,
        cursor="await_trick_prompt",
        idempotency_key="idem:trick",
    )
    active_frame = FrameState(
        frame_id="seq:trick:1:p0",
        frame_type="sequence",
        owner_player_id=0,
        parent_frame_id="turn:1:p0",
        module_queue=[active_module],
        active_module_id=active_module.module_id,
    )
    state = SimpleNamespace(
        runtime_runner_kind="module",
        runtime_frame_stack=[active_frame],
        runtime_active_prompt=None,
        runtime_active_prompt_batch=None,
    )
    request = SimpleNamespace(
        request_type="trick",
        player_id=0,
        fallback_policy="required",
        public_context={"round_index": 1, "turn_index": 2},
    )
    call = SimpleNamespace(
        request=request,
        legal_choices=[{"choice_id": "defer"}, {"choice_id": "use_trick"}],
        invocation=SimpleNamespace(state=state),
    )
    client = _LocalHumanDecisionClient.__new__(_LocalHumanDecisionClient)
    client.policy = SimpleNamespace(_prompt_seq=3)
    client._gateway = _Gateway()
    client._active_call = call

    result = client._ask({"legal_choices": [{"choice_id": "defer"}]}, None, lambda: "fallback")

    assert result == "defer"
    assert captured["runner_kind"] == "module"
    assert captured["request_id"] == "s1:r1:t2:p1:trick:4"
    assert captured["resume_token"]
    assert captured["frame_id"] == "seq:trick:1:p0"
    assert captured["module_id"] == "mod:trick_sequence:1:p0:choice"
    assert captured["module_type"] == "TrickChoiceModule"
    assert captured["module_cursor"] == "await_trick_prompt"
    assert captured["runtime_module"]["idempotency_key"] == "idem:trick"
    assert state.runtime_active_prompt is not None
    assert state.runtime_active_prompt.module_cursor == "await_trick_prompt"
