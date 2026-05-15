from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/scripts/external_ai_full_stack_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("external_ai_full_stack_smoke", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_worker_request_from_pending_prompt_uses_external_ai_contract_fields() -> None:
    module = _load_module()
    pending = {
        "request_id": "ai_req_1",
        "session_id": "sess_1",
        "seat": 1,
        "player_id": 10,
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
        "transport": "http",
        "worker_contract_version": "v1",
        "required_capabilities": ["choice_id_response"],
    }

    request = module._worker_request_from_pending_prompt(pending, fallback_seat=1)

    assert request == {
        "request_id": "ai_req_1",
        "session_id": "sess_1",
        "seat": 1,
        "player_id": 10,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": 10,
        "primary_player_id_source": "legacy",
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
        "transport": "http",
        "worker_contract_version": "v1",
        "required_capabilities": ["choice_id_response"],
    }


def test_worker_request_preserves_protocol_identity_companions() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_1",
        "legacy_request_id": "ai_req_1",
        "public_request_id": "req_public_1",
        "public_prompt_instance_id": "ppi_public_1",
        "session_id": "sess_1",
        "seat": 1,
        "player_id": 10,
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
        "seat_id": "seat_public_1",
        "viewer_id": "viewer_public_1",
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
    }

    request = module._worker_request_from_pending_prompt(pending, fallback_seat=1)

    assert request["request_id"] == "req_public_1"
    assert "player_id" not in request
    assert "player_id_alias_role" not in request
    assert request["primary_player_id"] == "player_public_10"
    assert request["primary_player_id_source"] == "public"
    assert request["legacy_request_id"] == "ai_req_1"
    assert request["public_request_id"] == "req_public_1"
    assert request["public_prompt_instance_id"] == "ppi_public_1"
    assert request["legacy_player_id"] == 10
    assert request["public_player_id"] == "player_public_10"
    assert request["seat_id"] == "seat_public_1"
    assert request["viewer_id"] == "viewer_public_1"


def test_worker_request_prefers_explicit_primary_identity_over_top_level_alias() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_2",
        "session_id": "sess_1",
        "seat": 1,
        "player_id": 10,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": "player_public_10",
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
    }

    request = module._worker_request_from_pending_prompt(pending, fallback_seat=1)

    assert "player_id" not in request
    assert "player_id_alias_role" not in request
    assert request["primary_player_id"] == "player_public_10"
    assert request["primary_player_id_source"] == "public"


def test_worker_request_ignores_numeric_public_primary_when_public_companion_exists() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_bad_primary",
        "session_id": "sess_1",
        "seat": 1,
        "player_id": 10,
        "primary_player_id": 10,
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
    }

    request = module._worker_request_from_pending_prompt(pending, fallback_seat=1)

    assert "player_id" not in request
    assert "player_id_alias_role" not in request
    assert request["primary_player_id"] == "player_public_10"
    assert request["primary_player_id_source"] == "public"
    assert request["legacy_player_id"] == 10


def test_pending_prompt_summary_exposes_primary_identity_and_companions() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_summary",
        "player_id": 10,
        "primary_player_id": "player_public_10",
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
        "seat_id": "seat_public_1",
        "viewer_id": "viewer_public_1",
    }

    summary = module._pending_prompt_identity_summary(pending)

    assert summary["player_id"] == 10
    assert summary["player_id_alias_role"] == "legacy_compatibility_alias"
    assert summary["primary_player_id"] == "player_public_10"
    assert summary["primary_player_id_source"] == "public"
    assert summary["legacy_player_id"] == 10
    assert summary["public_player_id"] == "player_public_10"
    assert summary["seat_id"] == "seat_public_1"
    assert summary["viewer_id"] == "viewer_public_1"


