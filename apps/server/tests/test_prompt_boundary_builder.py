from __future__ import annotations

from types import SimpleNamespace

from apps.server.src.services.prompt_boundary_builder import PromptBoundaryBuilder


def test_prompt_boundary_builder_allocates_next_instance_and_merges_request_context() -> None:
    builder = PromptBoundaryBuilder(current_prompt_sequence=3)
    active_call = SimpleNamespace(
        request=SimpleNamespace(
            request_type="movement",
            player_id=0,
            fallback_policy="required",
            public_context={"round_index": 1, "turn_index": 2},
        )
    )

    envelope = builder.prepare(
        {"public_context": {"source": "prompt"}},
        active_call=active_call,
    )

    assert builder.current_prompt_sequence() == 4
    assert envelope["prompt_instance_id"] == 4
    assert envelope["request_type"] == "movement"
    assert envelope["player_id"] == 1
    assert envelope["fallback_policy"] == "required"
    assert envelope["public_context"] == {"source": "prompt", "round_index": 1, "turn_index": 2}


def test_prompt_boundary_builder_can_replace_existing_prompt_instance_for_bridge_ask() -> None:
    builder = PromptBoundaryBuilder(current_prompt_sequence=8)

    envelope = builder.prepare({"prompt_instance_id": 2}, replace_prompt_instance_id=True)

    assert builder.current_prompt_sequence() == 9
    assert envelope["prompt_instance_id"] == 9


def test_prompt_boundary_builder_adds_public_prompt_identity_companions() -> None:
    builder = PromptBoundaryBuilder(current_prompt_sequence=4)

    envelope = builder.prepare({"request_id": "s1:r1:t2:p1:movement:5"})

    assert envelope["request_id"] == "s1:r1:t2:p1:movement:5"
    assert envelope["prompt_instance_id"] == 5
    assert envelope["legacy_request_id"] == "s1:r1:t2:p1:movement:5"
    assert envelope["public_request_id"].startswith("req_")
    assert envelope["public_prompt_instance_id"].startswith("pin_")


def test_prompt_boundary_builder_does_not_rewrap_public_request_id() -> None:
    builder = PromptBoundaryBuilder(current_prompt_sequence=4)

    envelope = builder.prepare(
        {
            "request_id": "req_public_1",
            "legacy_request_id": "s1:r1:t2:p1:movement:5",
        }
    )

    assert envelope["request_id"] == "req_public_1"
    assert envelope["public_request_id"] == "req_public_1"
    assert envelope["legacy_request_id"] == "s1:r1:t2:p1:movement:5"
    assert envelope["public_prompt_instance_id"].startswith("pin_")
