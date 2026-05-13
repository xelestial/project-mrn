from __future__ import annotations

from apps.server.src.domain.protocol_ids import (
    legacy_prompt_request_id,
    prompt_protocol_identity_fields,
    stable_prompt_request_id,
)


def test_stable_prompt_request_id_uses_legacy_shape_without_boundary_identity() -> None:
    request_id = stable_prompt_request_id(
        session_id="s1",
        envelope={"request_type": "movement", "player_id": 1, "prompt_instance_id": 5},
        public_context={"round_index": 2, "turn_index": 3},
    )

    assert request_id == "s1:r2:t3:p1:movement:5"


def test_legacy_prompt_request_id_keeps_external_payload_adapter_shape() -> None:
    request_id = legacy_prompt_request_id(
        session_id="s1",
        public_context={"round_index": 2, "turn_index": 3},
        request_type="movement",
        player_id=1,
        prompt_instance_id=5,
    )

    assert request_id == "s1:r2:t3:p1:movement:5"


def test_stable_prompt_request_id_includes_module_boundary_identity() -> None:
    request_id = stable_prompt_request_id(
        session_id="s1",
        envelope={
            "request_type": "movement",
            "player_id": 1,
            "prompt_instance_id": 4,
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:move",
            "module_cursor": "await_choice",
        },
        public_context={"round_index": 1, "turn_index": 1},
    )

    assert request_id == (
        "s1:prompt:frame:turn%3A1%3Ap0:module:mod%3Aturn%3A1%3Amove:"
        "cursor:await_choice:p1:movement:4"
    )
    assert request_id.endswith(":movement:4")


def test_stable_prompt_request_id_distinguishes_same_turn_prompts_by_module_boundary() -> None:
    base_envelope = {
        "request_type": "movement",
        "player_id": 1,
        "prompt_instance_id": 4,
    }
    public_context = {"round_index": 1, "turn_index": 1}

    first = stable_prompt_request_id(
        session_id="s1",
        envelope={
            **base_envelope,
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:move",
            "module_cursor": "await_choice",
        },
        public_context=public_context,
    )
    second = stable_prompt_request_id(
        session_id="s1",
        envelope={
            **base_envelope,
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:trick",
            "module_cursor": "await_choice",
        },
        public_context=public_context,
    )

    assert first != second
    assert first == stable_prompt_request_id(
        session_id="s1",
        envelope={
            **base_envelope,
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:move",
            "module_cursor": "await_choice",
        },
        public_context=public_context,
    )


def test_stable_prompt_request_id_reads_nested_runtime_module_identity() -> None:
    request_id = stable_prompt_request_id(
        session_id="s1",
        envelope={
            "request_type": "burden_exchange",
            "player_id": 2,
            "prompt_instance_id": 9,
            "batch_id": "batch:simul:1",
            "runtime_module": {
                "frame_id": "simul:1",
                "module_id": "mod:simul:1:resupply",
                "module_cursor": "await_resupply_batch:1",
            },
        },
        public_context={"round_index": 1, "turn_index": 1},
    )

    assert request_id == (
        "s1:prompt:batch:batch%3Asimul%3A1:frame:simul%3A1:"
        "module:mod%3Asimul%3A1%3Aresupply:cursor:await_resupply_batch%3A1:"
        "p2:burden_exchange:9"
    )


def test_prompt_protocol_identity_fields_are_stable_opaque_companions() -> None:
    identity = prompt_protocol_identity_fields(
        request_id="s1:r2:t3:p1:movement:5",
        prompt_instance_id=5,
    )
    repeat = prompt_protocol_identity_fields(
        request_id="s1:r2:t3:p1:movement:5",
        prompt_instance_id=5,
    )
    other = prompt_protocol_identity_fields(
        request_id="s1:r2:t3:p1:movement:6",
        prompt_instance_id=6,
    )

    assert identity == repeat
    assert identity["legacy_request_id"] == "s1:r2:t3:p1:movement:5"
    assert identity["public_request_id"].startswith("req_")
    assert identity["public_prompt_instance_id"].startswith("pin_")
    assert identity["public_request_id"] != identity["legacy_request_id"]
    assert identity["public_request_id"] != other["public_request_id"]
