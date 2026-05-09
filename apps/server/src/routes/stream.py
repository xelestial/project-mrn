from __future__ import annotations

import asyncio
import contextlib
import time
import traceback
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.server.src.core.error_payload import build_error_payload
from apps.server.src.domain.visibility import viewer_from_auth_context
from apps.server.src.infra.structured_log import log_event
from apps.server.src.services.decision_gateway import build_decision_ack_payload
from apps.server.src.services.session_service import SessionNotFoundError, SessionStateError

router = APIRouter(prefix="/api/v1/sessions", tags=["stream"])

_RUNTIME_WAKEUP_TASKS: dict[tuple[str, int], asyncio.Task[None]] = {}
_RUNTIME_WAKEUP_DEFERRED_RETRY_DELAY_SEC = 0.05
_RUNTIME_WAKEUP_DEFERRED_RETRY_DEADLINE_SEC = 30.0


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
    force: bool = False,
) -> int:
    latest = await stream_service.latest_view_commit_message_for_viewer(session_id, viewer)
    if latest is None:
        return last_commit_seq
    commit_seq = _commit_seq(latest) or _stream_seq(latest)
    if not force and commit_seq <= last_commit_seq:
        return last_commit_seq
    await _send_json_or_disconnect(websocket, latest)
    return max(last_commit_seq, commit_seq)


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


def _decision_view_commit_rejection_reason(message: dict[str, Any], latest_commit: dict[str, Any] | None) -> str | None:
    seen_commit_seq = _optional_int(message.get("view_commit_seq_seen"))
    if seen_commit_seq is None:
        return "missing_view_commit_seq_seen"
    if seen_commit_seq < 0:
        return "invalid_view_commit_seq_seen"
    latest_commit_seq = _commit_seq(latest_commit) if isinstance(latest_commit, dict) else 0
    if latest_commit_seq and seen_commit_seq > latest_commit_seq:
        return "future_view_commit_seq"
    active_prompt = _active_prompt_from_commit(latest_commit)
    if active_prompt is None:
        return None
    active_request_id = str(active_prompt.get("request_id") or "").strip()
    message_request_id = str(message.get("request_id") or "").strip()
    if active_request_id and message_request_id != active_request_id:
        return "stale_prompt_request"
    active_player_id = _optional_int(active_prompt.get("player_id"))
    message_player_id = _optional_int(message.get("player_id"))
    if active_player_id is not None and message_player_id is not None and active_player_id != message_player_id:
        return "prompt_player_mismatch"
    active_prompt_instance_id = _optional_int(active_prompt.get("prompt_instance_id"))
    message_prompt_instance_id = _optional_int(message.get("prompt_instance_id"))
    if active_prompt_instance_id is not None:
        if message_prompt_instance_id is None:
            return "missing_prompt_instance_id"
        if message_prompt_instance_id != active_prompt_instance_id:
            return "stale_prompt_instance"
    active_resume_token = str(active_prompt.get("resume_token") or "").strip()
    message_resume_token = str(message.get("resume_token") or "").strip()
    if active_resume_token and message_resume_token != active_resume_token:
        return "stale_prompt_resume_token"
    return None


