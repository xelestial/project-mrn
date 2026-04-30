from __future__ import annotations

import json

from fastapi import APIRouter, Depends, status

from apps.server.src.core.admin_auth import admin_error, require_admin
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


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


@router.get("/sessions/{session_id}/recovery", dependencies=[Depends(require_admin)])
def admin_recovery(
    session_id: str,
    sessions: SessionService = Depends(_sessions),
    runtime: RuntimeService = Depends(_runtime),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        admin_error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
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


@router.get("/sessions/{session_id}/archive", dependencies=[Depends(require_admin)])
def admin_archive(
    session_id: str,
    sessions: SessionService = Depends(_sessions),
    archive_service=Depends(_archive_service),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        admin_error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    if archive_service is None:
        admin_error("ARCHIVE_UNAVAILABLE", "Archive service is not configured.", status.HTTP_404_NOT_FOUND)
    archive_path = archive_service.archive_path_for(session_id)
    if not archive_path.exists() or not archive_path.is_file():
        admin_error("ARCHIVE_NOT_FOUND", "Archive file not found.", status.HTTP_404_NOT_FOUND)
    try:
        payload = json.loads(archive_path.read_text(encoding="utf-8"))
    except Exception:
        admin_error("ARCHIVE_READ_FAILED", "Archive file could not be read.", status.HTTP_500_INTERNAL_SERVER_ERROR)
    if not isinstance(payload, dict):
        admin_error("ARCHIVE_INVALID", "Archive file is not a JSON object.", status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _ok(payload)
