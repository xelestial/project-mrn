#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {raw}") from exc
    return json.loads(raw) if raw.strip() else {}


def _require_ok(response: dict[str, Any], label: str) -> dict[str, Any]:
    if response.get("ok") is not True:
        raise RuntimeError(f"{label} failed: {json.dumps(response, ensure_ascii=False)}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} returned non-object data: {json.dumps(response, ensure_ascii=False)}")
    return data


def _default_session_payload(*, worker_base_url: str, seed: int) -> dict[str, Any]:
    worker_url = worker_base_url.rstrip("/")
    return {
        "seats": [
            {
                "seat": 1,
                "seat_type": "ai",
                "ai_profile": "balanced",
                "participant_client": "external_ai",
                "participant_config": {"endpoint": worker_url},
            },
            {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
        ],
        "config": {
            "seed": seed,
            "seat_limits": {"min": 2, "max": 2, "allowed": [1, 2]},
            "participants": {
                "external_ai": {
                    "transport": "http",
                    "contract_version": "v1",
                    "endpoint": worker_url,
                    "healthcheck_policy": "required",
                    "require_ready": True,
                    "required_capabilities": ["choice_id_response", "healthcheck"],
                    "timeout_ms": 9000,
                    "retry_count": 1,
                    "backoff_ms": 100,
                    "fallback_mode": "local_ai",
                }
            },
        },
    }


_IDENTITY_COMPANION_FIELDS = (
    "legacy_request_id",
    "public_request_id",
    "public_prompt_instance_id",
    "legacy_player_id",
    "public_player_id",
    "seat_id",
    "viewer_id",
)


def _copy_identity_companions(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field in _IDENTITY_COMPANION_FIELDS:
        value = source.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if field == "legacy_player_id":
            target[field] = int(value)
            continue
        target[field] = str(value).strip() if isinstance(value, str) else value


def _numeric_legacy_player_id(source: dict[str, Any]) -> int:
    for field in ("legacy_player_id", "player_id"):
        value = source.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return 0


def _explicit_primary_player_identity(source: dict[str, Any]) -> tuple[Any, str] | None:
    primary_player_id = source.get("primary_player_id")
    primary_player_id_source = str(source.get("primary_player_id_source") or "").strip()
    if primary_player_id_source not in {"public", "protocol", "legacy"}:
        return None
    if isinstance(primary_player_id, bool):
        return None
    if isinstance(primary_player_id, int):
        if primary_player_id_source == "legacy":
            return primary_player_id, primary_player_id_source
        return None
    if isinstance(primary_player_id, str) and primary_player_id.strip():
        stripped = primary_player_id.strip()
        if primary_player_id_source == "legacy" and stripped.isdigit():
            return int(stripped), primary_player_id_source
        return stripped, primary_player_id_source
    return None


def _primary_player_identity(source: dict[str, Any]) -> tuple[Any, str]:
    explicit_identity = _explicit_primary_player_identity(source)
    if explicit_identity is not None:
        return explicit_identity

    public_player_id = source.get("public_player_id")
    if isinstance(public_player_id, str) and public_player_id.strip():
        return public_player_id.strip(), "public"

    player_id = source.get("player_id")
    if isinstance(player_id, str) and player_id.strip() and not player_id.strip().isdigit():
        return player_id.strip(), "protocol"

    return _numeric_legacy_player_id(source), "legacy"


def _add_player_identity_metadata(target: dict[str, Any], source: dict[str, Any]) -> None:
    primary_player_id, primary_player_id_source = _primary_player_identity(source)
    if isinstance(target.get("player_id"), int) and not isinstance(target.get("player_id"), bool):
        target["player_id_alias_role"] = "legacy_compatibility_alias"
    target["primary_player_id"] = primary_player_id
    target["primary_player_id_source"] = primary_player_id_source


def _pending_prompt_identity_summary(pending: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"player_id": pending.get("player_id")}
    _add_player_identity_metadata(summary, pending)
    _copy_identity_companions(summary, pending)
    return summary


def _protocol_player_id(source: dict[str, Any]) -> Any:
    primary_player_id, primary_player_id_source = _primary_player_identity(source)
    if primary_player_id_source in {"public", "protocol"}:
        return primary_player_id

    public_player_id = source.get("public_player_id")
    if isinstance(public_player_id, str) and public_player_id.strip():
        return public_player_id.strip()

    player_id = source.get("player_id")
    if isinstance(player_id, str) and player_id.strip() and not player_id.strip().isdigit():
        return player_id.strip()

    return _numeric_legacy_player_id(source)


def _worker_request_from_pending_prompt(pending: dict[str, Any], *, fallback_seat: int) -> dict[str, Any]:
    legal_choices = pending.get("legal_choices")
    if not isinstance(legal_choices, list) or not legal_choices:
        raise RuntimeError(f"pending prompt has no legal choices: {json.dumps(pending, ensure_ascii=False)}")
    public_context = pending.get("public_context")
    required_capabilities = pending.get("required_capabilities")
    request_type = str(pending.get("request_type") or "").strip()
    request = {
        "request_id": str(pending.get("request_id") or "").strip(),
        "session_id": str(pending.get("session_id") or "").strip(),
        "seat": int(pending.get("seat") or fallback_seat),
        "player_id": _protocol_player_id(pending),
        "decision_name": str(pending.get("decision_name") or request_type or "external_ai_decision").strip(),
        "request_type": request_type,
        "fallback_policy": str(pending.get("fallback_policy") or "ai").strip(),
        "public_context": dict(public_context) if isinstance(public_context, dict) else {},
        "legal_choices": legal_choices,
        "transport": str(pending.get("transport") or "http").strip(),
        "worker_contract_version": str(pending.get("worker_contract_version") or "v1").strip(),
        "required_capabilities": list(required_capabilities) if isinstance(required_capabilities, list) else [],
    }
    _add_player_identity_metadata(request, pending)
    _copy_identity_companions(request, pending)
    return request


def _callback_payload_from_prompt_and_worker_response(
    pending: dict[str, Any],
    worker_response: dict[str, Any],
) -> dict[str, Any]:
    choice_id = str(worker_response.get("choice_id") or "").strip()
    if not choice_id:
        raise RuntimeError(f"worker response missing choice_id: {json.dumps(worker_response, ensure_ascii=False)}")
    callback: dict[str, Any] = {
        "request_id": str(pending.get("request_id") or "").strip(),
        "player_id": _protocol_player_id(pending),
        "choice_id": choice_id,
        "choice_payload": worker_response.get("choice_payload") if isinstance(worker_response.get("choice_payload"), dict) else {},
    }
    for field in ("prompt_fingerprint", "prompt_fingerprint_version"):
        value = pending.get(field)
        if value is not None:
            callback[field] = value
    _add_player_identity_metadata(callback, pending)
    _copy_identity_companions(callback, pending)
    return callback


def _poll_external_ai_prompt(
    *,
    server_base_url: str,
    session_id: str,
    admin_headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    url = f"{server_base_url.rstrip('/')}/api/v1/admin/sessions/{session_id}/external-ai/pending-prompts"
    while time.monotonic() < deadline:
        data = _require_ok(_request_json(url, headers=admin_headers), "external-ai pending prompts")
        last_payload = data
        prompts = data.get("pending_prompts")
        if isinstance(prompts, list) and prompts:
            prompt = prompts[0]
            if isinstance(prompt, dict):
                return prompt
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for external AI pending prompt; last={last_payload}")


def _admin_headers(admin_token: str) -> dict[str, str]:
    token = admin_token.strip()
    if not token:
        raise RuntimeError("admin token is required; set --admin-token or MRN_ADMIN_TOKEN")
    return {"X-Admin-Token": token}


def _is_loopback_base_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url or ""))
    host = (parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _require_non_local_base_url(base_url: str, *, label: str) -> None:
    if _is_loopback_base_url(base_url):
        raise RuntimeError(f"{label} must be non-local when remote evidence is required")


def _worker_headers(worker_auth_header: str, worker_auth_value: str, *, require_worker_auth: bool) -> dict[str, str]:
    header = str(worker_auth_header or "").strip()
    value = str(worker_auth_value or "").strip()
    if require_worker_auth and (not header or not value):
        raise RuntimeError("--require-worker-auth requires both --worker-auth-header and --worker-auth-value")
    return {header: value} if header and value else {}


def _load_session_payload(path: str, *, worker_base_url: str, seed: int) -> dict[str, Any]:
    if not path:
        return _default_session_payload(worker_base_url=worker_base_url, seed=seed)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    server_base_url = args.server_base_url.rstrip("/")
    worker_base_url = args.worker_base_url.rstrip("/")
    if getattr(args, "require_non_local_server", False):
        _require_non_local_base_url(server_base_url, label="server base URL")
    if getattr(args, "require_non_local_worker", False):
        _require_non_local_base_url(worker_base_url, label="worker base URL")
    admin_headers = _admin_headers(args.admin_token or os.getenv("MRN_ADMIN_TOKEN", ""))
    worker_headers = _worker_headers(
        args.worker_auth_header,
        args.worker_auth_value,
        require_worker_auth=getattr(args, "require_worker_auth", False),
    )

    health = _request_json(f"{worker_base_url}/health", headers=worker_headers)
    session_payload = _load_session_payload(args.session_payload, worker_base_url=worker_base_url, seed=args.seed)
    created = _require_ok(
        _request_json(f"{server_base_url}/api/v1/sessions", method="POST", body=session_payload),
        "create session",
    )
    session_id = str(created.get("session_id") or "")
    host_token = str(created.get("host_token") or "")
    if not session_id or not host_token:
        raise RuntimeError(f"create session returned invalid identifiers: {created}")

    _require_ok(
        _request_json(
            f"{server_base_url}/api/v1/sessions/{session_id}/start",
            method="POST",
            body={"host_token": host_token},
        ),
        "start session",
    )
    pending = _poll_external_ai_prompt(
        server_base_url=server_base_url,
        session_id=session_id,
        admin_headers=admin_headers,
        timeout_seconds=args.timeout_seconds,
    )
    worker_request = _worker_request_from_pending_prompt(pending, fallback_seat=args.external_seat)
    worker_response = _request_json(
        f"{worker_base_url}/decide",
        method="POST",
        body=worker_request,
        headers=worker_headers,
    )
    callback_payload = _callback_payload_from_prompt_and_worker_response(pending, worker_response)
    callback = _require_ok(
        _request_json(
            f"{server_base_url}/api/v1/sessions/{session_id}/external-ai/decisions",
            method="POST",
            body=callback_payload,
            headers=admin_headers,
        ),
        "external-ai callback",
    )
    if callback.get("status") != "accepted":
        raise RuntimeError(f"external-ai callback was not accepted: {callback}")

    remaining = _require_ok(
        _request_json(
            f"{server_base_url}/api/v1/admin/sessions/{session_id}/external-ai/pending-prompts",
            headers=admin_headers,
        ),
        "external-ai pending prompts after callback",
    )
    remaining_prompts = remaining.get("pending_prompts") if isinstance(remaining.get("pending_prompts"), list) else []
    if any(isinstance(item, dict) and item.get("request_id") == pending.get("request_id") for item in remaining_prompts):
        raise RuntimeError(f"external AI prompt still pending after accepted callback: {pending.get('request_id')}")

    return {
        "ok": True,
        "session_id": session_id,
        "worker_health": health,
        "pending_prompt": {
            "request_id": pending.get("request_id"),
            **_pending_prompt_identity_summary(pending),
            "request_type": pending.get("request_type"),
            "provider": pending.get("provider"),
            "prompt_fingerprint": pending.get("prompt_fingerprint"),
        },
        "worker_decision": {
            "choice_id": worker_response.get("choice_id"),
            "worker_id": worker_response.get("worker_id"),
            "worker_adapter": worker_response.get("worker_adapter"),
            "policy_class": worker_response.get("policy_class"),
            "decision_style": worker_response.get("decision_style"),
        },
        "callback": callback,
        "remaining_external_ai_prompt_count": len(remaining_prompts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live full-stack smoke for external_ai worker decisions.")
    parser.add_argument("--server-base-url", default="http://127.0.0.1:9090")
    parser.add_argument("--worker-base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--worker-auth-header", default="")
    parser.add_argument("--worker-auth-value", default="")
    parser.add_argument("--require-worker-auth", action="store_true")
    parser.add_argument("--require-non-local-server", action="store_true")
    parser.add_argument("--require-non-local-worker", action="store_true")
    parser.add_argument("--session-payload", default="")
    parser.add_argument("--external-seat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--summary-out", default="")
    args = parser.parse_args()

    try:
        summary = run_smoke(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    raw = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.summary_out:
        Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_out).write_text(raw + "\n", encoding="utf-8")
    print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
