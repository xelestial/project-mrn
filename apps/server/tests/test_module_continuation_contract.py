from __future__ import annotations

from apps.server.src.domain.module_continuation_contract import (
    missing_module_continuation_fields,
    simultaneous_batch_state_error,
)


def _base_simultaneous_prompt() -> dict:
    return {
        "runner_kind": "module",
        "request_id": "req_resupply_p1",
        "request_type": "burden_exchange",
        "player_id": 1,
        "resume_token": "resume:1",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:processing",
        "module_type": "ResupplyModule",
        "module_cursor": "await_resupply_batch:1",
        "batch_id": "batch:simul:resupply:1:0",
        "legal_choices": [{"choice_id": "yes"}],
    }


def test_missing_module_continuation_fields_reports_required_engine_resume_fields() -> None:
    payload = _base_simultaneous_prompt()
    payload.pop("resume_token")
    payload["module_cursor"] = ""

    assert missing_module_continuation_fields(payload) == ["resume_token", "module_cursor"]


def test_simultaneous_batch_state_requires_numeric_engine_bridge_not_only_public_companions() -> None:
    payload = {
        **_base_simultaneous_prompt(),
        "missing_public_player_ids": ["player:1"],
        "resume_tokens_by_public_player_id": {"player:1": "resume:1"},
        "missing_seat_ids": ["seat:1"],
        "resume_tokens_by_seat_id": {"seat:1": "resume:1"},
    }

    assert simultaneous_batch_state_error(payload) == "missing_simultaneous_batch_state"


def test_simultaneous_batch_state_accepts_numeric_engine_bridge_with_public_companions() -> None:
    payload = {
        **_base_simultaneous_prompt(),
        "missing_player_ids": [1],
        "resume_tokens_by_player_id": {"1": "resume:1"},
        "missing_public_player_ids": ["player:1"],
        "resume_tokens_by_public_player_id": {"player:1": "resume:1"},
    }

    assert simultaneous_batch_state_error(payload) is None
