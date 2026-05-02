from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.infra.structured_log import log_event
from apps.server.src.routes.admin import router as admin_router
from apps.server.src.routes.debug import router as debug_router
from apps.server.src.routes.health import router as health_router
from apps.server.src.routes.prompts import router as prompts_router
from apps.server.src.routes.rooms import router as rooms_router
from apps.server.src.routes.sessions import router as sessions_router
from apps.server.src.routes.stream import router as stream_router

app = FastAPI(title="MRN Online Game Server", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(debug_router)
app.include_router(sessions_router)
app.include_router(rooms_router)
app.include_router(stream_router)
app.include_router(prompts_router)


async def _request_context(request: Request) -> dict[str, object]:
    session_id = request.path_params.get("session_id")
    request_id = request.query_params.get("request_id")
    player_id: int | None = None
    seq: int | None = None

    player_q = request.query_params.get("player_id")
    if player_q and player_q.isdigit():
        player_id = int(player_q)
    seq_q = request.query_params.get("seq")
    if seq_q and seq_q.isdigit():
        seq = int(seq_q)

    try:
        body = await request.body()
        if body:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict):
                if not request_id and isinstance(payload.get("request_id"), str):
                    request_id = payload["request_id"]
                if player_id is None and isinstance(payload.get("player_id"), int):
                    player_id = payload["player_id"]
                if seq is None and isinstance(payload.get("seq"), int):
                    seq = payload["seq"]
    except Exception:
        # context extraction must never block error handling
        pass

    return {
        "session_id": session_id if isinstance(session_id, str) else None,
        "request_id": request_id,
        "player_id": player_id,
        "seq": seq,
        "path": request.url.path,
        "method": request.method,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    context = await _request_context(request)
    if isinstance(exc.detail, dict) and {"ok", "data", "error"}.issubset(exc.detail.keys()):
        err = exc.detail.get("error") if isinstance(exc.detail.get("error"), dict) else {}
        log_event(
            "http_exception",
            status_code=exc.status_code,
            code=err.get("code"),
            message=err.get("message"),
            **context,
        )
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    err = build_error_payload(
        code="HTTP_EXCEPTION",
        message=str(exc.detail),
        retryable=False,
    )
    log_event(
        "http_exception",
        status_code=exc.status_code,
        code=err["code"],
        message=err["message"],
        **context,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "data": None,
            "error": err,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    context = await _request_context(request)
    err = build_error_payload(
        code="INTERNAL_SERVER_ERROR",
        message=str(exc),
        retryable=True,
    )
    log_event(
        "unhandled_exception",
        code=err["code"],
        message=err["message"],
        **context,
    )
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "data": None,
            "error": err,
        },
    )
