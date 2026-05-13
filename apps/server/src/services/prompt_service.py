from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Any, Callable

from apps.server.src.domain.protocol_ids import prompt_protocol_identity_fields
from apps.server.src.services.command_inbox import CommandInbox
from apps.server.src.services.prompt_fingerprint import (
    PROMPT_FINGERPRINT_VERSION,
    ensure_prompt_fingerprint,
    prompt_fingerprint_mismatch,
)


PENDING_PROMPT_ORPHAN_RETENTION_MS = 3 * 60 * 60 * 1000
_TERMINAL_RUNTIME_STATUSES = {
    "abandoned",
    "archived",
    "cancelled",
    "canceled",
    "completed",
    "deleted",
    "expired",
    "failed",
    "stopped",
}


@dataclass(slots=True)
class PendingPrompt:
    session_id: str
    request_id: str
    player_id: int
    timeout_ms: int
    created_at_ms: int
    payload: dict


class PromptService:
    """In-memory prompt lifecycle manager (B3 baseline)."""

    def __init__(
        self,
        prompt_store=None,
        command_store=None,
        command_inbox: CommandInbox | None = None,
        batch_collector=None,
    ) -> None:
        self._pending: dict[str, PendingPrompt] = {}
        self._resolved: dict[str, tuple[int, str, str]] = {}
        self._decisions: dict[str, dict] = {}
        self._lifecycle: dict[str, dict[str, Any]] = {}
        self._waiters: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._resolved_ttl_ms = 60 * 60 * 1000
        self._prompt_store = prompt_store
        self._command_store = command_store
        self._command_inbox = command_inbox or (
            CommandInbox(command_store=command_store) if command_store is not None else None
        )
        self._batch_collector = batch_collector

    def create_prompt(self, session_id: str, prompt: dict) -> PendingPrompt:
        superseded_waiters: list[threading.Event] = []
        with self._lock:
            self._prune_resolved()
            prompt = dict(prompt)
            request_id = str(prompt.get("request_id", "")).strip()
            if not request_id:
                raise ValueError("missing_request_id")
            _ensure_prompt_protocol_identity(prompt, request_id=request_id)
            prompt = ensure_prompt_fingerprint(prompt)
            storage_key = _scoped_request_key(session_id, request_id)
            existing = self._get_pending(request_id, session_id=session_id)
            if existing is not None:
                if prompt_fingerprint_mismatch(existing.payload, prompt):
                    raise ValueError("prompt_fingerprint_mismatch")
                raise ValueError("duplicate_pending_request_id")
            if self._has_recently_resolved_request(request_id, session_id=session_id):
                raise ValueError("duplicate_recent_request_id")
            if _is_module_prompt(prompt):
                _require_module_continuation(prompt)
            player_id = int(prompt.get("player_id", 0))
            timeout_ms = int(prompt.get("timeout_ms", 30000))
            created_at_ms = self._now_ms()
            prompt["created_at_ms"] = created_at_ms
            prompt["expires_at_ms"] = created_at_ms + PENDING_PROMPT_ORPHAN_RETENTION_MS
            superseded_waiters = self._supersede_pending_for_player(
                session_id=session_id,
                player_id=player_id,
                keep_request_id=request_id,
            )
            item = PendingPrompt(
                session_id=session_id,
                request_id=request_id,
                player_id=player_id,
                timeout_ms=timeout_ms,
                created_at_ms=created_at_ms,
                payload=prompt,
            )
            self._set_pending(item)
            self._record_lifecycle(
                request_id=request_id,
                state="created",
                session_id=session_id,
                player_id=player_id,
                prompt=prompt,
                now_ms=item.created_at_ms,
            )
            self._waiters[storage_key] = threading.Event()
        for waiter in superseded_waiters:
            waiter.set()
        return item

    def get_pending_prompt(self, request_id: str, session_id: str | None = None) -> PendingPrompt | None:
        with self._lock:
            normalized_request_id = str(request_id).strip()
            pending = self._get_pending(normalized_request_id, session_id=session_id)
            if pending is None:
                alias = self._resolve_pending_request_alias(normalized_request_id, session_id=session_id)
                if alias:
                    pending = self._get_pending(alias, session_id=session_id)
            if pending is None:
                return None
            return PendingPrompt(
                session_id=pending.session_id,
                request_id=pending.request_id,
                player_id=pending.player_id,
                timeout_ms=pending.timeout_ms,
                created_at_ms=pending.created_at_ms,
                payload=dict(pending.payload),
            )

    def list_pending_prompts(
        self,
        *,
        session_id: str | None = None,
        player_id: int | None = None,
    ) -> list[PendingPrompt]:
        with self._lock:
            prompts: list[PendingPrompt] = []
            for pending in self._iter_pending_values():
                if session_id is not None and pending.session_id != session_id:
                    continue
                if player_id is not None and pending.player_id != int(player_id):
                    continue
                prompts.append(
                    PendingPrompt(
                        session_id=pending.session_id,
                        request_id=pending.request_id,
                        player_id=pending.player_id,
                        timeout_ms=pending.timeout_ms,
                        created_at_ms=pending.created_at_ms,
                        payload=dict(pending.payload),
                    )
                )
            prompts.sort(key=lambda item: (item.created_at_ms, item.request_id))
            return prompts

    def submit_decision(self, payload: dict) -> dict:
        waiter: threading.Event | None = None
        with self._lock:
            self._prune_resolved()
            request_id = str(payload.get("request_id", "")).strip()
            if not request_id:
                return {"status": "rejected", "reason": "missing_request_id"}
            decision_session_id = str(payload.get("session_id") or "").strip()
            resolved_request_id = self._resolve_submitted_request_id(
                request_id,
                session_id=decision_session_id or None,
            )
            if resolved_request_id != request_id:
                payload = dict(payload)
                payload["request_id"] = resolved_request_id
                payload.setdefault("submitted_request_id", request_id)
                request_id = resolved_request_id
            choice_id = str(payload.get("choice_id", "")).strip()
            if not choice_id:
                self._record_lifecycle(request_id=request_id, state="rejected", decision=payload, reason="missing_choice_id")
                return {"status": "rejected", "reason": "missing_choice_id"}

            pending = self._get_pending(request_id, session_id=decision_session_id or None)
            storage_key = _scoped_request_key(pending.session_id, pending.request_id) if pending is not None else _scoped_request_key(decision_session_id, request_id)
            if pending is None:
                if self._has_recently_resolved_request(request_id, session_id=decision_session_id or None):
                    self._record_lifecycle(
                        request_id=request_id,
                        state="stale",
                        session_id=decision_session_id or None,
                        decision=payload,
                        reason="already_resolved",
                    )
                    return {"status": "stale", "reason": "already_resolved"}
                self._record_lifecycle(
                    request_id=request_id,
                    state="stale",
                    session_id=decision_session_id or None,
                    decision=payload,
                    reason="request_not_pending",
                )
                return {"status": "stale", "reason": "request_not_pending"}

            now = self._now_ms()
            if now > (pending.created_at_ms + pending.timeout_ms):
                self._delete_pending(request_id, session_id=pending.session_id)
                self._record_resolved(request_id=request_id, reason="prompt_timeout", session_id=pending.session_id)
                self._record_lifecycle(
                    request_id=request_id,
                    state="expired",
                    session_id=pending.session_id,
                    player_id=pending.player_id,
                    prompt=pending.payload,
                    decision=payload,
                    reason="prompt_timeout",
                    now_ms=now,
                )
                waiter = self._waiters.pop(storage_key, None)
                self._delete_decision(request_id, session_id=pending.session_id)
                result = {"status": "stale", "reason": "prompt_timeout"}
            else:
                player_id = int(payload.get("player_id", 0))
                if player_id != pending.player_id:
                    self._record_lifecycle(
                        request_id=request_id,
                        state="rejected",
                        session_id=pending.session_id,
                        player_id=pending.player_id,
                        prompt=pending.payload,
                        decision=payload,
                        reason="player_mismatch",
                        now_ms=now,
                    )
                    return {"status": "rejected", "reason": "player_mismatch"}
                expected_fingerprint = str(pending.payload.get("prompt_fingerprint") or "").strip()
                submitted_fingerprint = str(payload.get("prompt_fingerprint") or "").strip()
                if submitted_fingerprint and expected_fingerprint and submitted_fingerprint != expected_fingerprint:
                    self._record_lifecycle(
                        request_id=request_id,
                        state="rejected",
                        session_id=pending.session_id,
                        player_id=pending.player_id,
                        prompt=pending.payload,
                        decision=payload,
                        reason="prompt_fingerprint_mismatch",
                        now_ms=now,
                    )
                    return {"status": "rejected", "reason": "prompt_fingerprint_mismatch"}
                legal = {
                    str(choice.get("choice_id") or "").strip()
                    for choice in pending.payload.get("legal_choices", [])
                    if isinstance(choice, dict)
                }
                if legal and choice_id not in legal:
                    self._record_lifecycle(
                        request_id=request_id,
                        state="rejected",
                        session_id=pending.session_id,
                        player_id=pending.player_id,
                        prompt=pending.payload,
                        decision=payload,
                        reason="choice_not_legal",
                        now_ms=now,
                    )
                    return {"status": "rejected", "reason": "choice_not_legal"}
                if _is_module_prompt(pending.payload):
                    mismatch = _module_decision_mismatch(pending.payload, payload)
                    if mismatch:
                        self._record_lifecycle(
                            request_id=request_id,
                            state="rejected",
                            session_id=pending.session_id,
                            player_id=pending.player_id,
                            prompt=pending.payload,
                            decision=payload,
                            reason=mismatch,
                            now_ms=now,
                        )
                        return {"status": "rejected", "reason": mismatch}

                provider = str(payload.get("provider") or pending.payload.get("provider") or "human").strip().lower()
                if provider not in {"human", "ai"}:
                    provider = "human"
                decision_payload = dict(payload)
                decision_payload["provider"] = provider
                _copy_prompt_protocol_identity(pending.payload, decision_payload)
                _copy_prompt_player_identity(pending.payload, decision_payload)
                if expected_fingerprint:
                    decision_payload["prompt_fingerprint"] = expected_fingerprint
                    decision_payload["prompt_fingerprint_version"] = PROMPT_FINGERPRINT_VERSION
                self._record_lifecycle(
                    request_id=request_id,
                    state="decision_received",
                    session_id=pending.session_id,
                    player_id=pending.player_id,
                    prompt=pending.payload,
                    decision=decision_payload,
                    now_ms=now,
                )
                command_payload = {
                    "request_id": request_id,
                    "player_id": player_id,
                    "request_type": str(pending.payload.get("request_type") or ""),
                    "choice_id": choice_id,
                    "provider": provider,
                    "decision": decision_payload,
                    "submitted_at_ms": now,
                }
                _copy_prompt_player_identity(decision_payload, command_payload)
                command_payload.update(_module_command_continuation_fields(pending.payload, decision_payload))
                resolved_payload = {
                    "request_id": request_id,
                    "resolved_at_ms": now,
                    "reason": "accepted",
                    "session_id": pending.session_id,
                }
                accepted_command: dict | None = None
                batch_result = None
                if _is_simultaneous_batch_prompt(pending.payload) and self._batch_collector is not None:
                    batch_result = self._record_batch_response(
                        pending=pending,
                        response=command_payload,
                        server_time_ms=now,
                    )
                    accepted_command = batch_result.command
                    self._delete_pending(request_id, session_id=pending.session_id)
                    self._set_decision(request_id, decision_payload, session_id=pending.session_id)
                    self._record_resolved(
                        request_id=request_id,
                        reason="accepted",
                        now_ms=now,
                        session_id=pending.session_id,
                    )
                elif self._command_inbox is not None and self._command_inbox.supports_atomic_prompt_decision(self._prompt_store):
                    accepted_command = self._command_inbox.accept_prompt_decision(
                        prompt_store=self._prompt_store,
                        session_id=pending.session_id,
                        request_id=request_id,
                        decision_payload=decision_payload,
                        resolved_payload=resolved_payload,
                        command_payload=command_payload,
                        server_time_ms=now,
                    )
                    if accepted_command is None:
                        self._record_lifecycle(
                            request_id=request_id,
                            state="stale",
                            session_id=pending.session_id,
                            player_id=pending.player_id,
                            prompt=pending.payload,
                            decision=decision_payload,
                            reason="request_not_pending",
                            now_ms=now,
                        )
                        return {"status": "stale", "reason": "request_not_pending"}
                else:
                    if self._command_inbox is not None:
                        accepted_command = self._command_inbox.append_decision_command(
                            session_id=pending.session_id,
                            command_payload=command_payload,
                            request_id=request_id,
                            server_time_ms=now,
                        )
                        if accepted_command is None:
                            self._record_lifecycle(
                                request_id=request_id,
                                state="stale",
                                session_id=pending.session_id,
                                player_id=pending.player_id,
                                prompt=pending.payload,
                                decision=decision_payload,
                                reason="command_append_failed",
                                now_ms=now,
                            )
                            return {"status": "stale", "reason": "command_append_failed"}
                    self._delete_pending(request_id, session_id=pending.session_id)
                    self._set_decision(request_id, decision_payload, session_id=pending.session_id)
                    self._record_resolved(
                        request_id=request_id,
                        reason="accepted",
                        now_ms=now,
                        session_id=pending.session_id,
                    )
                self._record_lifecycle(
                    request_id=request_id,
                    state="accepted",
                    session_id=pending.session_id,
                    player_id=pending.player_id,
                    prompt=pending.payload,
                    decision=decision_payload,
                    reason="accepted",
                    now_ms=now,
                )
                self._record_lifecycle(
                    request_id=request_id,
                    state="resolved",
                    session_id=pending.session_id,
                    player_id=pending.player_id,
                    prompt=pending.payload,
                    decision=decision_payload,
                    reason="accepted",
                    now_ms=now,
                )
                waiter = self._waiters.get(storage_key)
                result = {
                    "status": "accepted",
                    "reason": None,
                    "session_id": pending.session_id,
                    "command_seq": _command_seq(accepted_command),
                }
                if batch_result is not None:
                    result["batch_status"] = batch_result.status
                    result["remaining_player_ids"] = list(batch_result.remaining_player_ids)
        if waiter is not None:
            waiter.set()
        return result

    def timeout_pending(self, now_ms: int | None = None, session_id: str | None = None) -> list[PendingPrompt]:
        now = now_ms if now_ms is not None else self._now_ms()
        timed_out: list[PendingPrompt] = []
        to_notify: list[threading.Event] = []
        with self._lock:
            for storage_key, pending in list(self._iter_pending_items()):
                request_id = pending.request_id
                if session_id is not None and pending.session_id != session_id:
                    continue
                if now > (pending.created_at_ms + pending.timeout_ms):
                    if not self._delete_pending(storage_key):
                        continue
                    timed_out.append(pending)
                    self._record_resolved(
                        request_id=request_id,
                        reason="prompt_timeout",
                        now_ms=now,
                        session_id=pending.session_id,
                    )
                    self._record_lifecycle(
                        request_id=request_id,
                        state="expired",
                        session_id=pending.session_id,
                        player_id=pending.player_id,
                        prompt=pending.payload,
                        reason="prompt_timeout",
                        now_ms=now,
                    )
                    waiter = self._waiters.pop(storage_key, None)
                    self._delete_decision(request_id, session_id=pending.session_id)
                    if waiter is not None:
                        to_notify.append(waiter)
        for waiter in to_notify:
            waiter.set()
        return timed_out

    def cleanup_orphaned_pending(
        self,
        *,
        now_ms: int | None = None,
        session_id: str | None = None,
        runtime_status_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        lease_owner_lookup: Callable[[str], str | None] | None = None,
    ) -> list[PendingPrompt]:
        now = now_ms if now_ms is not None else self._now_ms()
        cleaned: list[PendingPrompt] = []
        to_notify: list[threading.Event] = []
        with self._lock:
            for storage_key, pending in list(self._iter_pending_items()):
                if session_id is not None and pending.session_id != session_id:
                    continue
                if now <= self._pending_orphan_expires_at_ms(pending):
                    continue
                runtime_status = runtime_status_lookup(pending.session_id) if runtime_status_lookup is not None else None
                lease_owner = lease_owner_lookup(pending.session_id) if lease_owner_lookup is not None else None
                if not self._pending_session_is_orphaned(
                    runtime_status=runtime_status,
                    lease_owner=lease_owner,
                    now_ms=now,
                ):
                    continue
                cleaned.append(pending)
                self._delete_pending(pending.request_id, session_id=pending.session_id)
                self._delete_decision(pending.request_id, session_id=pending.session_id)
                self._record_resolved(
                    request_id=pending.request_id,
                    reason="orphan_pending_cleanup",
                    now_ms=now,
                    session_id=pending.session_id,
                )
                self._record_lifecycle(
                    request_id=pending.request_id,
                    state="expired",
                    session_id=pending.session_id,
                    player_id=pending.player_id,
                    prompt=pending.payload,
                    reason="orphan_pending_cleanup",
                    now_ms=now,
                )
                waiter = self._waiters.pop(storage_key, None)
                if waiter is not None:
                    to_notify.append(waiter)
        for waiter in to_notify:
            waiter.set()
        return cleaned

    def record_timeout_fallback_decision(
        self,
        pending: PendingPrompt,
        *,
        choice_id: str,
        submitted_at_ms: int | None = None,
    ) -> dict:
        now = submitted_at_ms if submitted_at_ms is not None else self._now_ms()
        request_id = str(pending.request_id).strip()
        fallback_choice_id = str(choice_id or "timeout_fallback").strip() or "timeout_fallback"
        legal_choice_ids = {
            str(choice.get("choice_id") or "").strip()
            for choice in pending.payload.get("legal_choices", [])
            if isinstance(choice, dict) and str(choice.get("choice_id") or "").strip()
        }
        if legal_choice_ids and fallback_choice_id not in legal_choice_ids:
            raise ValueError("prompt_fallback_choice_not_legal")
        decision_payload = {
            "type": "decision",
            "request_id": request_id,
            "player_id": int(pending.player_id),
            "choice_id": fallback_choice_id,
            "choice_payload": {},
            "provider": "timeout_fallback",
        }
        _copy_prompt_protocol_identity(pending.payload, decision_payload)
        _copy_prompt_player_identity(pending.payload, decision_payload)
        decision_payload.update(_module_command_continuation_fields(pending.payload, decision_payload))
        expected_fingerprint = str(pending.payload.get("prompt_fingerprint") or "").strip()
        if expected_fingerprint:
            decision_payload["prompt_fingerprint"] = expected_fingerprint
            decision_payload["prompt_fingerprint_version"] = PROMPT_FINGERPRINT_VERSION
        command_payload = {
            "request_id": request_id,
            "player_id": int(pending.player_id),
            "request_type": str(pending.payload.get("request_type") or ""),
            "choice_id": fallback_choice_id,
            "choice_payload": {},
            "provider": "timeout_fallback",
            "decision": decision_payload,
            "submitted_at_ms": now,
            "source": "timeout_fallback",
        }
        _copy_prompt_player_identity(decision_payload, command_payload)
        command_payload.update(_module_command_continuation_fields(pending.payload, decision_payload))
        with self._lock:
            self._set_decision(request_id, decision_payload, session_id=pending.session_id)
            self._record_lifecycle(
                request_id=request_id,
                state="decision_received",
                session_id=pending.session_id,
                player_id=pending.player_id,
                prompt=pending.payload,
                decision=decision_payload,
                now_ms=now,
            )
            command_ref = None
            batch_result = None
            if _is_simultaneous_batch_prompt(pending.payload) and self._batch_collector is not None:
                batch_result = self._record_batch_response(
                    pending=pending,
                    response=command_payload,
                    server_time_ms=now,
                )
                command_ref = batch_result.command
            elif self._command_inbox is not None:
                command_ref = self._command_inbox.append_decision_command(
                    session_id=pending.session_id,
                    command_payload=command_payload,
                    request_id=request_id,
                    server_time_ms=now,
                )
            if command_ref is not None:
                decision_payload["status"] = "accepted"
                decision_payload["session_id"] = pending.session_id
                decision_payload["command_seq"] = command_ref.get("seq")
            if batch_result is not None:
                decision_payload["status"] = "accepted"
                decision_payload["session_id"] = pending.session_id
                decision_payload["command_seq"] = _command_seq(command_ref)
                decision_payload["batch_status"] = batch_result.status
                decision_payload["remaining_player_ids"] = list(batch_result.remaining_player_ids)
            self._record_lifecycle(
                request_id=request_id,
                state="accepted",
                session_id=pending.session_id,
                player_id=pending.player_id,
                prompt=pending.payload,
                decision=decision_payload,
                reason="timeout_fallback",
                now_ms=now,
            )
            self._record_lifecycle(
                request_id=request_id,
                state="resolved",
                session_id=pending.session_id,
                player_id=pending.player_id,
                prompt=pending.payload,
                decision=decision_payload,
                reason="timeout_fallback",
                now_ms=now,
            )
        return decision_payload

    def _record_batch_response(self, *, pending: PendingPrompt, response: dict, server_time_ms: int):
        batch_id = str(pending.payload.get("batch_id") or "").strip()
        expected_player_ids = [
            int(raw)
            for raw in pending.payload.get("missing_player_ids", [])
            if _int_or_none(raw) is not None
        ]
        if not expected_player_ids:
            expected_player_ids = [int(pending.player_id)]
        return self._batch_collector.record_response(
            session_id=pending.session_id,
            batch_id=batch_id,
            player_id=int(pending.player_id),
            response=response,
            expected_player_ids=expected_player_ids,
            server_time_ms=server_time_ms,
        )

    def wait_for_decision(self, request_id: str, timeout_ms: int, session_id: str | None = None) -> dict | None:
        with self._lock:
            request_id = str(request_id or "").strip()
            decision = self._get_decision(request_id, session_id=session_id)
            if decision is not None:
                return decision
            lifecycle_alias = self._resolve_lifecycle_request_alias(request_id, session_id=session_id)
            if lifecycle_alias:
                request_id = lifecycle_alias
                decision = self._get_decision(request_id, session_id=session_id)
                if decision is not None:
                    return decision
            if timeout_ms <= 0:
                return None
            request_id = self._resolve_submitted_request_id(request_id, session_id=session_id)
            waiter_key = self._waiter_key(request_id, session_id=session_id)
            waiter = self._waiters.get(waiter_key) if waiter_key is not None else None
            if waiter is None:
                pending = self._get_pending(request_id, session_id=session_id)
                if pending is None:
                    return None
                waiter_key = _scoped_request_key(pending.session_id, pending.request_id)
                waiter = threading.Event()
                self._waiters[waiter_key] = waiter
        deadline = self._now_ms() + timeout_ms
        while self._now_ms() < deadline:
            waiter.wait(min(50, max(1, deadline - self._now_ms())) / 1000.0)
            with self._lock:
                decision = self._get_decision(request_id, session_id=session_id)
                if decision is not None:
                    if waiter_key is not None:
                        self._waiters.pop(waiter_key, None)
                    return decision
        with self._lock:
            decision = self._get_decision(request_id, session_id=session_id)
            if waiter_key is not None:
                self._waiters.pop(waiter_key, None)
            return decision

    def expire_prompt(self, request_id: str, reason: str = "prompt_timeout", session_id: str | None = None) -> PendingPrompt | None:
        waiter: threading.Event | None = None
        with self._lock:
            pending = self._get_pending(request_id, session_id=session_id)
            if pending is None:
                return None
            storage_key = _scoped_request_key(pending.session_id, pending.request_id)
            self._delete_pending(request_id, session_id=pending.session_id)
            self._record_resolved(request_id=request_id, reason=reason, session_id=pending.session_id)
            self._record_lifecycle(
                request_id=request_id,
                state="expired",
                session_id=pending.session_id,
                player_id=pending.player_id,
                prompt=pending.payload,
                reason=reason,
            )
            self._delete_decision(request_id, session_id=pending.session_id)
            waiter = self._waiters.pop(storage_key, None)
        if waiter is not None:
            waiter.set()
        return pending

    def has_pending_for_session(self, session_id: str) -> bool:
        with self._lock:
            for pending in self._iter_pending_values():
                if pending.session_id == session_id:
                    return True
        return False

    def delete_session_data(self, session_id: str) -> None:
        with self._lock:
            for storage_key, pending in list(self._iter_pending_items()):
                if pending.session_id != session_id:
                    continue
                self._delete_pending(storage_key)
                self._delete_decision(pending.request_id, session_id=pending.session_id)
                self._delete_lifecycle(pending.request_id, session_id=pending.session_id)
                self._waiters.pop(storage_key, None)

    def mark_prompt_delivered(
        self,
        request_id: str,
        *,
        session_id: str | None = None,
        stream_seq: int | None = None,
        commit_seq: int | None = None,
    ) -> dict[str, Any] | None:
        normalized_request_id = str(request_id).strip()
        with self._lock:
            resolved_request_id = self._resolve_submitted_request_id(normalized_request_id, session_id=session_id)
            pending = self._get_pending(resolved_request_id, session_id=session_id)
            current = self._get_lifecycle(resolved_request_id, session_id=session_id)
            if pending is None and current is None:
                return None
            return self._record_lifecycle(
                request_id=resolved_request_id,
                state="delivered",
                session_id=pending.session_id if pending is not None else session_id,
                player_id=pending.player_id if pending is not None else None,
                prompt=pending.payload if pending is not None else None,
                stream_seq=stream_seq,
                commit_seq=commit_seq,
            )

    def record_external_decision_result(
        self,
        payload: dict,
        *,
        status: str,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return None
        session_id = str(payload.get("session_id") or "").strip() or None
        with self._lock:
            resolved_request_id = self._resolve_submitted_request_id(request_id, session_id=session_id)
            lifecycle_payload = dict(payload)
            if resolved_request_id != request_id:
                lifecycle_payload["request_id"] = resolved_request_id
                lifecycle_payload.setdefault("submitted_request_id", request_id)
                lifecycle_payload.setdefault("public_request_id", request_id)
            pending = self._get_pending(resolved_request_id, session_id=session_id)
            return self._record_lifecycle(
                request_id=resolved_request_id,
                state=str(status or "rejected"),
                session_id=pending.session_id if pending is not None else session_id,
                player_id=pending.player_id if pending is not None else None,
                prompt=pending.payload if pending is not None else None,
                decision=lifecycle_payload,
                reason=reason,
            )

    def get_prompt_lifecycle(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            normalized_request_id = str(request_id).strip()
            lifecycle = self._get_lifecycle(normalized_request_id, session_id=session_id)
            if lifecycle is None:
                lifecycle_alias = self._resolve_lifecycle_request_alias(normalized_request_id, session_id=session_id)
                if lifecycle_alias:
                    lifecycle = self._get_lifecycle(lifecycle_alias, session_id=session_id)
            return dict(lifecycle) if lifecycle is not None else None

    def list_prompt_lifecycle(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if self._prompt_store is not None and callable(getattr(self._prompt_store, "list_lifecycle", None)):
                return [dict(item) for item in self._prompt_store.list_lifecycle(session_id)]
            items = [dict(item) for item in self._lifecycle.values()]
            if session_id is not None:
                items = [item for item in items if str(item.get("session_id") or "") == str(session_id)]
            return sorted(items, key=lambda item: (int(item.get("updated_at_ms") or 0), str(item.get("request_id") or "")))

    def _record_resolved(
        self,
        request_id: str,
        reason: str,
        now_ms: int | None = None,
        session_id: str | None = None,
    ) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        payload = {"request_id": str(request_id), "resolved_at_ms": now, "reason": reason}
        if session_id is not None:
            payload["session_id"] = str(session_id)
        if self._prompt_store is not None:
            self._prompt_store.save_resolved(request_id, payload, session_id=session_id)
        else:
            self._resolved[_scoped_request_key(session_id, request_id)] = (now, reason, str(session_id or ""))
        self._prune_resolved(now)

    def _prune_resolved(self, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        cutoff = now - self._resolved_ttl_ms
        if self._prompt_store is not None:
            for storage_key, payload in self._prompt_store.list_resolved().items():
                resolved_at = int(payload.get("resolved_at_ms", 0))
                if resolved_at < cutoff:
                    self._prompt_store.delete_resolved(storage_key)
                    self._prompt_store.delete_decision(storage_key)
                    self._delete_lifecycle(storage_key)
            return
        for storage_key, (resolved_at, _, _) in list(self._resolved.items()):
            if resolved_at < cutoff:
                self._resolved.pop(storage_key, None)
                self._decisions.pop(storage_key, None)
                self._lifecycle.pop(storage_key, None)

    def _supersede_pending_for_player(
        self,
        *,
        session_id: str,
        player_id: int,
        keep_request_id: str,
    ) -> list[threading.Event]:
        waiters: list[threading.Event] = []
        now = self._now_ms()
        for existing_key, pending in list(self._iter_pending_items()):
            if pending.session_id == session_id and pending.request_id == keep_request_id:
                continue
            if pending.session_id != session_id or pending.player_id != player_id:
                continue
            self._delete_pending(existing_key)
            self._delete_decision(pending.request_id, session_id=pending.session_id)
            self._record_resolved(
                request_id=pending.request_id,
                reason="superseded",
                now_ms=now,
                session_id=pending.session_id,
            )
            self._record_lifecycle(
                request_id=pending.request_id,
                state="expired",
                session_id=pending.session_id,
                player_id=pending.player_id,
                prompt=pending.payload,
                reason="superseded",
                now_ms=now,
            )
            waiter = self._waiters.pop(existing_key, None)
            if waiter is not None:
                waiters.append(waiter)
        return waiters

    def _has_pending_request(self, request_id: str, session_id: str | None = None) -> bool:
        if self._prompt_store is not None:
            return self._prompt_store.get_pending(request_id, session_id=session_id) is not None
        return self._pending_key(request_id, session_id=session_id) is not None

    def _has_recently_resolved_request(self, request_id: str, session_id: str | None = None) -> bool:
        normalized_session_id = str(session_id or "").strip()
        if self._prompt_store is not None:
            resolved = self._prompt_store.get_resolved(request_id, session_id=normalized_session_id or None)
            if resolved is None:
                return False
            if not normalized_session_id:
                return True
            return str(resolved.get("session_id") or "").strip() == normalized_session_id
        resolved_key = self._pending_key(request_id, session_id=normalized_session_id or None, collection=self._resolved)
        resolved = self._resolved.get(resolved_key) if resolved_key is not None else None
        if resolved is None:
            return False
        if not normalized_session_id:
            return True
        return str(resolved[2] or "").strip() == normalized_session_id

    def _set_pending(self, pending: PendingPrompt) -> None:
        if self._prompt_store is not None:
            self._prompt_store.save_pending(
                pending.request_id,
                {
                    "session_id": pending.session_id,
                    "request_id": pending.request_id,
                    "player_id": pending.player_id,
                    "timeout_ms": pending.timeout_ms,
                    "created_at_ms": pending.created_at_ms,
                    "payload": dict(pending.payload),
                },
                session_id=pending.session_id,
            )
            return
        self._pending[_scoped_request_key(pending.session_id, pending.request_id)] = pending

    def _get_pending(self, request_id: str, session_id: str | None = None) -> PendingPrompt | None:
        if self._prompt_store is not None:
            raw = self._prompt_store.get_pending(request_id, session_id=session_id)
            if raw is None:
                return None
            return PendingPrompt(
                session_id=str(raw.get("session_id", "")),
                request_id=str(raw.get("request_id", "")),
                player_id=int(raw.get("player_id", 0)),
                timeout_ms=int(raw.get("timeout_ms", 0)),
                created_at_ms=int(raw.get("created_at_ms", 0)),
                payload=dict(raw.get("payload", {})),
            )
        key = self._pending_key(request_id, session_id=session_id)
        return self._pending.get(key) if key is not None else None

    @staticmethod
    def _pending_orphan_expires_at_ms(pending: PendingPrompt) -> int:
        try:
            expires_at_ms = int(pending.payload.get("expires_at_ms") or 0)
        except (TypeError, ValueError):
            expires_at_ms = 0
        if expires_at_ms > 0:
            return expires_at_ms
        return pending.created_at_ms + PENDING_PROMPT_ORPHAN_RETENTION_MS

    @staticmethod
    def _pending_session_is_orphaned(
        *,
        runtime_status: dict[str, Any] | None,
        lease_owner: str | None,
        now_ms: int,
    ) -> bool:
        status = str((runtime_status or {}).get("status") or "").strip()
        if status in _TERMINAL_RUNTIME_STATUSES:
            return True
        if str(lease_owner or "").strip():
            return False
        if not runtime_status:
            return True
        try:
            lease_expires_at_ms = int(runtime_status.get("lease_expires_at_ms") or 0)
        except (TypeError, ValueError):
            lease_expires_at_ms = 0
        if lease_expires_at_ms > now_ms:
            return False
        try:
            last_activity_ms = int(runtime_status.get("last_activity_ms") or 0)
        except (TypeError, ValueError):
            last_activity_ms = 0
        if last_activity_ms > 0 and now_ms <= last_activity_ms + PENDING_PROMPT_ORPHAN_RETENTION_MS:
            return False
        return True

    def _delete_pending(self, request_id: str, session_id: str | None = None) -> bool:
        if self._prompt_store is not None:
            return bool(self._prompt_store.delete_pending(request_id, session_id=session_id))
        key = self._pending_key(request_id, session_id=session_id)
        if key is not None:
            return self._pending.pop(key, None) is not None
        return False

    def _iter_pending_values(self) -> list[PendingPrompt]:
        if self._prompt_store is not None:
            values: list[PendingPrompt] = []
            for item in self._prompt_store.list_pending():
                request_id = str(item.get("request_id", "")).strip()
                session_id = str(item.get("session_id") or "").strip() or None
                pending = self._get_pending(request_id, session_id=session_id)
                if pending is not None:
                    values.append(pending)
            return values
        return list(self._pending.values())

    def _iter_pending_items(self) -> list[tuple[str, PendingPrompt]]:
        items: list[tuple[str, PendingPrompt]] = []
        if self._prompt_store is not None:
            for raw in self._prompt_store.list_pending():
                request_id = str(raw.get("request_id", "")).strip()
                session_id = str(raw.get("session_id") or "").strip()
                pending = self._get_pending(request_id, session_id=session_id or None)
                if pending is not None:
                    items.append((_scoped_request_key(session_id, request_id), pending))
            return items
        return list(self._pending.items())

    def _set_decision(self, request_id: str, payload: dict, session_id: str | None = None) -> None:
        if self._prompt_store is not None:
            self._prompt_store.save_decision(request_id, payload, session_id=session_id)
            return
        self._decisions[_scoped_request_key(session_id, request_id)] = payload

    def _get_decision(self, request_id: str, session_id: str | None = None) -> dict | None:
        if self._prompt_store is not None:
            getter = getattr(self._prompt_store, "get_decision", None)
            if callable(getter):
                return getter(request_id, session_id=session_id)
            return self._prompt_store.pop_decision(request_id, session_id=session_id)
        key = self._pending_key(request_id, session_id=session_id, collection=self._decisions)
        decision = self._decisions.get(key) if key is not None else None
        return dict(decision) if decision is not None else None

    def _pop_decision(self, request_id: str, session_id: str | None = None) -> dict | None:
        if self._prompt_store is not None:
            return self._prompt_store.pop_decision(request_id, session_id=session_id)
        key = self._pending_key(request_id, session_id=session_id, collection=self._decisions)
        return self._decisions.pop(key, None) if key is not None else None

    def _delete_decision(self, request_id: str, session_id: str | None = None) -> None:
        if self._prompt_store is not None:
            self._prompt_store.delete_decision(request_id, session_id=session_id)
            return
        key = self._pending_key(request_id, session_id=session_id, collection=self._decisions)
        if key is not None:
            self._decisions.pop(key, None)

    def _record_lifecycle(
        self,
        *,
        request_id: str,
        state: str,
        session_id: str | None = None,
        player_id: int | None = None,
        prompt: dict | None = None,
        decision: dict | None = None,
        reason: str | None = None,
        stream_seq: int | None = None,
        commit_seq: int | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized_request_id = str(request_id or "").strip()
        now = now_ms if now_ms is not None else self._now_ms()
        current = self._get_lifecycle(normalized_request_id, session_id=session_id) or {}
        record: dict[str, Any] = dict(current)
        record.setdefault("schema_version", 1)
        record["request_id"] = normalized_request_id
        normalized_state = str(state or "unknown")
        record["state"] = normalized_state
        record["updated_at_ms"] = int(now)
        if "created_at_ms" not in record or state == "created":
            record["created_at_ms"] = int(now)
        if session_id is not None:
            record["session_id"] = str(session_id)
        if player_id is not None:
            record["player_id"] = int(player_id)
        if prompt is not None:
            record["request_type"] = str(prompt.get("request_type") or record.get("request_type") or "")
            record["prompt"] = _compact_prompt_lifecycle_payload(prompt)
        if decision is not None:
            compact_decision = _compact_decision_lifecycle_payload(decision)
            record["decision"] = compact_decision
            if normalized_state == "stale":
                stale_decisions = record.get("stale_decisions")
                if not isinstance(stale_decisions, list):
                    stale_decisions = []
                stale_decisions.append(compact_decision)
                record["stale_decisions"] = stale_decisions[-10:]
        if reason is not None:
            record["reason"] = str(reason)
        elif state in {"accepted", "delivered", "created", "decision_received", "resolved"}:
            record.pop("reason", None)
        if stream_seq is not None:
            record["stream_seq"] = int(stream_seq)
        if commit_seq is not None:
            record["commit_seq"] = int(commit_seq)
        record["state_history"] = self._append_lifecycle_history(
            record.get("state_history"),
            previous_state=current.get("state"),
            state=normalized_state,
            now_ms=int(now),
            reason=record.get("reason") if reason is not None else None,
            stream_seq=stream_seq,
            commit_seq=commit_seq,
        )
        if state == "decision_received":
            record["decision_received_at_ms"] = int(now)
        if state == "delivered":
            record["delivered_at_ms"] = int(now)
        if state == "accepted":
            record["accepted_at_ms"] = int(now)
        if state == "resolved":
            record["resolved_at_ms"] = int(now)
        if state == "stale":
            record["stale_at_ms"] = int(now)
        if state in {"accepted", "rejected", "stale", "expired", "resolved"}:
            record["terminal_at_ms"] = int(now)
        self._set_lifecycle(normalized_request_id, record, session_id=session_id)
        return dict(record)

    @staticmethod
    def _append_lifecycle_history(
        history: Any,
        *,
        previous_state: Any,
        state: str,
        now_ms: int,
        reason: Any = None,
        stream_seq: int | None = None,
        commit_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = (
            [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
        )
        if not events and isinstance(previous_state, str) and previous_state and previous_state != state:
            events.append({"state": previous_state})
        event: dict[str, Any] = {"state": state, "at_ms": int(now_ms)}
        if reason is not None:
            event["reason"] = str(reason)
        if stream_seq is not None:
            event["stream_seq"] = int(stream_seq)
        if commit_seq is not None:
            event["commit_seq"] = int(commit_seq)
        events.append(event)
        return events[-32:]

    def _set_lifecycle(self, request_id: str, payload: dict[str, Any], session_id: str | None = None) -> None:
        if self._prompt_store is not None and callable(getattr(self._prompt_store, "save_lifecycle", None)):
            self._prompt_store.save_lifecycle(request_id, payload, session_id=session_id)
            return
        self._lifecycle[_scoped_request_key(session_id, request_id)] = dict(payload)

    def _get_lifecycle(self, request_id: str, session_id: str | None = None) -> dict[str, Any] | None:
        if self._prompt_store is not None and callable(getattr(self._prompt_store, "get_lifecycle", None)):
            return self._prompt_store.get_lifecycle(request_id, session_id=session_id)
        key = self._pending_key(request_id, session_id=session_id, collection=self._lifecycle)
        lifecycle = self._lifecycle.get(key) if key is not None else None
        return dict(lifecycle) if lifecycle is not None else None

    def _delete_lifecycle(self, request_id: str, session_id: str | None = None) -> None:
        if self._prompt_store is not None and callable(getattr(self._prompt_store, "delete_lifecycle", None)):
            self._prompt_store.delete_lifecycle(request_id, session_id=session_id)
            return
        key = self._pending_key(request_id, session_id=session_id, collection=self._lifecycle)
        if key is not None:
            self._lifecycle.pop(key, None)

    def _resolve_submitted_request_id(self, request_id: str, session_id: str | None = None) -> str:
        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return ""
        if self._get_pending(normalized_request_id, session_id=session_id) is not None:
            return normalized_request_id
        pending_alias = self._resolve_pending_request_alias(normalized_request_id, session_id=session_id)
        if pending_alias:
            return pending_alias
        lifecycle_alias = self._resolve_lifecycle_request_alias(normalized_request_id, session_id=session_id)
        if lifecycle_alias:
            return lifecycle_alias
        return normalized_request_id

    def _resolve_pending_request_alias(self, request_id: str, session_id: str | None = None) -> str:
        matches: set[str] = set()
        for pending in self._iter_pending_values():
            if session_id is not None and pending.session_id != str(session_id):
                continue
            if _payload_request_alias_matches(pending.payload, request_id):
                matches.add(pending.request_id)
        return next(iter(matches)) if len(matches) == 1 else ""

    def _resolve_lifecycle_request_alias(self, request_id: str, session_id: str | None = None) -> str:
        matches: set[str] = set()
        for lifecycle in self._iter_lifecycle_values(session_id=session_id):
            prompt_payload = lifecycle.get("prompt")
            decision_payload = lifecycle.get("decision")
            if isinstance(prompt_payload, dict) and _payload_request_alias_matches(prompt_payload, request_id):
                matches.add(str(lifecycle.get("request_id") or "").strip())
            if isinstance(decision_payload, dict) and _payload_request_alias_matches(decision_payload, request_id):
                matches.add(str(lifecycle.get("request_id") or "").strip())
        matches.discard("")
        return next(iter(matches)) if len(matches) == 1 else ""

    def _iter_lifecycle_values(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if self._prompt_store is not None and callable(getattr(self._prompt_store, "list_lifecycle", None)):
            return [dict(item) for item in self._prompt_store.list_lifecycle(session_id=session_id)]
        values = [dict(item) for item in self._lifecycle.values()]
        if session_id is not None:
            normalized_session_id = str(session_id)
            values = [item for item in values if str(item.get("session_id") or "") == normalized_session_id]
        return values

    def _pending_key(
        self,
        request_id: str,
        *,
        session_id: str | None = None,
        collection: dict[str, Any] | None = None,
    ) -> str | None:
        normalized_request_id = str(request_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_request_id:
            return None
        if "\x1f" in normalized_request_id:
            return normalized_request_id
        items = self._pending if collection is None else collection
        if normalized_session_id:
            return _scoped_request_key(normalized_session_id, normalized_request_id)
        if normalized_request_id in items:
            return normalized_request_id
        matches: list[str] = []
        for key, value in items.items():
            raw_request_id = ""
            raw_session_id = ""
            if isinstance(value, PendingPrompt):
                raw_request_id = value.request_id
                raw_session_id = value.session_id
            elif isinstance(value, dict):
                raw_request_id = str(value.get("request_id") or value.get("prompt", {}).get("request_id") or "")
                raw_session_id = str(value.get("session_id") or "")
            elif isinstance(value, tuple):
                raw_request_id = _request_id_from_scoped_key(key)
                raw_session_id = str(value[2] or "") if len(value) > 2 else ""
            if raw_request_id == normalized_request_id and (not normalized_session_id or raw_session_id == normalized_session_id):
                matches.append(key)
        if len(matches) == 1:
            return matches[0]
        return None

    def _waiter_key(self, request_id: str, session_id: str | None = None) -> str | None:
        normalized_session_id = str(session_id or "").strip()
        normalized_request_id = str(request_id or "").strip()
        if normalized_session_id:
            return _scoped_request_key(normalized_session_id, normalized_request_id)
        key = self._pending_key(normalized_request_id)
        if key is not None:
            return key
        matches = [key for key in self._waiters if _request_id_from_scoped_key(key) == normalized_request_id]
        if len(matches) == 1:
            return matches[0]
        return None

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)


def _command_seq(command: dict | None) -> int | None:
    if not isinstance(command, dict):
        return None
    try:
        return int(command.get("seq", 0) or 0)
    except (TypeError, ValueError):
        return None


def _scoped_request_key(session_id: str | None, request_id: str) -> str:
    normalized_request_id = str(request_id or "").strip()
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id or "\x1f" in normalized_request_id:
        return normalized_request_id
    return f"{normalized_session_id}\x1f{normalized_request_id}"


def _request_id_from_scoped_key(key: str) -> str:
    return str(key or "").split("\x1f", 1)[1] if "\x1f" in str(key or "") else str(key or "")


def _is_module_prompt(prompt: dict) -> bool:
    return (
        str(prompt.get("runner_kind") or prompt.get("runtime_runner_kind") or "").strip() == "module"
        or isinstance(prompt.get("runtime_module"), dict)
        or bool(prompt.get("resume_token"))
    )


def _require_module_continuation(prompt: dict) -> None:
    required = ("resume_token", "frame_id", "module_id", "module_type", "module_cursor")
    missing = [field for field in required if not str(prompt.get(field) or "").strip()]
    if missing:
        raise ValueError(f"missing_module_continuation:{','.join(missing)}")
    if _is_simultaneous_batch_prompt(prompt):
        if not str(prompt.get("batch_id") or "").strip():
            raise ValueError("missing_batch_id")
        if not isinstance(prompt.get("missing_player_ids"), list) or not isinstance(
            prompt.get("resume_tokens_by_player_id"),
            dict,
        ):
            raise ValueError("missing_simultaneous_batch_state")


def _is_simultaneous_batch_prompt(prompt: dict) -> bool:
    module_type = str(prompt.get("module_type") or "").strip()
    request_type = str(prompt.get("request_type") or "").strip()
    module_cursor = str(prompt.get("module_cursor") or "").strip()
    if module_type == "SimultaneousPromptBatchModule":
        return True
    return (
        module_type == "ResupplyModule"
        and request_type in {"burden_exchange", "resupply_choice"}
        and module_cursor.startswith("await_resupply_batch")
    )


def _module_decision_mismatch(prompt: dict, decision: dict) -> str:
    for field, reason in (
        ("resume_token", "token_mismatch"),
        ("frame_id", "module_mismatch"),
        ("module_id", "module_mismatch"),
        ("module_type", "module_mismatch"),
        ("module_cursor", "module_cursor_mismatch"),
    ):
        expected = str(prompt.get(field) or "").strip()
        actual = str(decision.get(field) or "").strip()
        if expected and actual and actual != expected:
            return reason
    return ""


def _module_command_continuation_fields(prompt: dict, decision: dict) -> dict:
    if not _is_module_prompt(prompt):
        return {}
    fields: dict[str, object] = {}
    for field in ("resume_token", "frame_id", "module_id", "module_type", "module_cursor", "batch_id"):
        value = str(decision.get(field) or prompt.get(field) or "").strip()
        if field == "batch_id" and not value:
            value = _derive_batch_id_from_request_id(str(decision.get("request_id") or prompt.get("request_id") or ""))
        if value:
            fields[field] = value
    prompt_instance_id = _int_or_none(decision.get("prompt_instance_id"))
    if prompt_instance_id is None:
        prompt_instance_id = _int_or_none(prompt.get("prompt_instance_id"))
    if prompt_instance_id is not None:
        fields["prompt_instance_id"] = prompt_instance_id
    for field in (
        "missing_player_ids",
        "missing_public_player_ids",
        "missing_seat_ids",
        "missing_viewer_ids",
        "resume_tokens_by_player_id",
        "resume_tokens_by_public_player_id",
        "resume_tokens_by_seat_id",
        "resume_tokens_by_viewer_id",
    ):
        value = decision.get(field)
        if value is None:
            value = prompt.get(field)
        if isinstance(value, (list, dict)):
            fields[field] = value
    return fields


def _derive_batch_id_from_request_id(request_id: str) -> str:
    request_id = str(request_id or "").strip()
    if not request_id.startswith("batch:") or ":p" not in request_id:
        return ""
    batch_id, player_suffix = request_id.rsplit(":p", 1)
    if not player_suffix.isdigit():
        return ""
    return batch_id


def _ensure_prompt_protocol_identity(prompt: dict, *, request_id: str) -> None:
    for key, value in prompt_protocol_identity_fields(
        request_id=request_id,
        prompt_instance_id=prompt.get("prompt_instance_id"),
    ).items():
        prompt.setdefault(key, value)


def _copy_prompt_protocol_identity(source: dict, target: dict) -> None:
    for field in ("legacy_request_id", "public_request_id", "public_prompt_instance_id"):
        value = source.get(field)
        if str(value or "").strip():
            target.setdefault(field, value)


def _copy_prompt_player_identity(source: dict, target: dict) -> None:
    for field in (
        "public_player_id",
        "seat_id",
        "viewer_id",
        "legacy_player_id",
        "seat_index",
        "turn_order_index",
        "player_label",
    ):
        value = source.get(field)
        if str(value or "").strip():
            target.setdefault(field, value)


def _payload_request_alias_matches(payload: dict, request_id: str) -> bool:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        return False
    for field in ("legacy_request_id", "public_request_id"):
        if str(payload.get(field) or "").strip() == normalized_request_id:
            return True
    return False


def _int_or_none(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_prompt_lifecycle_payload(prompt: dict) -> dict[str, Any]:
    legal_choice_ids = [
        str(choice.get("choice_id") or "").strip()
        for choice in prompt.get("legal_choices", [])
        if isinstance(choice, dict) and str(choice.get("choice_id") or "").strip()
    ]
    result: dict[str, Any] = {
        "request_id": str(prompt.get("request_id") or ""),
        "legacy_request_id": str(prompt.get("legacy_request_id") or ""),
        "public_request_id": str(prompt.get("public_request_id") or ""),
        "request_type": str(prompt.get("request_type") or ""),
        "prompt_instance_id": str(prompt.get("prompt_instance_id") or ""),
        "public_prompt_instance_id": str(prompt.get("public_prompt_instance_id") or ""),
        "resume_token": str(prompt.get("resume_token") or ""),
        "frame_id": str(prompt.get("frame_id") or ""),
        "module_id": str(prompt.get("module_id") or ""),
        "module_type": str(prompt.get("module_type") or ""),
        "module_cursor": str(prompt.get("module_cursor") or ""),
        "timeout_ms": int(prompt.get("timeout_ms") or 0),
        "legal_choice_ids": legal_choice_ids,
        "prompt_fingerprint": str(prompt.get("prompt_fingerprint") or ""),
        "prompt_fingerprint_version": prompt.get("prompt_fingerprint_version"),
        "public_context": dict(prompt.get("public_context") or {}),
    }
    return {key: value for key, value in result.items() if value not in ("", None, [], {})}


def _compact_decision_lifecycle_payload(decision: dict) -> dict[str, Any]:
    result: dict[str, Any] = {
        "request_id": str(decision.get("request_id") or ""),
        "submitted_request_id": str(decision.get("submitted_request_id") or ""),
        "legacy_request_id": str(decision.get("legacy_request_id") or ""),
        "public_request_id": str(decision.get("public_request_id") or ""),
        "player_id": decision.get("player_id"),
        "choice_id": str(decision.get("choice_id") or ""),
        "view_commit_seq_seen": decision.get("view_commit_seq_seen"),
        "client_seq": decision.get("client_seq"),
        "provider": str(decision.get("provider") or ""),
        "prompt_instance_id": str(decision.get("prompt_instance_id") or ""),
        "public_prompt_instance_id": str(decision.get("public_prompt_instance_id") or ""),
        "resume_token": str(decision.get("resume_token") or ""),
        "prompt_fingerprint": str(decision.get("prompt_fingerprint") or ""),
    }
    return {key: value for key, value in result.items() if value not in ("", None, [], {})}
