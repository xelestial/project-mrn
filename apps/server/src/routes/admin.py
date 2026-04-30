from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, status

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionNotFoundError, SessionService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _sessions() -> SessionService:
    from apps.server.src.state import session_service

    return session_service


def _runtime() -> RuntimeService:
    from apps.server.src.state import runtime_service

    return runtime_service


def _archive_service():
    from apps.server.src.state import archive_service

    return archive_service


def _admin_token() -> str:
    from apps.server.src.state import runtime_settings

    return str(getattr(runtime_settings, "admin_token", "") or "")


def _error(code: str, message: str, http_status: int) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "ok": False,
            "data": None,
            "error": build_error_payload(code=code, message=message, retryable=False),
        },
    )


def _require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> None:
    expected = _admin_token()
    if not expected:
        _error("ADMIN_AUTH_DISABLED", "Admin API is not configured.", status.HTTP_403_FORBIDDEN)
    provided = _extract_admin_token(x_admin_token=x_admin_token, authorization=authorization)
    if not provided or not hmac.compare_digest(provided, expected):
        _error("ADMIN_UNAUTHORIZED", "Admin token is invalid.", status.HTTP_401_UNAUTHORIZED)


def _extract_admin_token(*, x_admin_token: str | None, authorization: str | None) -> str:
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()
    raw = str(authorization or "").strip()
    prefix = "bearer "
    if raw.lower().startswith(prefix):
        return raw[len(prefix) :].strip()
    return ""


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


@router.get("/sessions/{session_id}/recovery", dependencies=[Depends(_require_admin)])
def admin_recovery(
    session_id: str,
    sessions: SessionService = Depends(_sessions),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    recovery = runtime.recovery_checkpoint(session_id)
    return _ok(
        {
            "schema_version": 1,
            "schema_name": "mrn.admin_recovery",
            "visibility": "admin",
            "browser_safe": False,
            "session_id": session_id,
            "recovery_checkpoint": recovery,
        }
    )


@router.get("/sessions/{session_id}/archive", dependencies=[Depends(_require_admin)])
def admin_archive(
    session_id: str,
    sessions: SessionService = Depends(_sessions),
    archive_service=Depends(_archive_service),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        _error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    if archive_service is None:
        _error("ARCHIVE_UNAVAILABLE", "Archive service is not configured.", status.HTTP_404_NOT_FOUND)
    archive_path = archive_service.archive_path_for(session_id)
    if not archive_path.exists() or not archive_path.is_file():
        _error("ARCHIVE_NOT_FOUND", "Archive file not found.", status.HTTP_404_NOT_FOUND)
    try:
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
    except Exception:
        _error("ARCHIVE_READ_FAILED", "Archive file could not be read.", status.HTTP_500_INTERNAL_SERVER_ERROR)
    if not isinstance(payload, dict):
        _error("ARCHIVE_INVALID", "Archive file is not a JSON object.", status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _ok(payload)