def test_callback_payload_preserves_fingerprint_and_worker_choice_payload() -> None:
    module = _load_module()
    pending = {
        "request_id": "ai_req_1",
        "player_id": 10,
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
    }
    worker_response = {
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
        "worker_id": "worker-1",
    }

    callback = module._callback_payload_from_prompt_and_worker_response(pending, worker_response)

    assert callback == {
        "request_id": "ai_req_1",
        "player_id": 10,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": 10,
        "primary_player_id_source": "legacy",
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
    }


def test_callback_payload_preserves_protocol_identity_companions() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_1",
        "legacy_request_id": "ai_req_1",
        "public_request_id": "req_public_1",
        "public_prompt_instance_id": "ppi_public_1",
        "player_id": 10,
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
        "seat_id": "seat_public_1",
        "viewer_id": "viewer_public_1",
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
    }
    worker_response = {
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
    }

    callback = module._callback_payload_from_prompt_and_worker_response(pending, worker_response)

    assert callback == {
        "request_id": "req_public_1",
        "primary_player_id": "player_public_10",
        "primary_player_id_source": "public",
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
        "legacy_request_id": "ai_req_1",
        "public_request_id": "req_public_1",
        "public_prompt_instance_id": "ppi_public_1",
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
        "seat_id": "seat_public_1",
        "viewer_id": "viewer_public_1",
    }


def test_callback_payload_uses_primary_identity_without_top_level_player_id_when_available() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_3",
        "player_id": 10,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": "player_public_10",
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
    }
    worker_response = {
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
    }

    callback = module._callback_payload_from_prompt_and_worker_response(pending, worker_response)

    assert "player_id" not in callback
    assert "player_id_alias_role" not in callback
    assert callback["legacy_player_id"] == 10
    assert callback["primary_player_id"] == "player_public_10"
    assert callback["primary_player_id_source"] == "public"


def test_callback_payload_prefers_explicit_primary_identity_over_top_level_alias() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_2",
        "player_id": 10,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": "player_public_10",
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
    }
    worker_response = {
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
    }

    callback = module._callback_payload_from_prompt_and_worker_response(pending, worker_response)

    assert "player_id" not in callback
    assert "player_id_alias_role" not in callback
    assert callback["legacy_player_id"] == 10
    assert callback["primary_player_id"] == "player_public_10"
    assert callback["primary_player_id_source"] == "public"


def test_callback_payload_ignores_numeric_public_primary_when_public_companion_exists() -> None:
    module = _load_module()
    pending = {
        "request_id": "req_public_bad_primary",
        "player_id": 10,
        "primary_player_id": 10,
        "primary_player_id_source": "public",
        "legacy_player_id": 10,
        "public_player_id": "player_public_10",
    }
    worker_response = {
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
    }

    callback = module._callback_payload_from_prompt_and_worker_response(pending, worker_response)

    assert "player_id" not in callback
    assert "player_id_alias_role" not in callback
    assert callback["legacy_player_id"] == 10
    assert callback["primary_player_id"] == "player_public_10"
    assert callback["primary_player_id_source"] == "public"


def test_remote_smoke_requires_worker_auth_when_flagged() -> None:
    module = _load_module()

    try:
        module._worker_headers("", "", require_worker_auth=True)
    except RuntimeError as exc:
        assert "--require-worker-auth" in str(exc)
    else:
        raise AssertionError("remote worker smoke must reject missing worker auth")


def test_remote_smoke_rejects_local_worker_when_non_local_required() -> None:
    module = _load_module()

    try:
        module._require_non_local_base_url("http://127.0.0.1:8011", label="worker base URL")
    except RuntimeError as exc:
        assert "worker base URL must be non-local" in str(exc)
    else:
        raise AssertionError("remote evidence gate must reject local worker URLs")


def test_remote_smoke_accepts_non_local_worker_with_auth_header() -> None:
    module = _load_module()

    module._require_non_local_base_url("https://worker.example.test", label="worker base URL")

    assert module._worker_headers(
        "X-Worker-Auth",
        "Token secret",
        require_worker_auth=True,
    ) == {"X-Worker-Auth": "Token secret"}
