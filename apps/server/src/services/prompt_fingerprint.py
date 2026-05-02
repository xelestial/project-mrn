from __future__ import annotations

import hashlib
import json
from typing import Any


PROMPT_FINGERPRINT_VERSION = "prompt-fingerprint-v1"


def build_prompt_fingerprint(prompt: dict[str, Any]) -> str:
    material = _fingerprint_material(prompt)
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def ensure_prompt_fingerprint(prompt: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(prompt)
    enriched["prompt_fingerprint_version"] = PROMPT_FINGERPRINT_VERSION
    enriched["prompt_fingerprint"] = build_prompt_fingerprint(enriched)
    return enriched


def prompt_fingerprint_mismatch(expected_payload: dict[str, Any], actual_payload: dict[str, Any]) -> bool:
    expected = str(expected_payload.get("prompt_fingerprint") or "").strip()
    actual = str(actual_payload.get("prompt_fingerprint") or "").strip()
    return bool(expected and actual and expected != actual)


def _fingerprint_material(prompt: dict[str, Any]) -> dict[str, Any]:
    public_context = prompt.get("public_context")
    if not isinstance(public_context, dict):
        public_context = {}
    return {
        "version": PROMPT_FINGERPRINT_VERSION,
        "request_type": _normalize(prompt.get("request_type")),
        "player_id": _normalize(prompt.get("player_id")),
        "round_index": _normalize(prompt.get("round_index", public_context.get("round_index"))),
        "turn_index": _normalize(prompt.get("turn_index", public_context.get("turn_index"))),
        "runner_kind": _normalize(prompt.get("runner_kind") or prompt.get("runtime_runner_kind")),
        "resume_token": _normalize(prompt.get("resume_token")),
        "frame_id": _normalize(prompt.get("frame_id")),
        "module_id": _normalize(prompt.get("module_id")),
        "module_type": _normalize(prompt.get("module_type")),
        "batch_id": _normalize(prompt.get("batch_id")),
        "legal_choices": _normalize(prompt.get("legal_choices") or []),
        "public_context": _normalize(public_context),
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in {"prompt_fingerprint", "prompt_fingerprint_version"}
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
