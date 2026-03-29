from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from apps.server.src.routes.health import router as health_router
from apps.server.src.routes.prompts import router as prompts_router
from apps.server.src.routes.sessions import router as sessions_router
from apps.server.src.routes.stream import router as stream_router

app = FastAPI(title="MRN Online Game Server", version="0.1.0")

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(stream_router)
app.include_router(prompts_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"ok", "data", "error"}.issubset(exc.detail.keys()):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "HTTP_EXCEPTION",
                "message": str(exc.detail),
                "retryable": False,
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "retryable": True,
            },
        },
    )
