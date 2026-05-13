from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.visibility import viewer_from_auth_context
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import build_decision_ack_payload
from apps.server.src.services.session_service import SessionNotFoundError, SessionStateError

router = APIRouter(prefix="/api/v1/sessions", tags=["stream"])

_DELIVERED_STREAM_SEQ_CACHE_LIMIT = 4096


async def _send_json_or_disconnect(websocket: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await websocket.send_json(payload)
    except RuntimeError as exc:
        if 'Cannot call "send" once a close message has been sent' in str(exc):
            raise WebSocketDisconnect(code=1000) from exc
        raise


async def _receive_json_or_disconnect(websocket: WebSocket) -> dict[str, Any]:
    try:
        message = await websocket.receive_json()
    except RuntimeError as exc:
        text = str(exc)
        if (
            "WebSocket is not connected" in text
            or 'Cannot call "receive" once a disconnect message has been received' in text
        ):
            raise WebSocketDisconnect(code=1000) from exc
        raise
    return dict(message) if isinstance(message, dict) else {}


async def _send_latest_view_commit(
    websocket: WebSocket,
    stream_service: Any,
    *,
    session_id: str,
    last_commit_seq: int,
    viewer: Any,
    connection_id: str | None = None,
    trigger: str = "unspecified",
    force: bool = False,
) -> int:
    started = time.perf_counter()
    latest = await stream_service.latest_view_commit_message_for_viewer(session_id, viewer)
    lookup_ms = int((time.perf_counter() - started) * 1000)
    return await _send_resolved_latest_view_commit(
        websocket,
        latest,
        session_id=session_id,
        last_commit_seq=last_commit_seq,
        viewer=viewer,
        connection_id=connection_id,
        trigger=trigger,
        force=force,
        lookup_ms=lookup_ms,
    )


async def _send_resolved_latest_view_commit(
    websocket: WebSocket,
    latest: dict[str, Any] | None,
    *,
    session_id: str,
    last_commit_seq: int,
    viewer: Any,
    connection_id: str | None = None,
    trigger: str = "unspecified",
    force: bool = False,
    lookup_ms: int = 0,
) -> int:
    if latest is None:
        log_event(
            "stream_latest_view_commit_delivery",
            session_id=session_id,
            connection_id=connection_id,
            trigger=trigger,
            viewer=_viewer_label(viewer),
            action="no_latest",
            last_commit_seq=last_commit_seq,
            lookup_ms=lookup_ms,
            force=force,
        )
        return last_commit_seq
    commit_seq = _commit_seq(latest) or _stream_seq(latest)
    if not force and commit_seq <= last_commit_seq:
        log_event(
            "stream_latest_view_commit_delivery",
            session_id=session_id,
            connection_id=connection_id,
            trigger=trigger,
            viewer=_viewer_label(viewer),
            action="suppressed_stale",
            last_commit_seq=last_commit_seq,
            latest_commit_seq=commit_seq,
            latest_stream_seq=_stream_seq(latest),
            lookup_ms=lookup_ms,
            force=force,
        )
        return last_commit_seq
    send_started = time.perf_counter()
    await _send_json_or_disconnect(websocket, latest)
    send_ms = int((time.perf_counter() - send_started) * 1000)
    log_event(
        "stream_latest_view_commit_delivery",
        session_id=session_id,
        connection_id=connection_id,
        trigger=trigger,
        viewer=_viewer_label(viewer),
        action="sent",
        last_commit_seq=last_commit_seq,
        latest_commit_seq=commit_seq,
        latest_stream_seq=_stream_seq(latest),
        lookup_ms=lookup_ms,
        send_ms=send_ms,
        force=force,
    )
    return max(last_commit_seq, commit_seq)


def _viewer_label(viewer: Any) -> str:
    if getattr(viewer, "is_seat", False):
        player_id = getattr(viewer, "player_id", None)
        return f"player:{player_id}" if player_id is not None else "seat"
    if getattr(viewer, "is_admin", False):
        return "admin"
    if getattr(viewer, "is_backend", False):
        return "backend"
    return str(getattr(viewer, "role", None) or "spectator")


def _stream_seq(message: dict[str, Any]) -> int:
    try:
        return int(message.get("seq", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _commit_seq(message: dict[str, Any]) -> int:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return 0
    try:
        return int(payload.get("commit_seq", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _message_request_id(message: dict[str, Any]) -> str:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("request_id") or "").strip()


def _remember_delivered_stream_seq(delivered_stream_seqs: set[int], seq: int) -> None:
    if seq <= 0:
        return
    delivered_stream_seqs.add(seq)
    overflow = len(delivered_stream_seqs) - _DELIVERED_STREAM_SEQ_CACHE_LIMIT
    if overflow <= 0:
        return
    for stale_seq in sorted(delivered_stream_seqs)[:overflow]:
        delivered_stream_seqs.discard(stale_seq)


def _should_suppress_stale_raw_view_commit(raw_commit_seq: int, last_commit_seq: int) -> bool:
    return raw_commit_seq > 0 and raw_commit_seq <= last_commit_seq


async def _send_pending_prompts_for_viewer(
    *,
    websocket: WebSocket,
    stream_service: Any,
    prompt_service: Any,
    session_id: str,
    viewer: Any,
    delivered_prompt_request_ids: set[str],
    connection_id: str | None = None,
    trigger: str = "unspecified",
) -> int:
    if not getattr(viewer, "is_seat", False):
        return 0
    player_id = getattr(viewer, "player_id", None)
    if player_id is None:
        return 0
    list_pending = getattr(prompt_service, "list_pending_prompts", None)
    if not callable(list_pending):
        return 0

    sent = 0
    pending_prompts = list_pending(session_id=session_id, player_id=int(player_id))
    latest_seq = await stream_service.latest_seq(session_id)
    for pending in pending_prompts:
        payload = dict(getattr(pending, "payload", {}) or {})
        request_id = str(payload.get("request_id") or getattr(pending, "request_id", "") or "").strip()
        if not request_id or request_id in delivered_prompt_request_ids:
            continue
        message = {
            "type": "prompt",
            "seq": latest_seq,
            "session_id": session_id,
            "server_time_ms": int(time.time() * 1000),
            "payload": payload,
        }
        filtered = await stream_service.project_message_for_viewer(message, viewer)
        if filtered is None:
            continue
        await _send_json_or_disconnect(websocket, filtered)
        delivered_prompt_request_ids.add(request_id)
        mark_delivered = getattr(prompt_service, "mark_prompt_delivered", None)
        if callable(mark_delivered):
            mark_delivered(request_id, session_id=session_id, stream_seq=latest_seq)
        sent += 1
        log_event(
            "stream_pending_prompt_delivery",
            session_id=session_id,
            connection_id=connection_id,
            trigger=trigger,
            viewer=_viewer_label(viewer),
            request_id=request_id,
            action="sent",
        )
    if sent == 0:
        log_event(
            "stream_pending_prompt_delivery",
            session_id=session_id,
            connection_id=connection_id,
            trigger=trigger,
            viewer=_viewer_label(viewer),
            action="none",
        )
    return sent


async def _wake_runtime_after_accepted_decision(
    *,
    decision_state: dict[str, Any],
    session_id: str,
    session_service: Any | None = None,
    runtime_service: Any | None = None,
    command_router: Any | None = None,
) -> None:
    del session_service, runtime_service
    router = command_router
    if router is None:
        log_event(
            "runtime_wakeup_after_decision_skipped",
            session_id=session_id,
            reason="missing_command_router",
        )
        return
    result = router.wake_after_accept(
        command_ref=decision_state,
        session_id=session_id,
        trigger="accepted_decision",
    )
    if str(result.get("status") or "") in {"skipped", "deduped"}:
        return
    log_event(
        "runtime_wakeup_after_decision_scheduled",
        session_id=session_id,
        command_seq=result.get("command_seq"),
    )


def _resolve_decision_player_id(session_service: Any, session_id: str, message: dict[str, Any]) -> int | None:
    resolver = getattr(session_service, "resolve_protocol_player_id", None)
    if not callable(resolver):
        player_id = message.get("player_id")
        return player_id if isinstance(player_id, int) and not isinstance(player_id, bool) else None
    return resolver(
        session_id,
        player_id=message.get("player_id"),
        legacy_player_id=message.get("legacy_player_id"),
        seat=message.get("seat"),
        public_player_id=message.get("public_player_id"),
        seat_id=message.get("seat_id"),
        viewer_id=message.get("viewer_id"),
    )


async def _send_direct_decision_ack(
    *,
    websocket: WebSocket,
    stream_service: Any,
    viewer: Any,
    delivery_lock: asyncio.Lock,
    delivered_stream_seqs: set[int],
    session_id: str,
    connection_id: str,
    ack_message: Any,
) -> bool:
    if hasattr(ack_message, "to_dict"):
        message = ack_message.to_dict()
    elif isinstance(ack_message, dict):
        message = dict(ack_message)
    else:
        return False
    if str(message.get("type") or "") != "decision_ack":
        return False

    project_started = time.perf_counter()
    filtered = await stream_service.project_message_for_viewer(message, viewer)
    project_ms = int((time.perf_counter() - project_started) * 1000)
    if filtered is None:
        log_event(
            "decision_ack_direct_send_skipped",
            session_id=session_id,
            connection_id=connection_id,
            reason="not_visible_to_viewer",
            stream_seq=_stream_seq(message),
            project_ms=project_ms,
        )
        return False

    stream_seq = _stream_seq(filtered)
    lock_started = time.perf_counter()
    async with delivery_lock:
        lock_wait_ms = int((time.perf_counter() - lock_started) * 1000)
        if stream_seq > 0 and stream_seq in delivered_stream_seqs:
            log_event(
                "decision_ack_direct_send_skipped",
                session_id=session_id,
                connection_id=connection_id,
                reason="already_delivered",
                stream_seq=stream_seq,
                project_ms=project_ms,
                lock_wait_ms=lock_wait_ms,
            )
            return False
        send_started = time.perf_counter()
        await _send_json_or_disconnect(websocket, filtered)
        _remember_delivered_stream_seq(delivered_stream_seqs, stream_seq)
        log_event(
            "decision_ack_direct_sent",
            session_id=session_id,
            connection_id=connection_id,
            request_id=(filtered.get("payload") or {}).get("request_id") if isinstance(filtered.get("payload"), dict) else None,
            stream_seq=stream_seq,
            project_ms=project_ms,
            lock_wait_ms=lock_wait_ms,
            send_ms=int((time.perf_counter() - send_started) * 1000),
        )
        return True


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
        command_recovery_service,
        command_router,
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
        runtime_status = str(runtime_state.get("status") or "")
        if auth_ctx.get("role") == "seat" and runtime_status in {"recovery_required", "waiting_input"}:
            session = session_service.get_session(session_id)
            runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
            pending_command = command_recovery_service.pending_resume_command(session_id)
            if pending_command is not None:
                command_seq = int(pending_command.get("seq", 0) or 0)
                command_router.wake_command(
                    command_ref=pending_command,
                    session_id=session_id,
                    trigger="stream_connect",
                )
                log_event(
                    "runtime_recovery_resumed_pending_command",
                    session_id=session_id,
                    reason=runtime_state.get("reason"),
                    command_seq=command_seq,
                    status=runtime_status,
                )
            elif runtime_status == "recovery_required" and command_recovery_service.has_unprocessed_runtime_commands(session_id):
                log_event(
                    "runtime_recovery_deferred_pending_commands",
                    session_id=session_id,
                    reason=runtime_state.get("reason"),
                )
            elif runtime_status == "recovery_required":
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
    viewer = viewer_from_auth_context(auth_ctx, session_id=session_id)
    subscriber_queue = await stream_service.subscribe(session_id, conn_id, viewer=viewer)
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
    delivered_seq = 0
    delivered_stream_seqs: set[int] = set()
    delivered_prompt_request_ids: set[str] = set()
    last_commit_seq = 0
    delivery_lock = asyncio.Lock()

    async def _heartbeat() -> None:
        nonlocal last_commit_seq
        try:
            while not stop_event.is_set():
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
                heartbeat_lock_started = time.perf_counter()
                async with delivery_lock:
                    heartbeat_lock_wait_ms = int((time.perf_counter() - heartbeat_lock_started) * 1000)
                    last_commit_seq = await _send_latest_view_commit(
                        websocket=websocket,
                        stream_service=stream_service,
                        viewer=viewer,
                        session_id=session_id,
                        last_commit_seq=last_commit_seq,
                        trigger="heartbeat",
                        connection_id=conn_id,
                    )
                    heartbeat_send_started = time.perf_counter()
                    await _send_json_or_disconnect(
                        websocket,
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
                    heartbeat_send_ms = int((time.perf_counter() - heartbeat_send_started) * 1000)
                    if heartbeat_lock_wait_ms >= 1000 or heartbeat_send_ms >= 1000:
                        log_event(
                            "stream_heartbeat_slow",
                            session_id=session_id,
                            connection_id=conn_id,
                            viewer=_viewer_label(viewer),
                            lock_wait_ms=heartbeat_lock_wait_ms,
                            send_ms=heartbeat_send_ms,
                        )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval_sec)
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            stop_event.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_event("stream_heartbeat_failed", session_id=session_id, connection_id=conn_id, error=str(exc))
            stop_event.set()

    async def _sender() -> None:
        nonlocal delivered_seq, last_commit_seq
        try:
            while not stop_event.is_set():
                try:
                    message = await asyncio.wait_for(subscriber_queue.get(), timeout=sender_poll_timeout_sec)
                except asyncio.TimeoutError:
                    continue
                seq = _stream_seq(message)
                is_view_commit = str(message.get("type") or "") == "view_commit"
                is_prompt = str(message.get("type") or "") == "prompt"
                raw_commit_seq = _commit_seq(message) if is_view_commit else 0
                if is_prompt and _message_request_id(message) in delivered_prompt_request_ids:
                    log_event(
                        "stream_queue_prompt_delivery",
                        session_id=session_id,
                        connection_id=conn_id,
                        viewer=_viewer_label(viewer),
                        action="suppressed_already_repaired",
                        raw_stream_seq=seq,
                        request_id=_message_request_id(message),
                    )
                    continue
                if is_view_commit:
                    log_event(
                        "stream_sender_view_commit_stage",
                        session_id=session_id,
                        connection_id=conn_id,
                        viewer=_viewer_label(viewer),
                        action="dequeued",
                        raw_stream_seq=seq,
                        raw_commit_seq=raw_commit_seq,
                        queue_depth_after=subscriber_queue.qsize(),
                        last_commit_seq=last_commit_seq,
                    )
                if seq > 0 and seq in delivered_stream_seqs:
                    continue
                if is_view_commit and _should_suppress_stale_raw_view_commit(raw_commit_seq, last_commit_seq):
                    log_event(
                        "stream_queue_view_commit_delivery",
                        session_id=session_id,
                        connection_id=conn_id,
                        viewer=_viewer_label(viewer),
                        action="suppressed_stale_raw_before_project",
                        raw_stream_seq=seq,
                        raw_commit_seq=raw_commit_seq,
                        last_commit_seq=last_commit_seq,
                    )
                    continue
                project_started = time.perf_counter()
                if getattr(stream_service, "outbox_mode", "dual") == "read":
                    filtered = message
                else:
                    filtered = await stream_service.project_message_for_viewer(message, viewer)
                project_ms = int((time.perf_counter() - project_started) * 1000)
                if is_view_commit:
                    log_event(
                        "stream_sender_view_commit_stage",
                        session_id=session_id,
                        connection_id=conn_id,
                        viewer=_viewer_label(viewer),
                        action="projected",
                        raw_stream_seq=seq,
                        raw_commit_seq=raw_commit_seq,
                        filtered_commit_seq=_commit_seq(filtered) if isinstance(filtered, dict) else 0,
                        project_ms=project_ms,
                        projected=filtered is not None,
                    )
                lock_started = time.perf_counter()
                async with delivery_lock:
                    lock_wait_ms = int((time.perf_counter() - lock_started) * 1000)
                    if is_view_commit:
                        log_event(
                            "stream_sender_view_commit_stage",
                            session_id=session_id,
                            connection_id=conn_id,
                            viewer=_viewer_label(viewer),
                            action="lock_acquired",
                            raw_stream_seq=seq,
                            raw_commit_seq=raw_commit_seq,
                            lock_wait_ms=lock_wait_ms,
                            last_commit_seq=last_commit_seq,
                        )
                    if seq > 0 and seq in delivered_stream_seqs:
                        continue
                    if is_view_commit and _should_suppress_stale_raw_view_commit(raw_commit_seq, last_commit_seq):
                        log_event(
                            "stream_queue_view_commit_delivery",
                            session_id=session_id,
                            connection_id=conn_id,
                            viewer=_viewer_label(viewer),
                            action="suppressed_stale_raw",
                            raw_stream_seq=seq,
                            raw_commit_seq=raw_commit_seq,
                            last_commit_seq=last_commit_seq,
                        )
                        continue
                    delivered_seq = max(delivered_seq, seq)
                    if filtered is not None:
                        if filtered.get("type") == "view_commit":
                            commit_seq = _commit_seq(filtered)
                            if commit_seq <= last_commit_seq:
                                log_event(
                                    "stream_queue_view_commit_delivery",
                                    session_id=session_id,
                                    connection_id=conn_id,
                                    viewer=_viewer_label(viewer),
                                    action="suppressed_stale",
                                    raw_stream_seq=seq,
                                    last_commit_seq=last_commit_seq,
                                    filtered_commit_seq=commit_seq,
                                )
                                continue
                            last_commit_seq = commit_seq
                            log_event(
                                "stream_sender_view_commit_stage",
                                session_id=session_id,
                                connection_id=conn_id,
                                viewer=_viewer_label(viewer),
                                action="send_start",
                                raw_stream_seq=seq,
                                filtered_commit_seq=commit_seq,
                                last_commit_seq=last_commit_seq,
                            )
                        send_started = time.perf_counter()
                        await _send_json_or_disconnect(websocket, filtered)
                        send_ms = int((time.perf_counter() - send_started) * 1000)
                        if filtered.get("type") == "view_commit":
                            log_event(
                                "stream_queue_view_commit_delivery",
                                session_id=session_id,
                                connection_id=conn_id,
                                viewer=_viewer_label(viewer),
                                action="sent",
                                raw_stream_seq=seq,
                                last_commit_seq=last_commit_seq,
                                filtered_commit_seq=_commit_seq(filtered),
                                send_ms=send_ms,
                            )
                        if filtered.get("type") == "prompt":
                            request_id = _message_request_id(filtered)
                            if request_id:
                                delivered_prompt_request_ids.add(request_id)
                        if filtered.get("type") != "view_commit":
                            _remember_delivered_stream_seq(delivered_stream_seqs, seq)
                    elif str(message.get("type") or "") == "view_commit":
                        log_event(
                            "stream_queue_view_commit_delivery",
                            session_id=session_id,
                            connection_id=conn_id,
                            viewer=_viewer_label(viewer),
                            action="projected_none",
                            raw_stream_seq=seq,
                            last_commit_seq=last_commit_seq,
                        )
        except WebSocketDisconnect:
            stop_event.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_event("stream_sender_failed", session_id=session_id, connection_id=conn_id, error=str(exc))
            stop_event.set()

    heart: asyncio.Task | None = None
    sender: asyncio.Task | None = None
    try:
        latest_commit = await stream_service.latest_view_commit_message_for_viewer(session_id, viewer)
        if latest_commit is not None:
            last_commit_seq = _commit_seq(latest_commit)
            delivered_seq = _stream_seq(latest_commit)
            await _send_json_or_disconnect(websocket, latest_commit)
            log_event(
                "stream_latest_view_commit_delivery",
                session_id=session_id,
                connection_id=conn_id,
                trigger="connect",
                viewer=_viewer_label(viewer),
                action="sent",
                last_commit_seq=0,
                latest_commit_seq=last_commit_seq,
                latest_stream_seq=delivered_seq,
                force=True,
            )
        else:
            log_event(
                "stream_latest_view_commit_delivery",
                session_id=session_id,
                connection_id=conn_id,
                trigger="connect",
                viewer=_viewer_label(viewer),
                action="no_latest",
                last_commit_seq=last_commit_seq,
                force=True,
            )
        await _send_pending_prompts_for_viewer(
            websocket=websocket,
            stream_service=stream_service,
            prompt_service=prompt_service,
            session_id=session_id,
            viewer=viewer,
            delivered_prompt_request_ids=delivered_prompt_request_ids,
            connection_id=conn_id,
            trigger="connect",
        )

        heart = asyncio.create_task(_heartbeat())
        sender = asyncio.create_task(_sender())
        while True:
            message = await _receive_json_or_disconnect(websocket)
            msg_type = str(message.get("type", "")).strip().lower()
            if msg_type == "resume":
                requested_last_commit_seq = int(message.get("last_commit_seq", 0) or 0)
                async with delivery_lock:
                    previous_commit_seq = last_commit_seq
                    effective_last_commit_seq = max(requested_last_commit_seq, last_commit_seq)
                    last_commit_seq = await _send_latest_view_commit(
                        websocket,
                        stream_service,
                        session_id=session_id,
                        last_commit_seq=effective_last_commit_seq,
                        viewer=viewer,
                        connection_id=conn_id,
                        trigger="resume",
                        force=True,
                    )
                    await _send_pending_prompts_for_viewer(
                        websocket=websocket,
                        stream_service=stream_service,
                        prompt_service=prompt_service,
                        session_id=session_id,
                        viewer=viewer,
                        delivered_prompt_request_ids=delivered_prompt_request_ids,
                        connection_id=conn_id,
                        trigger="resume",
                    )
                log_event(
                    "stream_resume_snapshot",
                    session_id=session_id,
                    connection_id=conn_id,
                    requested_last_commit_seq=requested_last_commit_seq,
                    previous_commit_seq=previous_commit_seq,
                    delivered_commit_seq=last_commit_seq,
                    delivered_seq=delivered_seq,
                )
                continue
            if msg_type == "decision":
                route_started_ms = time.perf_counter()
                submit_decision_ms = 0
                ack_publish_ms = 0
                wake_runtime_ms = 0
                decision_state: dict[str, Any] | None = None
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
                resolved_player_id = _resolve_decision_player_id(session_service, session_id, message)
                if resolved_player_id != auth_ctx.get("player_id"):
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
                message["player_id"] = resolved_player_id
                message["session_id"] = session_id
                phase_started_ms = time.perf_counter()
                decision_state = prompt_service.submit_decision(message)
                submit_decision_ms = int((time.perf_counter() - phase_started_ms) * 1000)
                phase_started_ms = time.perf_counter()
                ack_message = await stream_service.publish_decision_ack(
                    session_id,
                    build_decision_ack_payload(
                        request_id=str(message.get("request_id", "")),
                        status=str(decision_state.get("status", "rejected")),
                        player_id=int(message.get("player_id", 0)),
                        reason=decision_state.get("reason"),
                        provider="human",
                    ),
                )
                ack_publish_ms = int((time.perf_counter() - phase_started_ms) * 1000)
                await _send_direct_decision_ack(
                    websocket=websocket,
                    stream_service=stream_service,
                    viewer=viewer,
                    delivery_lock=delivery_lock,
                    delivered_stream_seqs=delivered_stream_seqs,
                    session_id=session_id,
                    connection_id=conn_id,
                    ack_message=ack_message,
                )
                log_event(
                    "decision_received",
                    session_id=session_id,
                    request_id=message.get("request_id"),
                    player_id=message.get("player_id"),
                    status=decision_state.get("status", "rejected"),
                    reason=decision_state.get("reason"),
                    command_seq=decision_state.get("command_seq"),
                )
                phase_started_ms = time.perf_counter()
                await _wake_runtime_after_accepted_decision(
                    decision_state=decision_state,
                    session_id=session_id,
                    command_router=command_router,
                )
                wake_runtime_ms = int((time.perf_counter() - phase_started_ms) * 1000)
                log_event(
                    "decision_route_timing",
                    session_id=session_id,
                    request_id=message.get("request_id"),
                    player_id=message.get("player_id"),
                    status=decision_state.get("status", "rejected"),
                    reason=decision_state.get("reason"),
                    command_seq=decision_state.get("command_seq"),
                    total_ms=int((time.perf_counter() - route_started_ms) * 1000),
                    submit_decision_ms=submit_decision_ms,
                    ack_publish_ms=ack_publish_ms,
                    wake_runtime_ms=wake_runtime_ms,
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
        if heart is not None:
            heart.cancel()
        if sender is not None:
            sender.cancel()
        with contextlib.suppress(Exception):
            await stream_service.unsubscribe(session_id, conn_id)
        if auth_ctx["role"] == "seat" and auth_ctx["seat"] is not None:
            with contextlib.suppress(Exception):
                session_service.mark_connected(session_id, auth_ctx["seat"], False)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            if heart is not None:
                await heart
        with contextlib.suppress(asyncio.CancelledError, Exception):
            if sender is not None:
                await sender
        log_event("stream_disconnected", session_id=session_id, connection_id=conn_id)
