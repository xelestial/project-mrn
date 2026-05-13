from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime_modules.contracts import FrameState, ModuleRef
from apps.server.src.services.decision_gateway import METHOD_SPECS
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import _LocalHumanDecisionClient

ROOT_DIR = Path(__file__).resolve().parents[3]
ROUND_COMBINATION_PACK = ROOT_DIR / "packages/runtime-contracts/ws/examples/round-combination.regression-pack.json"


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


def _contract_prompt(entry: dict, index: int) -> dict:
    request_type = str(entry["request_type"])
    prompt_module_by_type = {
        "mark_target": "TargetJudicatorModule",
        "trick_to_use": "TrickChoiceModule",
        "hidden_trick_card": "TrickChoiceModule",
        "specific_trick_reward": "TrickResolveModule",
        "movement": "MapMoveModule",
        "lap_reward": "LapRewardModule",
        "purchase_tile": "PurchaseDecisionModule",
        "coin_placement": "ScoreTokenPlacementPromptModule",
        "burden_exchange": "ResupplyModule",
    }
    module_type = prompt_module_by_type.get(request_type, "MapMoveModule")
    frame_contract = str(entry.get("frame_contract") or "")
    frame_prefix = {
        "TurnFrame": "turn",
        "TrickSequenceFrame": "seq:trick",
        "ActionSequenceFrame": "seq:action",
        "SimultaneousResolutionFrame": "simul:resupply",
    }.get(frame_contract, "turn")
    frame_id = f"{frame_prefix}:contract:{index}:p0"
    prompt = {
        "runner_kind": "module",
        "request_id": f"req_contract_{index}_{request_type}",
        "request_type": request_type,
        "player_id": 1,
        "timeout_ms": 30000,
        "resume_token": f"resume_contract_{index}",
        "frame_id": frame_id,
        "module_id": f"mod:{frame_id}:{request_type}",
        "module_type": module_type,
        "module_cursor": f"{request_type}:await_choice",
        "legal_choices": [{"choice_id": "choice_1"}],
    }
    if entry.get("resume_contract") == "SimultaneousPromptBatchContinuation":
        prompt.update(
            {
                "batch_id": f"batch:{frame_id}",
                "missing_player_ids": [1],
                "resume_tokens_by_player_id": {"1": f"resume_contract_{index}"},
            }
        )
    return prompt


def _decision_from_prompt(prompt: dict) -> dict:
    return {
        "request_id": prompt["request_id"],
        "player_id": prompt["player_id"],
        "choice_id": "choice_1",
        "resume_token": prompt["resume_token"],
        "frame_id": prompt["frame_id"],
        "module_id": prompt["module_id"],
        "module_type": prompt["module_type"],
        "module_cursor": prompt["module_cursor"],
        "batch_id": prompt.get("batch_id"),
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
            command = {
                "seq": len(commands) + 1,
                "session_id": session_id,
                "type": command_type,
                "payload": dict(payload),
                "kwargs": dict(kwargs),
            }
            commands.append(command)
            return command

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
        "missing_player_ids": [1],
        "resume_tokens_by_player_id": {"1": "token_1"},
        "module_id": "mod:simul:resupply:1:1:resupply",
        "module_type": "ResupplyModule",
    }
    pending = service.create_prompt("s1", prompt)

    assert pending.payload["batch_id"] == "batch_1"
    assert pending.payload["missing_player_ids"] == [1]
    assert pending.payload["resume_tokens_by_player_id"] == {"1": "token_1"}
    assert pending.payload["module_type"] == "ResupplyModule"


def test_timeout_fallback_decision_preserves_batch_continuation_inside_decision() -> None:
    commands: list[dict] = []

    class _CommandStore:
        def append_command(self, session_id, command_type, payload, **kwargs):  # noqa: ANN001
            commands.append({"session_id": session_id, "type": command_type, "payload": dict(payload)})

    service = PromptService(command_store=_CommandStore())
    prompt = {
        **_module_prompt(),
        "request_id": "batch:simul:resupply:2:107:mod:simul:resupply:2:107:resupply:1:p1",
        "player_id": 2,
        "request_type": "burden_exchange",
        "frame_id": "simul:resupply:2:107",
        "module_id": "mod:simul:resupply:2:107:resupply",
        "module_type": "ResupplyModule",
        "module_cursor": "await_resupply_batch:1",
        "batch_id": "batch:simul:resupply:2:107:mod:simul:resupply:2:107:resupply:1",
        "missing_player_ids": [2],
        "resume_tokens_by_player_id": {"2": "token_1"},
        "legal_choices": [{"choice_id": "yes"}, {"choice_id": "no"}],
    }
    pending = service.create_prompt("s1", prompt)

    decision = service.record_timeout_fallback_decision(pending, choice_id="yes", submitted_at_ms=123)

    assert decision["batch_id"] == prompt["batch_id"]
    assert decision["frame_id"] == prompt["frame_id"]
    assert decision["module_id"] == prompt["module_id"]
    assert decision["module_type"] == prompt["module_type"]
    assert decision["module_cursor"] == prompt["module_cursor"]
    command_payload = commands[0]["payload"]
    assert command_payload["batch_id"] == prompt["batch_id"]
    assert command_payload["decision"]["batch_id"] == prompt["batch_id"]


