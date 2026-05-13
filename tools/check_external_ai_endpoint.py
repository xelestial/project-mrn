from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _request_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=5) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def _sample_decision_request() -> dict[str, Any]:
    return {
        "request_id": "smoke-request-1",
        "session_id": "smoke-session-1",
        "seat": 1,
        "decision_name": "choose_purchase_tile",
        "request_type": "purchase_tile",
        "player_id": 2,
        "transport": "http",
        "fallback_policy": "engine_default",
        "public_context": {
            "round_index": 3,
            "turn_index": 4,
            "tile_index": 14,
            "tile_zone": "green",
            "tile_kind": "T3",
            "tile_purchase_cost": 3,
            "tile_rent_cost": 5,
            "player_cash": 12,
            "player_shards": 2,
            "player_position": 14,
            "source": "landing",
        },
        "legal_choices": [
            {"choice_id": "yes", "title": "Buy tile 14", "value": {"buy": True, "tile_index": 14, "cost": 3}},
            {"choice_id": "no", "title": "Skip purchase", "value": {"buy": False, "tile_index": 14, "cost": 3}},
        ],
        "worker_contract_version": "v1",
        "required_capabilities": ["choice_id_response", "healthcheck"],
    }


def _is_loopback_base_url(base_url: str) -> bool:
    parsed = urlparse(str(base_url or ""))
    host = (parsed.hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _auth_headers(auth_header: str, auth_value: str, *, require_auth: bool = False) -> dict[str, str]:
    header = str(auth_header or "").strip()
    value = str(auth_value or "").strip()
    if require_auth and (not header or not value):
        raise ValueError("--require-auth requires both --auth-header and --auth-value")
    return {header: value} if header and value else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-check an MRN external AI worker endpoint.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--auth-header", default="")
    parser.add_argument("--auth-value", default="")
    parser.add_argument("--require-auth", action="store_true")
    parser.add_argument("--require-non-local-endpoint", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--require-adapter", default="")
    parser.add_argument("--require-profile", default="")
    parser.add_argument("--require-policy-class", default="")
    parser.add_argument("--require-decision-style", default="")
    parser.add_argument("--require-request-type", action="append", default=[])
    parser.add_argument("--summary-out", default="")
    args = parser.parse_args(argv)

    try:
        headers = _auth_headers(args.auth_header, args.auth_value, require_auth=args.require_auth)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.require_non_local_endpoint and _is_loopback_base_url(args.base_url):
        print(
            "ERROR: --require-non-local-endpoint rejects loopback/local worker endpoints",
            file=sys.stderr,
        )
        return 1

    try:
        health = _request_json(f"{args.base_url.rstrip('/')}/health", headers=headers)
        decide = _request_json(
            f"{args.base_url.rstrip('/')}/decide",
            method="POST",
            body=_sample_decision_request(),
            headers=headers,
        )
    except urllib.error.URLError as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    problems: list[str] = []
    if args.require_ready and health.get("ready") is not True:
        problems.append("worker not ready")
    if args.require_adapter and health.get("worker_adapter") != args.require_adapter:
        problems.append(f"adapter mismatch: {health.get('worker_adapter')} != {args.require_adapter}")
    if args.require_profile and health.get("worker_profile") != args.require_profile:
        problems.append(f"profile mismatch: {health.get('worker_profile')} != {args.require_profile}")
    if args.require_policy_class and health.get("policy_class") != args.require_policy_class:
        problems.append(f"policy_class mismatch: {health.get('policy_class')} != {args.require_policy_class}")
    if args.require_decision_style and health.get("decision_style") != args.require_decision_style:
        problems.append(f"decision_style mismatch: {health.get('decision_style')} != {args.require_decision_style}")

    supported_request_types = set(health.get("supported_request_types") or [])
    for request_type in args.require_request_type:
        if request_type not in supported_request_types:
            problems.append(f"missing request type support: {request_type}")

    if not decide.get("choice_id"):
        problems.append("decision response missing choice_id")

    summary = {"health": health, "decide": decide}
    raw = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.summary_out:
        Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_out).write_text(raw + "\n", encoding="utf-8")
    print(raw)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print("OK: external AI endpoint passed smoke checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
