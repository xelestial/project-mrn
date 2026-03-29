from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.server.src.services.session_service import SessionNotFoundError, SessionStateError

router = APIRouter(prefix="/api/v1/sessions", tags=["stream"])


@router.get("/{session_id}/stream-capability")
def stream_capability(session_id: str) -> dict:
    """Temporary probe endpoint for B1 baseline.

    Real websocket endpoint is scheduled in B2:
    WS /api/v1/sessions/{session_id}/stream
    """
    return {
        "ok": True,
        "data": {
            "session_id": session_id,
            "websocket_ready": True,
            "planned_endpoint": f"/api/v1/sessions/{session_id}/stream",
        },
        "error": None,
    }


@router.websocket("/{session_id}/stream")
async def stream_ws(websocket: WebSocket, session_id: str) -> None:
    from apps.server.src.state import prompt_service, session_service, stream_service

    token = websocket.query_params.get("token")
    try:
        session_service.get_session(session_id)
        auth_ctx = session_service.verify_session_token(session_id, token)
    except SessionNotFoundError:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "seq": 0,
                "session_id": session_id,
                "server_time_ms": int(time.time() * 1000),
                "payload": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "Session not found.",
                    "retryable": False,
                },
            }
        )
        await websocket.close()
        return
    except SessionStateError:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "seq": 0,
                "session_id": session_id,
                "server_time_ms": int(time.time() * 1000),
                "payload": {
                    "code": "UNAUTHORIZED_SEAT",
                    "message": "Invalid session token.",
                    "retryable": False,
                },
            }
        )
        await websocket.close()
        return

    await websocket.accept()
    conn_id = f"conn_{uuid.uuid4().hex[:10]}"
    subscriber_queue = await stream_service.subscribe(session_id, conn_id)
    if auth_ctx["role"] == "seat" and auth_ctx["seat"] is not None:
        session_service.mark_connected(session_id, auth_ctx["seat"], True)
    stop_event = asyncio.Event()

    async def _heartbeat() -> None:
        while not stop_event.is_set():
            latest = await stream_service.latest_seq(session_id)
            timed_out = prompt_service.timeout_pending(session_id=session_id)
            for pending in timed_out:
                public_context = pending.payload.get("public_context", {})
                round_index = public_context.get("round_index")
                turn_index = public_context.get("turn_index")
                fallback_policy = pending.payload.get("fallback_policy", "timeout_fallback")
                await stream_service.publish(
                    session_id,
                    "decision_ack",
                    {
                        "request_id": pending.request_id,
                        "status": "stale",
                        "player_id": pending.player_id,
                        "reason": "prompt_timeout",
                    },
                )
                await stream_service.publish(
                    session_id,
                    "event",
                    {
                        "event_type": "decision_timeout_fallback",
                        "request_id": pending.request_id,
                        "player_id": pending.player_id,
                        "fallback_policy": fallback_policy,
                        "round_index": round_index,
                        "turn_index": turn_index,
                    },
                )
            await websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": latest,
                    "session_id": session_id,
                    "server_time_ms": int(time.time() * 1000),
                    "payload": {"interval_ms": 5000},
                }
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

    async def _sender() -> None:
        while not stop_event.is_set():
            try:
                message = await asyncio.wait_for(subscriber_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await websocket.send_json(message)

    heart = asyncio.create_task(_heartbeat())
    sender = asyncio.create_task(_sender())
    try:
        while True:
            message: dict[str, Any] = await websocket.receive_json()
            msg_type = str(message.get("type", "")).strip().lower()
            if msg_type == "resume":
                last_seq = int(message.get("last_seq", 0))
                oldest_seq, latest_seq = await stream_service.replay_window(session_id)
                if oldest_seq > 0 and last_seq < (oldest_seq - 1):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "seq": latest_seq,
                            "session_id": session_id,
                            "server_time_ms": int(time.time() * 1000),
                            "payload": {
                                "code": "RESUME_GAP_TOO_OLD",
                                "message": "Resume gap too old; sending latest buffered stream.",
                                "retryable": True,
                                "last_seq": last_seq,
                                "oldest_seq": oldest_seq,
                                "latest_seq": latest_seq,
                            },
                        }
                    )
                    last_seq = oldest_seq - 1
                replay = await stream_service.replay_from(session_id, last_seq)
                for item in replay:
                    await websocket.send_json(item.to_dict())
                continue
            if msg_type == "decision":
                if auth_ctx["role"] != "seat":
                    await stream_service.publish(
                        session_id,
                        "error",
                        {
                            "code": "UNAUTHORIZED_SEAT",
                            "message": "Spectator cannot submit decisions.",
                            "retryable": False,
                        },
                    )
                    continue
                if message.get("player_id") != auth_ctx.get("player_id"):
                    await stream_service.publish(
                        session_id,
                        "error",
                        {
                            "code": "PLAYER_MISMATCH",
                            "message": "Decision player does not match authenticated seat.",
                            "retryable": False,
                        },
                    )
                    continue
                decision_state = prompt_service.submit_decision(message)
                await stream_service.publish(
                    session_id,
                    "decision_ack",
                    {
                        "request_id": message.get("request_id"),
                        "status": decision_state.get("status", "rejected"),
                        "player_id": message.get("player_id"),
                        "reason": decision_state.get("reason"),
                    },
                )
                continue
            await stream_service.publish(
                session_id,
                "error",
                {
                    "code": "UNSUPPORTED_MESSAGE",
                    "message": f"Unsupported message type: {msg_type}",
                    "retryable": False,
                },
            )
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        heart.cancel()
        sender.cancel()
        with contextlib.suppress(Exception):
            await stream_service.unsubscribe(session_id, conn_id)
        if auth_ctx["role"] == "seat" and auth_ctx["seat"] is not None:
            with contextlib.suppress(Exception):
                session_service.mark_connected(session_id, auth_ctx["seat"], False)
        with contextlib.suppress(Exception):
            await heart
        with contextlib.suppress(Exception):
            await sender