def _active_prompt_from_commit(latest_commit: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(latest_commit, dict):
        return None
    payload = latest_commit.get("payload")
    if not isinstance(payload, dict):
        return None
    view_state = payload.get("view_state")
    if not isinstance(view_state, dict):
        return None
    prompt = view_state.get("prompt")
    if not isinstance(prompt, dict):
        return None
    active_prompt = prompt.get("active")
    return active_prompt if isinstance(active_prompt, dict) and active_prompt else None


def _prompt_payload_from_active_view_prompt(active_prompt: dict[str, Any], session_id: str) -> dict[str, Any]:
    payload = dict(active_prompt)
    payload["session_id"] = session_id
    if "legal_choices" not in payload and isinstance(payload.get("choices"), list):
        payload["legal_choices"] = [dict(choice) for choice in payload.get("choices") or [] if isinstance(choice, dict)]
    payload.pop("choices", None)
    return payload


def _repair_missing_pending_prompt_from_view_commit(
    *,
    prompt_service: Any,
    session_id: str,
    message: dict[str, Any],
    latest_commit: dict[str, Any] | None,
) -> bool:
    active_prompt = _active_prompt_from_commit(latest_commit)
    if active_prompt is None:
        return False
    if str(active_prompt.get("request_id") or "").strip() != str(message.get("request_id") or "").strip():
        return False
    active_player_id = _optional_int(active_prompt.get("player_id"))
    message_player_id = _optional_int(message.get("player_id"))
    if active_player_id is None or message_player_id is None or active_player_id != message_player_id:
        return False
    active_prompt_instance_id = _optional_int(active_prompt.get("prompt_instance_id"))
    message_prompt_instance_id = _optional_int(message.get("prompt_instance_id"))
    if active_prompt_instance_id is not None and message_prompt_instance_id is not None and active_prompt_instance_id != message_prompt_instance_id:
        return False
    active_resume_token = str(active_prompt.get("resume_token") or "").strip()
    message_resume_token = str(message.get("resume_token") or "").strip()
    if active_resume_token and message_resume_token and active_resume_token != message_resume_token:
        return False
    try:
        prompt_service.create_prompt(
            session_id=session_id,
            prompt=_prompt_payload_from_active_view_prompt(active_prompt, session_id),
        )
    except ValueError as exc:
        if str(exc) not in {"duplicate_pending_request_id", "duplicate_recent_request_id"}:
            log_event(
                "decision_pending_prompt_repair_failed",
                session_id=session_id,
                request_id=message.get("request_id"),
                player_id=message.get("player_id"),
                error=str(exc),
            )
            return False
    except Exception as exc:
        log_event(
            "decision_pending_prompt_repair_failed",
            session_id=session_id,
            request_id=message.get("request_id"),
            player_id=message.get("player_id"),
            error=repr(exc),
        )
        return False
    log_event(
        "decision_pending_prompt_repaired",
        session_id=session_id,
        request_id=message.get("request_id"),
        player_id=message.get("player_id"),
    )
    return True


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _process_pending_runtime_command(
    *,
    session_id: str,
    command_seq: int,
    session_service: Any,
    runtime_service: Any,
    trigger: str,
) -> dict:
    if command_seq <= 0:
        return {"status": "skipped", "reason": "invalid_command_seq"}
    session = session_service.get_session(session_id)
    runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
    result = await runtime_service.process_command_once(
        session_id=session_id,
        command_seq=int(command_seq),
        consumer_name="runtime_wakeup",
        seed=int(runtime_cfg.get("seed", session.config.get("seed", 42))),
        policy_mode=runtime_cfg.get("policy_mode"),
    )
    result_status = str((result or {}).get("status") or "").strip()
    event_name = "runtime_wakeup_deferred_command" if result_status == "running_elsewhere" else "runtime_wakeup_processed_command"
    log_event(
        event_name,
        session_id=session_id,
        command_seq=int(command_seq),
        trigger=trigger,
        result_status=result_status,
        reason=(result or {}).get("reason"),
    )
    return result or {}


async def _wake_runtime_after_accepted_decision(
    *,
    decision_state: dict[str, Any],
    session_id: str,
    session_service: Any,
    runtime_service: Any,
) -> None:
    if str(decision_state.get("status") or "") != "accepted":
        return
    command_seq = _optional_int(decision_state.get("command_seq"))
    if command_seq is None or command_seq <= 0:
        return
    decision_session_id = str(decision_state.get("session_id") or session_id).strip()
    if decision_session_id != session_id:
        log_event(
            "runtime_wakeup_after_decision_skipped",
            session_id=session_id,
            decision_session_id=decision_session_id,
            command_seq=command_seq,
            reason="session_mismatch",
        )
        return
    task_key = (session_id, int(command_seq))
    existing_task = _RUNTIME_WAKEUP_TASKS.get(task_key)
    if existing_task is not None and not existing_task.done():
        log_event(
            "runtime_wakeup_after_decision_deduped",
            session_id=session_id,
            command_seq=command_seq,
            reason="wakeup_already_scheduled",
        )
        return

    async def _run_wakeup() -> None:
        started = time.perf_counter()
        try:
            while True:
                result = await _process_pending_runtime_command(
                    session_id=session_id,
                    command_seq=command_seq,
                    session_service=session_service,
                    runtime_service=runtime_service,
                    trigger="accepted_decision",
                )
                result_status = str((result or {}).get("status") or "").strip()
                if result_status != "running_elsewhere":
                    break
                elapsed = time.perf_counter() - started
                if elapsed >= _RUNTIME_WAKEUP_DEFERRED_RETRY_DEADLINE_SEC:
                    log_event(
                        "runtime_wakeup_deferred_retry_exhausted",
                        session_id=session_id,
                        command_seq=command_seq,
                        duration_ms=int(elapsed * 1000),
                    )
                    break
                await asyncio.sleep(_RUNTIME_WAKEUP_DEFERRED_RETRY_DELAY_SEC)
        except Exception as exc:  # pragma: no cover - defensive wakeup path
            log_event(
                "runtime_wakeup_after_decision_failed",
                session_id=session_id,
                command_seq=command_seq,
                error_type=exc.__class__.__name__,
                error=repr(exc),
                traceback=traceback.format_exc(),
            )
        finally:
            log_event(
                "runtime_wakeup_after_decision_finished",
                session_id=session_id,
                command_seq=command_seq,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    task = asyncio.create_task(_run_wakeup(), name=f"runtime-wakeup:{session_id}:{command_seq}")
    _RUNTIME_WAKEUP_TASKS[task_key] = task

    def _drop_completed_task(done_task: asyncio.Task[None]) -> None:
        if _RUNTIME_WAKEUP_TASKS.get(task_key) is done_task:
            _RUNTIME_WAKEUP_TASKS.pop(task_key, None)

    task.add_done_callback(_drop_completed_task)
    log_event(
        "runtime_wakeup_after_decision_scheduled",
        session_id=session_id,
        command_seq=command_seq,
    )


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
        runtime_status = str(runtime_state.get("status") or "")
        if auth_ctx.get("role") == "seat" and runtime_status in {"recovery_required", "waiting_input"}:
            session = session_service.get_session(session_id)
            runtime_cfg = dict(session.resolved_parameters.get("runtime", {}))
            pending_command = runtime_service.pending_resume_command(session_id)
            if pending_command is not None:
                command_seq = int(pending_command.get("seq", 0) or 0)
                await _process_pending_runtime_command(
                    session_id=session_id,
                    command_seq=command_seq,
                    session_service=session_service,
                    runtime_service=runtime_service,
                    trigger="stream_connect",
                )
                log_event(
                    "runtime_recovery_resumed_pending_command",
                    session_id=session_id,
                    reason=runtime_state.get("reason"),
                    command_seq=command_seq,
                    status=runtime_status,
                )
            elif runtime_status == "recovery_required" and runtime_service.has_unprocessed_runtime_commands(session_id):
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
                async with delivery_lock:
                    last_commit_seq = await _send_latest_view_commit(
                        websocket,
                        stream_service,
                        session_id=session_id,
                        last_commit_seq=last_commit_seq,
                        viewer=viewer,
                    )
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
                async with delivery_lock:
                    if seq > 0 and seq <= delivered_seq:
                        continue
                    filtered = await stream_service.project_message_for_viewer(message, viewer)
                    delivered_seq = max(delivered_seq, seq)
                    if filtered is not None:
                        if filtered.get("type") == "view_commit":
                            commit_seq = _commit_seq(filtered)
                            if commit_seq <= last_commit_seq:
                                continue
                            last_commit_seq = commit_seq
                        await _send_json_or_disconnect(websocket, filtered)
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
                        force=True,
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
                latest_commit = await stream_service.latest_view_commit_message_for_viewer(session_id, viewer)
                rejection_reason = _decision_view_commit_rejection_reason(message, latest_commit)
                if rejection_reason is not None:
                    prompt_service.record_external_decision_result(
                        {**message, "session_id": session_id},
                        status="stale",
                        reason=rejection_reason,
                    )
                    await stream_service.publish(
                        session_id,
                        "decision_ack",
                        build_decision_ack_payload(
                            request_id=str(message.get("request_id", "")),
                            status="stale",
                            player_id=int(message.get("player_id", 0)),
                            reason=rejection_reason,
                            provider="human",
                        ),
                    )
                    async with delivery_lock:
                        last_commit_seq = await _send_latest_view_commit(
                            websocket,
                            stream_service,
                            session_id=session_id,
                            last_commit_seq=-1,
                            viewer=viewer,
                        )
                    log_event(
                        "decision_rejected_by_view_commit",
                        session_id=session_id,
                        request_id=message.get("request_id"),
                        player_id=message.get("player_id"),
                        reason=rejection_reason,
                        view_commit_seq_seen=message.get("view_commit_seq_seen"),
                    )
                    continue
                message["session_id"] = session_id
                decision_state = prompt_service.submit_decision(message)
                if (
                    decision_state.get("status") == "stale"
                    and decision_state.get("reason") == "request_not_pending"
                    and _repair_missing_pending_prompt_from_view_commit(
                        prompt_service=prompt_service,
                        session_id=session_id,
                        message=message,
                        latest_commit=latest_commit,
                    )
                ):
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
                    command_seq=decision_state.get("command_seq"),
                )
                await _wake_runtime_after_accepted_decision(
                    decision_state=decision_state,
                    session_id=session_id,
                    session_service=session_service,
                    runtime_service=runtime_service,
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
