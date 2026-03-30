from __future__ import annotations

from apps.server.src.core.error_payload import build_error_payload


def test_error_payload_maps_internal_server_error_to_runtime_category() -> None:
    payload = build_error_payload(code="INTERNAL_SERVER_ERROR", message="boom")
    assert payload["code"] == "INTERNAL_SERVER_ERROR"
    assert payload["category"] == "runtime"
    assert payload["retryable"] is True


def test_error_payload_maps_http_exception_to_transport_category() -> None:
    payload = build_error_payload(code="HTTP_EXCEPTION", message="bad request", retryable=False)
    assert payload["code"] == "HTTP_EXCEPTION"
    assert payload["category"] == "transport"
    assert payload["retryable"] is False