def test_simultaneous_module_prompt_requires_batch_id() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "resupply_1:p1",
        "request_type": "burden_exchange",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:resupply",
        "module_type": "ResupplyModule",
        "module_cursor": "await_resupply_batch:1",
    }

    with pytest.raises(ValueError, match="missing_batch_id"):
        service.create_prompt("s1", prompt)


def test_single_player_prompt_inside_simultaneous_frame_does_not_require_batch_state() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "hidden_1",
        "request_type": "hidden_trick_card",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:resupply",
        "module_type": "ResupplyModule",
        "module_cursor": "hidden_trick_card:await_choice",
    }

    pending = service.create_prompt("s1", prompt)

    assert pending.payload["request_type"] == "hidden_trick_card"
    assert "batch_id" not in pending.payload


def test_simultaneous_module_prompt_requires_batch_wire_state() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "resupply_1:p1",
        "request_type": "burden_exchange",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:resupply",
        "module_type": "ResupplyModule",
        "module_cursor": "await_resupply_batch:1",
        "batch_id": "batch:simul:resupply:1:0",
    }

    with pytest.raises(ValueError, match="missing_simultaneous_batch_state"):
        service.create_prompt("s1", prompt)


def test_prompt_decision_contract_matrix_preserves_required_wire_fields() -> None:
    commands: list[dict] = []

    class _CommandStore:
        def append_command(self, session_id, command_type, payload, **kwargs):  # noqa: ANN001
            command = {
                "seq": len(commands) + 1,
                "session_id": session_id,
                "type": command_type,
                "payload": dict(payload),
                "kwargs": dict(kwargs),
            }
            commands.append(command)
            return command

    pack = json.loads(ROUND_COMBINATION_PACK.read_text(encoding="utf-8"))
    service = PromptService(command_store=_CommandStore())

    for index, entry in enumerate(pack["prompt_decision_contract_matrix"], start=1):
        prompt = _contract_prompt(entry, index)
        pending = service.create_prompt("s1", prompt)
        result = service.submit_decision(_decision_from_prompt(prompt))

        assert result["status"] == "accepted"
        assert prompt["module_type"] in entry["owner_modules"]
        for field in entry["required_wire_fields"]:
            assert pending.payload[field], f"{entry['request_type']} prompt missing {field}"
            assert commands[-1]["payload"][field], f"{entry['request_type']} command missing {field}"


def test_prompt_decision_contract_matrix_request_types_are_decision_gateway_specs() -> None:
    pack = json.loads(ROUND_COMBINATION_PACK.read_text(encoding="utf-8"))
    gateway_request_types = {spec.request_type for spec in METHOD_SPECS.values()}

    for entry in pack["prompt_decision_contract_matrix"]:
        assert entry["request_type"] in gateway_request_types


def test_local_human_prompt_created_inside_module_attaches_active_continuation() -> None:
    captured: dict = {}
    stable_request_input: dict = {}

    class _Gateway:
        def _stable_prompt_request_id(self, envelope, public_context):  # noqa: ANN001
            stable_request_input.update(envelope)
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

    result = client._ask({"player_id": 0, "legal_choices": [{"choice_id": "defer"}]}, None, lambda: "fallback")

    assert result == "defer"
    assert captured["runner_kind"] == "module"
    assert captured["player_id"] == 1
    assert captured["request_id"] == "s1:r1:t2:p1:trick:4"
    assert stable_request_input["frame_id"] == "seq:trick:1:p0"
    assert stable_request_input["module_id"] == "mod:trick_sequence:1:p0:choice"
    assert stable_request_input["module_cursor"] == "await_trick_prompt"
    assert captured["resume_token"]
    assert captured["frame_id"] == "seq:trick:1:p0"
    assert captured["module_id"] == "mod:trick_sequence:1:p0:choice"
    assert captured["module_type"] == "TrickChoiceModule"
    assert captured["module_cursor"] == "await_trick_prompt"
    assert captured["runtime_module"]["idempotency_key"] == "idem:trick"
    assert state.runtime_active_prompt is not None
    assert state.runtime_active_prompt.module_cursor == "await_trick_prompt"
