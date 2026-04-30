from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from apps.server.src.core.error_payload import build_error_payload


def admin_error(code: str, message: str, http_status: int) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "ok": False,
            "data": None,
            "error": build_error_payload(code=code, message=message, retryable=False),
        },
    )


def require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> None:
    expected = _configured_admin_token()
    if not expected:
        admin_error("ADMIN_AUTH_DISABLED", "Admin API is not configured.", status.HTTP_403_FORBIDDEN)
    provided = extract_admin_token(x_admin_token=x_admin_token, authorization=authorization)
    if not provided or not hmac.compare_digest(provided, expected):
        admin_error("ADMIN_UNAUTHORIZED", "Admin token is invalid.", status.HTTP_401_UNAUTHORIZED)


def extract_admin_token(*, x_admin_token: str | None, authorization: str | None) -> str:
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()
    raw = str(authorization or "").strip()
    prefix = "bearer "
    if raw.lower().startswith(prefix):
        return raw[len(prefix) :].strip()
    return ""


def _configured_admin_token() -> str:
    from apps.server.src.state import runtime_settings

    return str(getattr(runtime_settings, "admin_token", "") or "")
