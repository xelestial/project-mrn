from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import (
    build_decision_ack_payload,
    build_decision_resolved_payload,
    build_decision_timeout_fallback_payload,
)
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
    from apps.server.src.state import prompt_service, runtime_service, runtime_settings, session_service, stream_service

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
                "payload": build_error_payload(code="SESSION_NOT_FOUND", message="Session not found.", retryable=False),
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
                "payload": build_error_payload(code="UNAUTHORIZED_SEAT", message="Invalid session token.", retryable=False),
            }
        )
        await websocket.close()
        return

    await websocket.accept()
    try:
        runtime_state = runtime_service.runtime_status(session_id)
        if auth_ctx.get("role") == "seat" and runtime_state.get("status") == "recovery_required":
            session = session_service.get_session(session_id)
            runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
            await runtime_service.start_runtime(
                session_id=session_id,
                seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
                policy_mode=runtime_cfg.get("policy_mode"),
            )
            log_event(
                "runtime_recovery_started",
                session_id=session_id,
                reason=runtime_state.get("reason"),
            )
    except Exception as exc:  # pragma: no cover - defensive runtime recovery path
        log_event("runtime_recovery_failed", session_id=session_id, error=str(exc))

    conn_id = f"conn_{uuid.uuid4().hex[:10]}"
    subscriber_queue = await stream_service.subscribe(session_id, conn_id)
    if auth_ctx["role"] == "seat" and auth_ctx["seat"] is not None:
        session_service.mark_connected(session_id, auth_ctx["seat"], True)
    stop_event = asyncio.Event()
    heartbeat_interval_ms = int(runtime_settings.stream_heartbeat_interval_ms)
    sender_poll_timeout_ms = int(runtime_settings.stream_sender_poll_timeout_ms)
    heartbeat_interval_sec = max(0.05, heartbeat_interval_ms / 1000.0)
    sender_poll_timeout_sec = max(0.05, sender_poll_timeout_ms / 1000.0)
    log_event(
        "stream_connected",
        session_id=session_id,
        connection_id=conn_id,
        auth_role=auth_ctx.get("role"),
        seat=auth_ctx.get("seat"),
        player_id=auth_ctx.get("player_id"),
    )

    async def _heartbeat() -> None:
        while not stop_event.is_set():
            latest = await stream_service.latest_seq(session_id)
            pressure = await stream_service.backpressure_stats(session_id)
            timed_out = prompt_service.timeout_pending(session_id=session_id)
            for pending in timed_out:
                public_context = pending.payload.get("public_context", {})
                round_index = public_context.get("round_index")
                turn_index = public_context.get("turn_index")
                fallback_policy = pending.payload.get("fallback_policy", "timeout_fallback")
                fallback_result = await runtime_service.execute_prompt_fallback(
                    session_id=session_id,
                    request_id=pending.request_id,
                    player_id=pending.player_id,
                    fallback_policy=str(fallback_policy),
                    prompt_payload=pending.payload,
                )
                await stream_service.publish(
                    session_id,
                    "decision_ack",
                    build_decision_ack_payload(
                        request_id=pending.request_id,
                        status="stale",
                        player_id=pending.player_id,
                        reason="prompt_timeout",
                        provider="human",
                    ),
                )
                await stream_service.publish(
                    session_id,
                    "event",
                    build_decision_resolved_payload(
                        request_id=pending.request_id,
                        player_id=pending.player_id,
                        resolution="timeout_fallback",
                        choice_id=fallback_result.get("choice_id"),
                        provider="human",
                        round_index=round_index,
                        turn_index=turn_index,
                    ),
                )
                await stream_service.publish(
                    session_id,
                    "event",
                    build_decision_timeout_fallback_payload(
                        request_id=pending.request_id,
                        player_id=pending.player_id,
                        fallback_policy=str(fallback_policy),
                        fallback_execution=fallback_result.get("status"),
                        fallback_choice_id=fallback_result.get("choice_id"),
                        provider="human",
                        round_index=round_index,
                        turn_index=turn_index,
                    ),
                )
                log_event(
                    "decision_timeout_fallback",
                    session_id=session_id,
                    request_id=pending.request_id,
                    player_id=pending.player_id,
                    fallback_policy=fallback_policy,
                    fallback_status=fallback_result.get("status"),
                )
            await websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": latest,
                    "session_id": session_id,
                    "server_time_ms": int(time.time() * 1000),
                    "payload": {"interval_ms": heartbeat_interval_ms, "backpressure": pressure},
                }
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval_sec)
            except asyncio.TimeoutError:
                pass

    async def _sender() -> None:
        while not stop_event.is_set():
            try:
                message = await asyncio.wait_for(subscriber_queue.get(), timeout=sender_poll_timeout_sec)
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
                                **build_error_payload(
                                    code="RESUME_GAP_TOO_OLD",
                                    message="Resume gap too old; sending latest buffered stream.",
                                    retryable=True,
                                ),
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
                log_event(
                    "stream_resume",
                    session_id=session_id,
                    connection_id=conn_id,
                    replay_count=len(replay),
                    last_seq=last_seq,
                )
                continue
            if msg_type == "decision":
                if auth_ctx["role"] != "seat":
                    await stream_service.publish(
                        session_id,
                        "error",
                        build_error_payload(
                            code="UNAUTHORIZED_SEAT",
                            message="Spectator cannot submit decisions.",
                            retryable=False,
                        ),
                    )
                    continue
                if message.get("player_id") != auth_ctx.get("player_id"):
                    await stream_service.publish(
                        session_id,
                        "error",
                        build_error_payload(
                            code="PLAYER_MISMATCH",
                            message="Decision player does not match authenticated seat.",
                            retryable=False,
                        ),
                    )
                    continue
                decision_state = prompt_service.submit_decision(message)
                await stream_service.publish(
                    session_id,
                    "decision_ack",
                    build_decision_ack_payload(
                        request_id=str(message.get("request_id", "")),
                        status=str(decision_state.get("status", "rejected")),
                        player_id=int(message.get("player_id", 0)),
                        reason=decision_state.get("reason"),
                        provider="human",
                    ),
                )
                log_event(
                    "decision_received",
                    session_id=session_id,
                    request_id=message.get("request_id"),
                    player_id=message.get("player_id"),
                    status=decision_state.get("status", "rejected"),
                    reason=decision_state.get("reason"),
                )
                continue
            await stream_service.publish(
                session_id,
                "error",
                build_error_payload(
                    code="UNSUPPORTED_MESSAGE",
                    message=f"Unsupported message type: {msg_type}",
                    retryable=False,
                ),
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
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await heart
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sender
        log_event("stream_disconnected", session_id=session_id, connection_id=conn_id)
