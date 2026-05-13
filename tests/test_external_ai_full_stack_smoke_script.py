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
        "decision_name": "choose_movement",
        "request_type": "movement",
        "fallback_policy": "ai",
        "public_context": {"turn_index": 3},
        "legal_choices": [{"choice_id": "dice"}],
        "transport": "http",
        "worker_contract_version": "v1",
        "required_capabilities": ["choice_id_response"],
    }


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
        "choice_id": "dice",
        "choice_payload": {"source": "worker"},
        "prompt_fingerprint": "pf_123",
        "prompt_fingerprint_version": "prompt_fingerprint.v1",
    }
