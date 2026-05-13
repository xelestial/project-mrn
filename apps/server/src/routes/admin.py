from __future__ import annotations

import json

from fastapi import APIRouter, Depends, status

from apps.server.src.core.admin_auth import admin_error, require_admin
from apps.server.src.services.prompt_service import PendingPrompt, PromptService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionNotFoundError, SessionService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _sessions() -> SessionService:
    from apps.server.src.state import session_service

    return session_service


def _runtime() -> RuntimeService:
    from apps.server.src.state import runtime_service

    return runtime_service


def _prompts() -> PromptService:
    from apps.server.src.state import prompt_service

    return prompt_service


def _archive_service():
    from apps.server.src.state import archive_service

    return archive_service


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


def _external_ai_pending_prompt_payload(pending: PendingPrompt, sessions: SessionService) -> dict:
    payload = dict(pending.payload)
    public_context = payload.get("public_context")
    legal_choices = payload.get("legal_choices")
    identity_fields = dict(sessions.protocol_identity_fields(pending.session_id, pending.player_id) or {})
    for key in ("legacy_player_id", "public_player_id", "seat_id", "viewer_id"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            identity_fields[key] = value
    result = {
        "request_id": pending.request_id,
        "legacy_request_id": str(payload.get("legacy_request_id") or pending.request_id),
        "public_request_id": str(payload.get("public_request_id") or pending.request_id),
        "session_id": pending.session_id,
        "player_id": pending.player_id,
        "seat": payload.get("seat"),
        "provider": "ai",
        "request_type": str(payload.get("request_type") or ""),
        "decision_name": str(payload.get("decision_name") or payload.get("request_type") or ""),
        "fallback_policy": str(payload.get("fallback_policy") or "ai"),
        "timeout_ms": pending.timeout_ms,
        "created_at_ms": pending.created_at_ms,
        "prompt_fingerprint": str(payload.get("prompt_fingerprint") or ""),
        "prompt_fingerprint_version": payload.get("prompt_fingerprint_version"),
        "public_context": dict(public_context) if isinstance(public_context, dict) else {},
        "legal_choices": list(legal_choices) if isinstance(legal_choices, list) else [],
        "transport": str(payload.get("transport") or "http"),
        "worker_contract_version": str(payload.get("worker_contract_version") or "v1"),
        "required_capabilities": list(payload.get("required_capabilities") or [])
        if isinstance(payload.get("required_capabilities"), list)
        else [],
    }
    public_prompt_instance_id = payload.get("public_prompt_instance_id")
    if public_prompt_instance_id is not None and str(public_prompt_instance_id).strip():
        result["public_prompt_instance_id"] = str(public_prompt_instance_id)
    result.update(identity_fields)
    return result


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


@router.get("/sessions/{session_id}/external-ai/pending-prompts", dependencies=[Depends(require_admin)])
def admin_external_ai_pending_prompts(
    session_id: str,
    sessions: SessionService = Depends(_sessions),
    prompts: PromptService = Depends(_prompts),
) -> dict:
    try:
        sessions.get_session(session_id)
    except SessionNotFoundError:
        admin_error("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    pending = [
        _external_ai_pending_prompt_payload(item, sessions)
        for item in prompts.list_pending_prompts(session_id=session_id)
        if str(item.payload.get("provider") or "").strip().lower() == "ai"
    ]
    return _ok(
        {
            "schema_version": 1,
            "schema_name": "mrn.admin_external_ai_pending_prompts",
            "visibility": "admin",
            "browser_safe": False,
            "session_id": session_id,
            "pending_prompts": pending,
        }
    )
