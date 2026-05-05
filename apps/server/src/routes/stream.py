from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.visibility import project_stream_message_for_viewer, viewer_from_auth_context
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import build_decision_ack_payload
from apps.server.src.services.session_service import SessionNotFoundError, SessionStateError

router = APIRouter(prefix="/api/v1/sessions", tags=["stream"])


def _filter_stream_message(message: dict[str, Any], auth_ctx: dict[str, Any]) -> dict[str, Any] | None:
    return project_stream_message_for_viewer(message, viewer_from_auth_context(auth_ctx))


def _strip_view_state(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload")
    if isinstance(payload, dict):
        payload.pop("view_state", None)
    return message


async def _project_replay_messages(
    stream_service: Any,
    replay_items: list[Any],
    *,
    viewer: Any,
    auth_ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    visible: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in replay_items:
        raw = item.to_dict()
        filtered = _filter_stream_message(raw, auth_ctx)
        if filtered is not None:
            visible.append((raw, _strip_view_state(filtered)))

    if not visible:
        return []

    latest_raw, _ = visible[-1]
    latest_projected = await stream_service.project_message_for_viewer(latest_raw, viewer)
    projected: list[dict[str, Any]] = []
    for index, (_, filtered) in enumerate(visible):
        if index == len(visible) - 1 and latest_projected is not None:
            projected.append(latest_projected)
        else:
            projected.append(filtered)
    return projected


async def _send_stream_catch_up(
    websocket: WebSocket,
    stream_service: Any,
    *,
    session_id: str,
    last_sent_seq: int,
    viewer: Any,
    auth_ctx: dict[str, Any],
) -> int:
    latest_seq = int(await stream_service.latest_seq(session_id))
    if latest_seq <= last_sent_seq:
        return last_sent_seq

    replay = await stream_service.replay_from(session_id, last_sent_seq)
    if not replay:
        return latest_seq

    for filtered in await _project_replay_messages(
        stream_service,
        replay,
        viewer=viewer,
        auth_ctx=auth_ctx,
    ):
        await websocket.send_json(filtered)

    return latest_seq


def _stream_seq(message: dict[str, Any]) -> int:
    try:
        return int(message.get("seq", 0) or 0)
    except (TypeError, ValueError):
        return 0


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
    from apps.server.src.state import (
        prompt_service,
        runtime_service,
        runtime_settings,
        session_service,
        stream_service,
    )

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
    except SessionStateError as exc:
        reason = str(exc)
        code = "SPECTATOR_NOT_ALLOWED" if reason == "spectator_not_allowed" else "UNAUTHORIZED_SEAT"
        message = (
            "Spectator access is not allowed for this session."
            if reason == "spectator_not_allowed"
            else "Invalid session token."
        )
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "seq": 0,
                "session_id": session_id,
                "server_time_ms": int(time.time() * 1000),
                "payload": build_error_payload(code=code, message=message, retryable=False),
            }
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        runtime_state = runtime_service.runtime_status(session_id)
        if auth_ctx.get("role") == "seat" and runtime_state.get("status") == "recovery_required":
            session = session_service.get_session(session_id)
            runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
            pending_command = runtime_service.pending_resume_command(session_id)
            if pending_command is not None:
                command_seq = int(pending_command.get("seq", 0) or 0)
                await runtime_service.process_command_once(
                    session_id=session_id,
                    command_seq=command_seq,
                    consumer_name="runtime_wakeup",
                    seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
                    policy_mode=runtime_cfg.get("policy_mode"),
                )
                log_event(
                    "runtime_recovery_resumed_pending_command",
                    session_id=session_id,
                    reason=runtime_state.get("reason"),
                    command_seq=command_seq,
                )
            elif runtime_service.has_unprocessed_runtime_commands(session_id):
                log_event(
                    "runtime_recovery_deferred_pending_commands",
                    session_id=session_id,
                    reason=runtime_state.get("reason"),
                )
            else:
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
    viewer = viewer_from_auth_context(auth_ctx, session_id=session_id)
    delivered_seq = 0
    resume_received = False
    delivery_lock = asyncio.Lock()

    async def _heartbeat() -> None:
        nonlocal delivered_seq
        while not stop_event.is_set():
            if resume_received:
                async with delivery_lock:
                    previous_seq = delivered_seq
                    delivered_seq = await _send_stream_catch_up(
                        websocket,
                        stream_service,
                        session_id=session_id,
                        last_sent_seq=delivered_seq,
                        viewer=viewer,
                        auth_ctx=auth_ctx,
                    )
                    latest = delivered_seq
                if delivered_seq > previous_seq:
                    log_event(
                        "stream_catch_up",
                        session_id=session_id,
                        connection_id=conn_id,
                        from_seq=previous_seq,
                        latest_seq=delivered_seq,
                    )
            else:
                latest = await stream_service.latest_seq(session_id)
            pressure = await stream_service.backpressure_stats(session_id)
            runtime_diag = runtime_service.runtime_status(session_id)
            active_module = None
            checkpoint = runtime_diag.get("checkpoint") if isinstance(runtime_diag, dict) else None
            if isinstance(checkpoint, dict):
                frames = checkpoint.get("runtime_frame_stack")
                if isinstance(frames, list):
                    for frame in reversed(frames):
                        if isinstance(frame, dict) and frame.get("active_module_id"):
                            active_module = frame.get("active_module_id")
                            break
            await websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": latest,
                    "session_id": session_id,
                    "server_time_ms": int(time.time() * 1000),
                    "payload": {
                        "interval_ms": heartbeat_interval_ms,
                        "backpressure": pressure,
                        "runner_kind": runtime_diag.get("runner_kind") if isinstance(runtime_diag, dict) else None,
                        "active_module_id": active_module,
                    },
                }
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval_sec)
            except asyncio.TimeoutError:
                pass

    async def _sender() -> None:
        nonlocal delivered_seq
        while not stop_event.is_set():
            try:
                message = await asyncio.wait_for(subscriber_queue.get(), timeout=sender_poll_timeout_sec)
            except asyncio.TimeoutError:
                continue
            seq = _stream_seq(message)
            async with delivery_lock:
                if seq > 0 and seq <= delivered_seq:
                    continue
                filtered = await stream_service.project_message_for_viewer(message, viewer)
                delivered_seq = max(delivered_seq, seq)
                if filtered is not None:
                    await websocket.send_json(filtered)

    heart = asyncio.create_task(_heartbeat())
    sender = asyncio.create_task(_sender())
    try:
        while True:
            message: dict[str, Any] = await websocket.receive_json()
            msg_type = str(message.get("type", "")).strip().lower()
            if msg_type == "resume":
                requested_last_seq = int(message.get("last_seq", 0))
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
                async with delivery_lock:
                    last_seq = max(last_seq, delivered_seq)
                    replay = await stream_service.replay_from(session_id, last_seq)
                    for filtered in await _project_replay_messages(
                        stream_service,
                        replay,
                        viewer=viewer,
                        auth_ctx=auth_ctx,
                    ):
                        await websocket.send_json(filtered)
                    delivered_seq = max(delivered_seq, latest_seq)
                    resume_received = True
                log_event(
                    "stream_resume",
                    session_id=session_id,
                    connection_id=conn_id,
                    replay_count=len(replay),
                    last_seq=requested_last_seq,
                    delivered_seq=delivered_seq,
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
