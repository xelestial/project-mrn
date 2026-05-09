from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from apps.server.src.infra.redis_client import RedisConnection
from apps.server.src.services.realtime_persistence import (
    DEBUG_REDIS_RETENTION_SECONDS,
    RedisGameStateStore,
    RedisPromptStore,
    RedisRuntimeStateStore,
    RedisStreamStore,
)


@dataclass(frozen=True)
class RedisStateIssue:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


class RedisStateInspector:
    """Read-only diagnostic view over the Redis game/session state."""

    def __init__(self, connection: RedisConnection) -> None:
        self._connection = connection
        self._game_state = RedisGameStateStore(connection)
        self._prompt_store = RedisPromptStore(connection)
        self._runtime_state = RedisRuntimeStateStore(connection)
        self._stream_store = RedisStreamStore(connection)

    def inspect_session(self, session_id: str, *, now_ms: int | None = None) -> dict[str, Any]:
        normalized_session_id = str(session_id or "").strip()
        generated_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)

        checkpoint = self._game_state.load_checkpoint(normalized_session_id) or {}
        current_state = self._game_state.load_current_state(normalized_session_id) or {}
        view_state = self._game_state.load_view_state(normalized_session_id) or {}
        debug_snapshot = self._game_state.load_debug_snapshot(normalized_session_id) or {}
        view_commit_index = self._game_state.load_view_commit_index(normalized_session_id) or {}
        runtime_status = self._runtime_state.load_status(normalized_session_id) or {}
        lease_owner = self._runtime_state.lease_owner(normalized_session_id)
        fallbacks = self._runtime_state.recent_fallbacks(normalized_session_id, limit=10)

        pending_prompts = self._session_prompts(self._prompt_store.list_pending(), normalized_session_id)
        resolved_prompts = self._session_resolved_prompts(normalized_session_id)
        lifecycle_prompts = self._prompt_store.list_lifecycle(normalized_session_id)
        prompt_index = {
            str(prompt.get("request_id") or ""): prompt
            for prompt in [*pending_prompts, *resolved_prompts, *lifecycle_prompts]
            if str(prompt.get("request_id") or "").strip()
        }
        active_prompt = self._active_prompt(checkpoint, current_state, runtime_status, view_commit_index, normalized_session_id)
        active_request_ids = self._active_request_ids(checkpoint, current_state, runtime_status, view_commit_index, normalized_session_id)
        view_commits = self._view_commits(normalized_session_id, view_commit_index)
        outbox_rows = self._stream_store.load_viewer_outbox_index(normalized_session_id)

        issues = self._issues(
            session_id=normalized_session_id,
            checkpoint=checkpoint,
            view_commit_index=view_commit_index,
            view_commits=view_commits,
            runtime_status=runtime_status,
            lease_owner=lease_owner,
            pending_prompts=pending_prompts,
            lifecycle_prompts=lifecycle_prompts,
            prompt_index=prompt_index,
            active_request_ids=active_request_ids,
            outbox_rows=outbox_rows,
        )
        issue_dicts = [issue.as_dict() for issue in issues]
        diagnostic_status = self._diagnostic_status(issue_dicts)
        latest_commit_seq = self._latest_commit_seq(checkpoint, view_commit_index)
        latest_source_event_seq = self._latest_source_event_seq(checkpoint, view_commit_index)
        runtime = self._runtime_summary(runtime_status, active_prompt)
        round_index = self._first_int(
            runtime_status.get("round_index"),
            checkpoint.get("round_index"),
            current_state.get("round_index"),
            view_commit_index.get("round_index"),
        )
        turn_index = self._first_int(
            runtime_status.get("turn_index"),
            checkpoint.get("turn_index"),
            current_state.get("turn_index"),
            view_commit_index.get("turn_index"),
        )
        turn_label = str(runtime_status.get("turn_label") or checkpoint.get("turn_label") or f"R{round_index}-T{turn_index}")

        return {
            "schema_version": 1,
            "session_id": normalized_session_id,
            "generated_at_ms": generated_at_ms,
            "summary": {
                "diagnostic_status": diagnostic_status,
                "runtime_status": str(runtime_status.get("status") or checkpoint.get("runtime_status") or checkpoint.get("latest_event_type") or ""),
                "round_index": round_index,
                "turn_index": turn_index,
                "turn_label": turn_label,
                "current_player_id": self._first_int(
                    runtime_status.get("current_player_id"),
                    current_state.get("current_player_id"),
                    current_state.get("acting_player_id"),
                    active_prompt.get("player_id"),
                    checkpoint.get("waiting_prompt_player_id"),
                ),
                "latest_seq": self._int_or_default(checkpoint.get("latest_seq"), 0),
                "latest_event_type": checkpoint.get("latest_event_type"),
                "latest_commit_seq": latest_commit_seq,
                "latest_source_event_seq": latest_source_event_seq,
                "waiting_prompt_request_id": self._first_text(
                    checkpoint.get("waiting_prompt_request_id"),
                    active_prompt.get("request_id"),
                ),
                "waiting_prompt_player_id": self._first_int(
                    checkpoint.get("waiting_prompt_player_id"),
                    active_prompt.get("player_id"),
                ),
                "waiting_prompt_type": self._first_text(
                    checkpoint.get("waiting_prompt_type"),
                    active_prompt.get("request_type"),
                ),
                "runtime_lease_owner": lease_owner,
                "pending_prompt_count": len(pending_prompts),
                "lifecycle_prompt_count": len(lifecycle_prompts),
                "viewer_commit_count": len(view_commits["viewers"]),
                "viewer_outbox_count": len(outbox_rows),
            },
            "state": {
                "checkpoint": self._compact_mapping(
                    checkpoint,
                    (
                        "schema_version",
                        "latest_seq",
                        "latest_event_type",
                        "latest_commit_seq",
                        "latest_source_event_seq",
                        "round_index",
                        "turn_index",
                        "has_view_commit",
                        "waiting_prompt_request_id",
                        "waiting_prompt_player_id",
                        "waiting_prompt_type",
                        "frame_id",
                        "module_id",
                        "module_type",
                        "module_cursor",
                    ),
                ),
                "runtime": runtime,
                "lease": {"owner": lease_owner, "recent_fallbacks": fallbacks},
                "players": self._compact_players(current_state, view_state),
                "board": self._compact_board(current_state, view_state),
                "debug_snapshot_summary": self._compact_mapping(
                    debug_snapshot.get("summary") if isinstance(debug_snapshot.get("summary"), dict) else {},
                    (
                        "status",
                        "round_index",
                        "turn_index",
                        "current_player_id",
                        "latest_seq",
                        "latest_commit_seq",
                        "waiting_prompt_request_id",
                    ),
                ),
            },
            "prompts": {
                "active_request_ids": sorted(active_request_ids),
                "pending": [self._compact_prompt(prompt) for prompt in pending_prompts],
                "resolved": [self._compact_prompt(prompt) for prompt in resolved_prompts],
                "lifecycle": [self._compact_prompt(prompt) for prompt in lifecycle_prompts],
            },
            "view_commits": view_commits,
            "outbox": {
                "retention_seconds": DEBUG_REDIS_RETENTION_SECONDS,
                "count": len(outbox_rows),
                "latest": [self._compact_outbox(row) for row in outbox_rows[-40:]],
            },
            "issues": issue_dicts,
            "recommendations": self._recommendations(issue_dicts),
            "raw_keys": self._raw_key_map(normalized_session_id),
        }

    def _issues(
        self,
        *,
        session_id: str,
        checkpoint: dict[str, Any],
        view_commit_index: dict[str, Any],
        view_commits: dict[str, Any],
        runtime_status: dict[str, Any],
        lease_owner: str | None,
        pending_prompts: list[dict[str, Any]],
        lifecycle_prompts: list[dict[str, Any]],
        prompt_index: dict[str, dict[str, Any]],
        active_request_ids: set[str],
        outbox_rows: list[dict[str, Any]],
    ) -> list[RedisStateIssue]:
        issues: list[RedisStateIssue] = []
        if not checkpoint:
            issues.append(
                RedisStateIssue(
                    code="missing_checkpoint",
                    severity="critical",
                    message="Redis checkpoint가 없어 현재 세션 상태를 권위적으로 복원할 수 없습니다.",
                    evidence={"session_id": session_id},
                )
            )
            return issues

        runtime_state = str(runtime_status.get("status") or "").strip().lower()
        if runtime_state == "failed":
            issues.append(
                RedisStateIssue(
                    code="runtime_failed",
                    severity="critical",
                    message="서버 런타임이 failed 상태입니다.",
                    evidence=self._compact_mapping(
                        runtime_status,
                        (
                            "status",
                            "error",
                            "exception_class",
                            "exception_repr",
                            "traceback",
                            "round_index",
                            "turn_index",
                            "turn_label",
                            "active_frame_id",
                            "active_module_id",
                            "active_module_type",
                        ),
                    ),
                )
            )

        checkpoint_commit_seq = self._int_or_default(checkpoint.get("latest_commit_seq"), 0)
        index_commit_seq = self._int_or_default(view_commit_index.get("latest_commit_seq"), 0)
        if bool(checkpoint.get("has_view_commit")) and not view_commit_index:
            issues.append(
                RedisStateIssue(
                    code="missing_view_commit_index",
                    severity="warning",
                    message="checkpoint는 view_commit 존재를 표시하지만 view_commit_index가 없습니다.",
                    evidence={"checkpoint_latest_commit_seq": checkpoint_commit_seq},
                )
            )
        elif checkpoint_commit_seq and index_commit_seq and checkpoint_commit_seq != index_commit_seq:
            issues.append(
                RedisStateIssue(
                    code="checkpoint_commit_seq_mismatch",
                    severity="critical",
                    message="checkpoint와 view_commit_index의 latest_commit_seq가 다릅니다.",
                    evidence={
                        "checkpoint_latest_commit_seq": checkpoint_commit_seq,
                        "index_latest_commit_seq": index_commit_seq,
                    },
                )
            )

        latest_commit_seq = max(checkpoint_commit_seq, index_commit_seq)
        stale_viewers = [
            {"label": viewer.get("label"), "commit_seq": viewer.get("commit_seq")}
            for viewer in view_commits.get("viewers", [])
            if self._int_or_default(viewer.get("commit_seq"), 0) and self._int_or_default(viewer.get("commit_seq"), 0) < latest_commit_seq
        ]
        if stale_viewers:
            issues.append(
                RedisStateIssue(
                    code="viewer_commit_stale",
                    severity="warning",
                    message="일부 viewer view_commit이 최신 commit_seq보다 오래됐습니다.",
                    evidence={"latest_commit_seq": latest_commit_seq, "stale_viewers": stale_viewers},
                )
            )

        waiting_state = (
            runtime_state in {"waiting_input", "prompt_required", "suspended"}
            or str(checkpoint.get("latest_event_type") or "").strip() == "prompt_required"
            or bool(str(checkpoint.get("waiting_prompt_request_id") or "").strip())
        )
        pending_ids = {str(prompt.get("request_id") or "") for prompt in pending_prompts if str(prompt.get("request_id") or "").strip()}
        for request_id in sorted(active_request_ids):
            if request_id in pending_ids:
                continue
            if waiting_state:
                issues.append(
                    RedisStateIssue(
                        code="waiting_prompt_missing_pending",
                        severity="critical",
                        message="런타임/체크포인트가 active prompt를 가리키지만 pending prompt가 없습니다.",
                        evidence={"request_id": request_id, "runtime_status": runtime_state},
                    )
                )
            elif request_id not in prompt_index:
                issues.append(
                    RedisStateIssue(
                        code="active_prompt_missing_record",
                        severity="warning",
                        message="active prompt request_id를 pending/resolved/lifecycle에서 찾을 수 없습니다.",
                        evidence={"request_id": request_id, "runtime_status": runtime_state},
                    )
                )

        for prompt in pending_prompts:
            request_id = str(prompt.get("request_id") or "").strip()
            if request_id and request_id not in active_request_ids:
                issues.append(
                    RedisStateIssue(
                        code="pending_prompt_without_runtime_wait",
                        severity="warning",
                        message="pending prompt가 있지만 runtime/checkpoint/view_commit active prompt와 연결되지 않습니다.",
                        evidence={
                            "request_id": request_id,
                            "player_id": prompt.get("player_id"),
                            "request_type": prompt.get("request_type"),
                        },
                    )
                )

        if runtime_state in {"running", "processing", "in_progress"} and not lease_owner:
            issues.append(
                RedisStateIssue(
                    code="lease_missing_for_running_runtime",
                    severity="warning",
                    message="running 계열 runtime status인데 lease owner가 없습니다.",
                    evidence={"runtime_status": runtime_state},
                )
            )

        if latest_commit_seq and not any(self._int_or_default(row.get("commit_seq"), 0) == latest_commit_seq for row in outbox_rows):
            issues.append(
                RedisStateIssue(
                    code="viewer_outbox_missing_latest_commit",
                    severity="warning",
                    message="viewer outbox에서 최신 commit_seq 전달 기록을 찾지 못했습니다. TTL 만료일 수도 있습니다.",
                    evidence={"latest_commit_seq": latest_commit_seq, "retention_seconds": DEBUG_REDIS_RETENTION_SECONDS},
                )
            )

        for viewer_commit in view_commits.get("viewers", []):
            if not isinstance(viewer_commit, dict):
                continue
            commit_seq = self._int_or_default(viewer_commit.get("commit_seq"), 0)
            if not commit_seq:
                continue
            expected_scope = self._viewer_scope_for_commit(viewer_commit)
            if not expected_scope:
                continue
            matched = any(
                str(row.get("message_type") or "") == "view_commit"
                and self._int_or_default(row.get("commit_seq"), 0) == commit_seq
                and str(row.get("viewer_scope") or "") == expected_scope
                for row in outbox_rows
            )
            if matched:
                continue
            issues.append(
                RedisStateIssue(
                    code="viewer_commit_outbox_missing",
                    severity="critical",
                    message="viewer별 view_commit은 존재하지만 해당 viewer outbox 전달 기록이 없습니다.",
                    evidence={
                        "viewer_label": viewer_commit.get("label"),
                        "expected_scope": expected_scope,
                        "commit_seq": commit_seq,
                    },
                )
            )

        lifecycle_by_request_id = {
            str(prompt.get("request_id") or ""): prompt
            for prompt in lifecycle_prompts
            if str(prompt.get("request_id") or "").strip()
        }
        for prompt in pending_prompts:
            request_id = str(prompt.get("request_id") or "").strip()
            if not request_id:
                continue
            lifecycle = lifecycle_by_request_id.get(request_id)
            if not lifecycle:
                issues.append(
                    RedisStateIssue(
                        code="pending_prompt_missing_lifecycle",
                        severity="warning",
                        message="pending prompt가 있지만 lifecycle 레코드가 없습니다.",
                        evidence={
                            "request_id": request_id,
                            "player_id": prompt.get("player_id"),
                            "request_type": prompt.get("request_type"),
                        },
                    )
                )
                continue
            lifecycle_state = str(lifecycle.get("state") or "").strip().lower()
            if lifecycle_state not in {"delivered", "decision_received", "accepted", "rejected", "stale", "resolved"}:
                continue
            player_id = self._int_or_default(prompt.get("player_id") or lifecycle.get("player_id"), 0)
            expected_scope = f"player:{player_id}" if player_id > 0 else ""
            if not expected_scope:
                continue
            matched = any(
                str(row.get("message_type") or "") == "prompt"
                and str(row.get("request_id") or "") == request_id
                and str(row.get("viewer_scope") or "") == expected_scope
                for row in outbox_rows
            )
            if matched:
                continue
            issues.append(
                RedisStateIssue(
                    code="prompt_delivery_outbox_missing",
                    severity="critical",
                    message="prompt lifecycle은 delivered 이후 상태인데 대상 player outbox 전달 기록이 없습니다.",
                    evidence={
                        "request_id": request_id,
                        "player_id": player_id,
                        "expected_scope": expected_scope,
                        "lifecycle_state": lifecycle_state,
                    },
                )
            )

        return issues

    def _viewer_scope_for_commit(self, viewer_commit: dict[str, Any]) -> str:
        label = str(viewer_commit.get("label") or "").strip().lower()
        if label.startswith("player:"):
            return label
        if label.startswith("seat:"):
            return f"player:{label.split(':', 1)[1]}"
        viewer = viewer_commit.get("viewer") if isinstance(viewer_commit.get("viewer"), dict) else {}
        role = str(viewer.get("role") or label).strip().lower()
        if role in {"seat", "player"}:
            player_id = self._int_or_default(viewer.get("player_id"), 0)
            return f"player:{player_id}" if player_id > 0 else ""
        if role in {"spectator", "admin", "public"}:
            return role
        return label if label in {"spectator", "admin", "public"} else ""

    def _view_commits(self, session_id: str, index: dict[str, Any]) -> dict[str, Any]:
        labels = []
        raw_labels = index.get("view_commit_viewers")
        if isinstance(raw_labels, list):
            labels.extend(str(label) for label in raw_labels)
        if not labels:
            labels = ["spectator", "public", "admin"]
        viewers = []
        for label in sorted(set(labels)):
            payload = self._load_view_commit_for_label(session_id, label)
            if payload is None:
                continue
            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
            active_prompt = runtime.get("active_prompt") if isinstance(runtime.get("active_prompt"), dict) else {}
            viewers.append(
                {
                    "label": label,
                    "commit_seq": self._int_or_default(payload.get("commit_seq"), 0),
                    "source_event_seq": self._int_or_default(payload.get("source_event_seq"), 0),
                    "viewer": self._compact_mapping(
                        payload.get("viewer") if isinstance(payload.get("viewer"), dict) else {},
                        ("role", "player_id", "seat", "viewer_id"),
                    ),
                    "runtime": self._compact_mapping(
                        runtime,
                        (
                            "status",
                            "round_index",
                            "turn_index",
                            "turn_label",
                            "current_player_id",
                            "active_frame_id",
                            "active_module_id",
                            "active_module_type",
                            "active_module_cursor",
                        ),
                    ),
                    "active_prompt": self._compact_prompt(active_prompt),
                }
            )
        return {
            "latest_commit_seq": self._int_or_default(index.get("latest_commit_seq"), 0),
            "latest_source_event_seq": self._int_or_default(index.get("latest_source_event_seq"), 0),
            "viewer_labels": sorted(set(labels)),
            "viewers": viewers,
        }

    def _load_view_commit_for_label(self, session_id: str, label: str) -> dict[str, Any] | None:
        normalized = str(label or "").strip().lower()
        if normalized.startswith("seat:"):
            normalized = f"player:{normalized.split(':', 1)[1]}"
        if normalized.startswith("player:"):
            try:
                player_id = int(normalized.split(":", 1)[1])
            except (TypeError, ValueError):
                return None
            return self._game_state.load_view_commit(session_id, "player", player_id=player_id)
        if normalized in {"public", "spectator", "admin"}:
            return self._game_state.load_view_commit(session_id, normalized)
        return None

    def _active_prompt(
        self,
        checkpoint: dict[str, Any],
        current_state: dict[str, Any],
        runtime_status: dict[str, Any],
        view_commit_index: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        for candidate in (
            runtime_status.get("active_prompt"),
            current_state.get("runtime_active_prompt"),
            checkpoint.get("runtime_active_prompt"),
        ):
            if isinstance(candidate, dict) and candidate.get("request_id"):
                return candidate
        for viewer in self._view_commits(session_id, view_commit_index).get("viewers", []):
            active_prompt = viewer.get("active_prompt")
            if isinstance(active_prompt, dict) and active_prompt.get("request_id"):
                return active_prompt
        if checkpoint.get("waiting_prompt_request_id"):
            return {
                "request_id": checkpoint.get("waiting_prompt_request_id"),
                "player_id": checkpoint.get("waiting_prompt_player_id"),
                "request_type": checkpoint.get("waiting_prompt_type"),
            }
        return {}

    def _active_request_ids(
        self,
        checkpoint: dict[str, Any],
        current_state: dict[str, Any],
        runtime_status: dict[str, Any],
        view_commit_index: dict[str, Any],
        session_id: str,
    ) -> set[str]:
        request_ids: set[str] = set()
        for value in (
            checkpoint.get("waiting_prompt_request_id"),
            checkpoint.get("decision_resume_request_id"),
        ):
            text = str(value or "").strip()
            if text:
                request_ids.add(text)
        for payload in (checkpoint, current_state, runtime_status):
            self._collect_request_ids(payload.get("runtime_active_prompt"), request_ids)
            self._collect_request_ids(payload.get("runtime_active_prompt_batch"), request_ids)
            self._collect_request_ids(payload.get("active_prompt"), request_ids)
        for viewer in self._view_commits(session_id, view_commit_index).get("viewers", []):
            self._collect_request_ids(viewer.get("active_prompt"), request_ids)
        return request_ids

    def _collect_request_ids(self, value: Any, sink: set[str]) -> None:
        if isinstance(value, dict):
            request_id = str(value.get("request_id") or "").strip()
            if request_id:
                sink.add(request_id)
            prompts = value.get("prompts_by_player_id")
            if isinstance(prompts, dict):
                for prompt in prompts.values():
                    self._collect_request_ids(prompt, sink)
            prompts_list = value.get("prompts")
            if isinstance(prompts_list, list):
                for prompt in prompts_list:
                    self._collect_request_ids(prompt, sink)
        elif isinstance(value, list):
            for item in value:
                self._collect_request_ids(item, sink)

    def _session_prompts(self, prompts: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        return [prompt for prompt in prompts if str(prompt.get("session_id") or "").strip() == session_id]

    def _session_resolved_prompts(self, session_id: str) -> list[dict[str, Any]]:
        result = []
        for prompt in self._prompt_store.list_resolved().values():
            if str(prompt.get("session_id") or "").strip() == session_id:
                result.append(prompt)
        result.sort(key=lambda item: str(item.get("request_id") or ""))
        return result

    def _runtime_summary(self, runtime_status: dict[str, Any], active_prompt: dict[str, Any]) -> dict[str, Any]:
        return {
            **self._compact_mapping(
                runtime_status,
                (
                    "status",
                    "round_index",
                    "turn_index",
                    "turn_label",
                    "current_player_id",
                    "active_frame_id",
                    "active_module_id",
                    "active_module_type",
                    "active_module_cursor",
                    "exception_class",
                    "exception_repr",
                    "error",
                ),
            ),
            "active_prompt": self._compact_prompt(active_prompt),
        }

    def _raw_key_map(self, session_id: str) -> dict[str, str]:
        return {
            "checkpoint": self._connection.key("game", session_id, "checkpoint"),
            "current_state": self._connection.key("game", session_id, "current_state"),
            "view_state_public": self._connection.key("game", session_id, "view_state"),
            "view_commit_index": self._connection.key("game", session_id, "view_commit_index"),
            "debug_snapshot": self._connection.key("game", session_id, "debug_snapshot"),
            "stream_events": self._connection.key("stream", session_id, "events"),
            "stream_source_events": self._connection.key("stream", session_id, "source_events"),
            "stream_seq": self._connection.key("stream", session_id, "seq"),
            "stream_event_index": self._connection.key("stream", session_id, "event_index"),
            "stream_viewer_outbox": self._connection.key("stream", session_id, "viewer_outbox"),
            "commands_stream": self._connection.key("commands", session_id, "stream"),
            "commands_seq": self._connection.key("commands", session_id, "seq"),
            "commands_seen": self._connection.key("commands", "seen"),
            "prompts_pending_hash": self._connection.key("prompts", "pending"),
            "prompts_resolved_hash": self._connection.key("prompts", "resolved"),
            "prompts_decisions_hash": self._connection.key("prompts", "decisions"),
            "prompts_lifecycle_hash": self._connection.key("prompts", "lifecycle"),
            "prompts_debug_index": self._connection.key("prompts", session_id, "debug_index"),
            "runtime_status_hash": self._connection.key("runtime", "status"),
            "runtime_fallbacks": self._connection.key("runtime", session_id, "fallbacks"),
            "runtime_lease": self._connection.key("runtime", session_id, "lease"),
        }

    def _recommendations(self, issues: list[dict[str, Any]]) -> list[str]:
        if not issues:
            return []
        by_code = {str(issue.get("code") or "") for issue in issues}
        recommendations: list[str] = []
        if "runtime_failed" in by_code:
            recommendations.append("runtime status의 exception_class/exception_repr/traceback을 기준으로 서버 런타임 fixture를 먼저 고정하십시오.")
        if "checkpoint_commit_seq_mismatch" in by_code or "viewer_commit_stale" in by_code:
            recommendations.append("view_commit 생성 경로와 checkpoint commit_transition 원자성을 우선 확인하십시오.")
        if "waiting_prompt_missing_pending" in by_code or "pending_prompt_without_runtime_wait" in by_code:
            recommendations.append("PromptService lifecycle과 RuntimeService active prompt 저장 시점을 비교하십시오.")
        if "viewer_outbox_missing_latest_commit" in by_code:
            recommendations.append("outbox TTL 만료가 아니라면 WebSocket publish/projection 경로가 최신 view_commit을 기록했는지 확인하십시오.")
        if "missing_checkpoint" in by_code:
            recommendations.append("세션 id가 맞는지 확인하고, current_state/checkpoint 저장 전에 세션이 삭제됐는지 확인하십시오.")
        return recommendations

    @staticmethod
    def _compact_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
        compact = RedisStateInspector._compact_mapping(
            prompt,
            (
                "request_id",
                "prompt_instance_id",
                "request_type",
                "player_id",
                "state",
                "reason",
                "view_commit_seq",
                "view_commit_seq_seen",
                "resume_token",
                "timeout_ms",
                "created_at_ms",
                "expires_at_ms",
            ),
        )
        choices = prompt.get("legal_choices")
        if isinstance(choices, list):
            compact["legal_choice_count"] = len(choices)
        return compact

    @staticmethod
    def _compact_outbox(row: dict[str, Any]) -> dict[str, Any]:
        return RedisStateInspector._compact_mapping(
            row,
            (
                "session_id",
                "viewer_scope",
                "stream_seq",
                "message_type",
                "event_id",
                "request_id",
                "player_id",
                "target_player_id",
                "commit_seq",
                "server_time_ms",
            ),
        )

    @staticmethod
    def _compact_players(current_state: dict[str, Any], view_state: dict[str, Any]) -> list[dict[str, Any]]:
        players = current_state.get("players")
        if not isinstance(players, list):
            players = view_state.get("players")
        if isinstance(players, dict) and isinstance(players.get("items"), list):
            players = players.get("items")
        if not isinstance(players, list):
            return []
        return [
            RedisStateInspector._compact_mapping(
                player if isinstance(player, dict) else {},
                (
                    "player_id",
                    "id",
                    "seat",
                    "name",
                    "display_name",
                    "character",
                    "character_id",
                    "alive",
                    "position",
                    "tile_index",
                    "money",
                    "cash",
                    "coins",
                    "points",
                    "score",
                    "shards",
                    "lap_count",
                    "rank",
                    "bankrupt",
                ),
            )
            for player in players[:8]
            if isinstance(player, dict)
        ]

    @staticmethod
    def _compact_board(current_state: dict[str, Any], view_state: dict[str, Any]) -> dict[str, Any]:
        board = current_state.get("board")
        if not isinstance(board, dict):
            board = view_state.get("board")
        if not isinstance(board, dict):
            return {}
        compact = RedisStateInspector._compact_mapping(
            board,
            ("round_index", "turn_index", "f_value", "end_time", "weather", "lap", "tile_count"),
        )
        tiles = board.get("tiles")
        if isinstance(tiles, list):
            compact["tile_count"] = len(tiles)
        return compact

    @staticmethod
    def _compact_mapping(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: payload[key] for key in keys if key in payload and payload[key] is not None}

    @staticmethod
    def _diagnostic_status(issues: list[dict[str, Any]]) -> str:
        if any(str(issue.get("severity") or "") == "critical" for issue in issues):
            return "critical"
        if issues:
            return "warning"
        return "ok"

    @staticmethod
    def _latest_commit_seq(checkpoint: dict[str, Any], index: dict[str, Any]) -> int:
        return max(
            RedisStateInspector._int_or_default(checkpoint.get("latest_commit_seq"), 0),
            RedisStateInspector._int_or_default(index.get("latest_commit_seq"), 0),
        )

    @staticmethod
    def _latest_source_event_seq(checkpoint: dict[str, Any], index: dict[str, Any]) -> int:
        return max(
            RedisStateInspector._int_or_default(checkpoint.get("latest_source_event_seq"), 0),
            RedisStateInspector._int_or_default(index.get("latest_source_event_seq"), 0),
        )

    @staticmethod
    def _first_int(*values: Any) -> int:
        for value in values:
            parsed = RedisStateInspector._int_or_none(value)
            if parsed is not None:
                return parsed
        return 0

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _int_or_default(value: Any, default: int) -> int:
        parsed = RedisStateInspector._int_or_none(value)
        return default if parsed is None else parsed

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
