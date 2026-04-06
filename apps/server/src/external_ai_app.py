from __future__ import annotations

import os
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.services.external_ai_worker_service import ExternalAiWorkerService


class ExternalAiDecisionRequest(BaseModel):
    request_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    seat: int = Field(..., ge=1)
    player_id: int = Field(..., ge=1)
    decision_name: str = Field(..., min_length=1)
    request_type: str = Field(..., min_length=1)
    fallback_policy: str = Field(..., min_length=1)
    public_context: dict = Field(default_factory=dict)
    legal_choices: list[dict] = Field(default_factory=list)
    transport: str = Field(..., min_length=1)
    worker_contract_version: str = Field(default="v1", min_length=1)
    required_capabilities: list[str] = Field(default_factory=list)


class ExternalAiDecisionResponse(BaseModel):
    choice_id: str = Field(..., min_length=1)
    choice_payload: dict | None = None
    worker_id: str = Field(..., min_length=1)
    policy_mode: str = Field(..., min_length=1)
    policy_class: str = Field(..., min_length=1)
    worker_contract_version: str = Field(default="v1", min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    supported_request_types: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    ready: bool | None = None


@lru_cache(maxsize=1)
def _service() -> ExternalAiWorkerService:
    worker_id = os.getenv("MRN_EXTERNAL_AI_WORKER_ID", "external-ai-worker")
    policy_mode = os.getenv("MRN_EXTERNAL_AI_POLICY_MODE", "heuristic_v3_gpt")
    return ExternalAiWorkerService(worker_id=worker_id, policy_mode=policy_mode)


def create_app(service: ExternalAiWorkerService | None = None) -> FastAPI:
    resolved_service = service or _service()
    app = FastAPI(title="MRN External AI Worker", version="0.1.0")
    expected_auth_header = os.getenv("MRN_EXTERNAL_AI_AUTH_HEADER_NAME", "Authorization").strip() or "Authorization"
    expected_auth_scheme = os.getenv("MRN_EXTERNAL_AI_AUTH_SCHEME", "Bearer").strip()
    expected_auth_token = os.getenv("MRN_EXTERNAL_AI_AUTH_TOKEN", "").strip()

    def _authorize(request: Request) -> None:
        if not expected_auth_token:
            return
        provided = (request.headers.get(expected_auth_header) or "").strip()
        expected = f"{expected_auth_scheme} {expected_auth_token}".strip() if expected_auth_scheme else expected_auth_token
        if provided != expected:
            raise HTTPException(
                status_code=401,
                detail={
                    "ok": False,
                    "data": None,
                    "error": build_error_payload(
                        code="EXTERNAL_AI_UNAUTHORIZED",
                        message="missing_or_invalid_worker_auth",
                        retryable=False,
                    ),
                },
            )

    @app.get("/health")
    def health(request: Request) -> dict[str, object]:
        _authorize(request)
        metadata = resolved_service.describe()
        return {
            "ok": True,
            **metadata,
        }

    @app.post("/decide", response_model=ExternalAiDecisionResponse)
    def decide(
        payload: ExternalAiDecisionRequest,
        request: Request,
    ) -> dict[str, object]:
        _authorize(request)
        try:
            return resolved_service.decide(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "data": None,
                    "error": build_error_payload(
                        code="EXTERNAL_AI_INVALID_REQUEST",
                        message=str(exc),
                        retryable=False,
                    ),
                },
            ) from exc

    return app


app = create_app()
