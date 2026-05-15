from __future__ import annotations

import pytest

from apps.server.src.domain.protocol_identity import (
    assert_no_public_identity_numeric_leaks,
    public_identity_numeric_leaks,
)
from apps.server.src.services.decision_gateway import build_decision_ack_payload


def test_public_identity_numeric_leak_guard_rejects_numeric_public_identity_fields() -> None:
    payload = {
        "public_player_id": 2,
        "seat_id": "3",
        "viewer_id": True,
        "event_id": "4",
        "nested": {
            "acting_public_player_id": "5",
            "missing_public_player_ids": ["ply_ok", 6],
            "responses_by_public_player_id": {
                7: {"choice_id": "yes"},
                "8": {"choice_id": "no"},
                "ply_ok": {"public_player_id": "ply_ok"},
            },
        },
    }

    leaks = public_identity_numeric_leaks(payload)

    assert "$.public_player_id" in leaks
    assert "$.seat_id" in leaks
    assert "$.viewer_id" in leaks
    assert "$.event_id" in leaks
    assert "$.nested.acting_public_player_id" in leaks
    assert "$.nested.missing_public_player_ids[1]" in leaks
    assert "$.nested.responses_by_public_player_id.<key:7>" in leaks
    assert "$.nested.responses_by_public_player_id.<key:8>" in leaks
    with pytest.raises(AssertionError, match="public identity numeric leak"):
        assert_no_public_identity_numeric_leaks(payload, boundary="decision_ack")


def test_public_identity_numeric_leak_guard_allows_legacy_numeric_aliases() -> None:
    payload = {
        "player_id": 2,
        "legacy_player_id": 2,
        "seat": 2,
        "seat_index": 2,
        "turn_order_index": 2,
        "prompt_instance_id": 17,
        "public_player_id": "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "seat_id": "seat_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "viewer_id": "view_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "public_request_id": "req_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "public_prompt_instance_id": "pin_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "responses_by_player_id": {
            2: {"choice_id": "yes", "player_id": 2},
        },
        "responses_by_public_player_id": {
            "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
                "choice_id": "yes",
                "legacy_player_id": 2,
                "public_player_id": "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            },
        },
        "expected_player_ids": [1, 2],
        "expected_public_player_ids": [
            "ply_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "ply_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        ],
    }

    assert public_identity_numeric_leaks(payload) == []
    assert_no_public_identity_numeric_leaks(payload)


def test_decision_ack_builder_labels_numeric_player_id_as_legacy_alias() -> None:
    payload = build_decision_ack_payload(
        request_id="req_1",
        status="accepted",
        player_id=2,
    )

    assert payload["player_id"] == 2
    assert payload["player_id_alias_role"] == "legacy_compatibility_alias"
    assert payload["primary_player_id"] == 2
    assert payload["primary_player_id_source"] == "legacy"


def test_decision_ack_builder_emits_public_player_id_when_available() -> None:
    payload = build_decision_ack_payload(
        request_id="req_1",
        status="accepted",
        player_id=2,
        identity_fields={"public_player_id": "ply_2"},
    )

    assert payload["player_id"] == "ply_2"
    assert payload["legacy_player_id"] == 2
    assert "player_id_alias_role" not in payload
    assert payload["primary_player_id"] == "ply_2"
    assert payload["primary_player_id_source"] == "public"
