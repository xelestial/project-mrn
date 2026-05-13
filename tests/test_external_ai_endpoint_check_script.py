from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/check_external_ai_endpoint.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_external_ai_endpoint", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_requires_auth_before_contacting_endpoint(monkeypatch) -> None:
    module = _load_module()
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_request_json(url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((url, kwargs.get("headers")))
        return {}

    monkeypatch.setattr(module, "_request_json", fake_request_json)

    assert module.main(["--base-url", "https://worker.example.test", "--require-auth"]) == 1
    assert calls == []


def test_requires_non_local_endpoint_before_contacting_endpoint(monkeypatch) -> None:
    module = _load_module()
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_request_json(url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((url, kwargs.get("headers")))
        return {}

    monkeypatch.setattr(module, "_request_json", fake_request_json)

    assert (
        module.main(
            [
                "--base-url",
                "http://127.0.0.1:8011",
                "--require-non-local-endpoint",
                "--auth-header",
                "X-Worker-Auth",
                "--auth-value",
                "Token secret",
                "--require-auth",
            ]
        )
        == 1
    )
    assert calls == []


def test_remote_endpoint_smoke_writes_summary_and_passes_auth_headers(monkeypatch, tmp_path) -> None:
    module = _load_module()
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def fake_request_json(url: str, *, method: str = "GET", **kwargs: Any) -> dict[str, Any]:
        calls.append((url, method, kwargs.get("headers")))
        if url.endswith("/health"):
            return {
                "ready": True,
                "worker_adapter": "priority_score_v1",
                "worker_profile": "priority_scored",
                "policy_class": "PriorityScoredPolicy",
                "decision_style": "priority_scored_contract",
                "supported_request_types": ["movement", "purchase_tile"],
            }
        return {"choice_id": "yes"}

    monkeypatch.setattr(module, "_request_json", fake_request_json)
    summary_path = tmp_path / "summary.json"

    assert (
        module.main(
            [
                "--base-url",
                "https://worker.example.test",
                "--require-non-local-endpoint",
                "--auth-header",
                "X-Worker-Auth",
                "--auth-value",
                "Token secret",
                "--require-auth",
                "--require-ready",
                "--require-adapter",
                "priority_score_v1",
                "--require-profile",
                "priority_scored",
                "--require-policy-class",
                "PriorityScoredPolicy",
                "--require-decision-style",
                "priority_scored_contract",
                "--require-request-type",
                "movement",
                "--summary-out",
                str(summary_path),
            ]
        )
        == 0
    )
    assert calls == [
        ("https://worker.example.test/health", "GET", {"X-Worker-Auth": "Token secret"}),
        ("https://worker.example.test/decide", "POST", {"X-Worker-Auth": "Token secret"}),
    ]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["decide"]["choice_id"] == "yes"
