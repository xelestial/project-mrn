from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from apps.server.src.domain.session_models import SessionStatus, utc_now_iso
from apps.server.src.infra.structured_log import log_event


class LocalJsonArchiveService:
    def __init__(
        self,
        *,
        session_service,
        stream_service,
        archive_dir: str,
        hot_retention_seconds: int = 300,
        room_service=None,
        prompt_service=None,
        runtime_service=None,
        game_state_store=None,
        command_store=None,
        redis_key_prefix: str = "",
        service_version: str = "dev",
    ) -> None:
        self._session_service = session_service
        self._stream_service = stream_service
        self._room_service = room_service
        self._prompt_service = prompt_service
        self._runtime_service = runtime_service
        self._game_state_store = game_state_store
        self._command_store = command_store
        self._archive_dir = Path(archive_dir)
        self._hot_retention_seconds = max(0, int(hot_retention_seconds))
        self._redis_key_prefix = str(redis_key_prefix or "")
        self._service_version = str(service_version or "dev")
        self._cleanup_tasks: dict[str, asyncio.Task] = {}

    async def handle_session_finished(self, session_id: str) -> None:
        try:
            session = self._session_service.get_session(session_id)
        except Exception:
            return
        if session.status not in {SessionStatus.FINISHED, SessionStatus.ABORTED}:
            return
        room = self._resolve_room(session_id)
        stream_messages = [message.to_dict() for message in await self._stream_service.snapshot(session_id)]
        exported_at = utc_now_iso()
        payload = self._build_archive_payload(
            session=session,
            room=room,
            stream_messages=stream_messages,
            exported_at=exported_at,
        )
        await asyncio.to_thread(self._write_archive, session_id, payload)
        log_event(
            "session_archive_written",
            session_id=session_id,
            archive_path=str(self.archive_path_for(session_id)),
            event_count=payload["counts"]["event_count"],
        )
        self._schedule_cleanup(session_id)

    def archive_path_for(self, session_id: str) -> Path:
        return self._archive_dir / f"{session_id}.json"

    def _schedule_cleanup(self, session_id: str) -> None:
        existing = self._cleanup_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        self._cleanup_tasks[session_id] = asyncio.create_task(
            self._cleanup_after_retention(session_id),
            name=f"archive_cleanup:{session_id}",
        )

    async def _cleanup_after_retention(self, session_id: str) -> None:
        if self._hot_retention_seconds > 0:
            await asyncio.sleep(self._hot_retention_seconds)
        await self._stream_service.delete_session_data(session_id)
        if self._prompt_service is not None:
            self._prompt_service.delete_session_data(session_id)
        if self._runtime_service is not None:
            self._runtime_service.delete_session_data(session_id)
        if self._game_state_store is not None:
            self._game_state_store.delete_session_data(session_id)
        self._session_service.delete_session(session_id)
        log_event(
            "session_archive_cleanup_completed",
            session_id=session_id,
            hot_retention_seconds=self._hot_retention_seconds,
        )

    def _resolve_room(self, session_id: str):
        if self._room_service is None:
            return None
        try:
            return self._room_service.find_room_for_session(session_id)
        except Exception:
            return None

    def _build_archive_payload(
        self,
        *,
        session,
        room,
        stream_messages: list[dict[str, Any]],
        exported_at: str,
    ) -> dict[str, Any]:
        runtime = dict(session.resolved_parameters.get("runtime", {}))
        seed = runtime.get("seed", session.config.get("seed"))
        policy_mode = runtime.get("policy_mode")
        commands = self._load_command_stream(session.session_id, stream_messages)
        analysis = [self._stream_entry_payload(message) for message in stream_messages if message.get("type") == "analysis"]
        events = [
            self._stream_entry_payload(message)
            for message in stream_messages
            if message.get("type") not in {"command", "analysis"}
        ]
        source_events = [entry for entry in events if entry.get("type") != "view_commit"]
        view_commits = [entry for entry in events if entry.get("type") == "view_commit"]
        final_view_state = self._load_final_view_state(session.session_id, stream_messages)
        final_state = self._load_final_state(session.session_id)
        room_no = getattr(room, "room_no", None)
        room_title = getattr(room, "room_title", None)
        player_results = []
        for seat in session.seats:
            if seat.player_id is None:
                continue
            player_results.append(
                {
                    "player_id": int(seat.player_id),
                    "display_name": seat.display_name or f"Player {seat.player_id}",
                    "seat": int(seat.seat),
                }
            )
        stored_checkpoint = self._load_final_checkpoint(session.session_id)
        latest_stream_seq = max((int(message.get("seq", 0)) for message in stream_messages), default=0)
        latest_stream_time_ms = max((int(message.get("server_time_ms", 0)) for message in stream_messages), default=0)
        return {
            "schema_version": 1,
            "schema_name": "mrn.canonical_archive",
            "visibility": "backend_canonical",
            "browser_safe": False,
            "exported_at": exported_at,
            "exporter": {
                "kind": "backend_local_json",
                "service_version": self._service_version,
                "redis_prefix": self._redis_key_prefix,
            },
            "session": {
                "session_id": session.session_id,
                "room_no": room_no,
                "room_title": room_title,
                "status": session.status.value,
                "created_at": session.created_at,
                "started_at": session.started_at,
                "finished_at": exported_at,
                "seed": seed,
                "policy_mode": policy_mode,
            },
            "manifest": dict(session.parameter_manifest),
            "summary": {
                "round_index": int(session.round_index),
                "turn_index": int(session.turn_index),
                "abort_reason": session.abort_reason,
                "player_results": player_results,
            },
            "final_checkpoint": stored_checkpoint or {
                "engine_seq": latest_stream_seq,
                "schema_version": 1,
                "turn": int(session.turn_index),
                "round": int(session.round_index),
                "latest_stream_time_ms": latest_stream_time_ms,
            },
            "final_state": final_state,
            "final_view_state": final_view_state,
            "streams": {
                "commands": commands,
                "events": events,
                "analysis": analysis,
            },
            "counts": {
                "command_count": len(commands),
                "event_count": len(source_events),
                "view_commit_count": len(view_commits),
                "stream_message_count": len(commands) + len(events) + len(analysis),
                "analysis_count": len(analysis),
            },
        }

    @staticmethod
    def _stream_entry_payload(message: dict[str, Any]) -> dict[str, Any]:
        seq = int(message.get("seq", 0))
        server_time_ms = int(message.get("server_time_ms", 0))
        return {
            "stream_id": f"{server_time_ms}-{seq}",
            "seq": seq,
            "type": str(message.get("type", "event")),
            "server_time_ms": server_time_ms,
            "payload": dict(message.get("payload", {})),
        }

    @staticmethod
    def _latest_view_state(messages: list[dict[str, Any]]) -> dict[str, Any]:
        for message in reversed(messages):
            payload = message.get("payload")
            if not isinstance(payload, dict):
                continue
            view_state = payload.get("view_state")
            if isinstance(view_state, dict):
                return dict(view_state)
        return {}

    def _load_final_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        if self._game_state_store is None:
            return None
        try:
            return self._game_state_store.load_checkpoint(session_id)
        except Exception:
            return None

    def _load_final_state(self, session_id: str) -> dict[str, Any]:
        if self._game_state_store is not None:
            try:
                current_state = self._game_state_store.load_current_state(session_id)
            except Exception:
                current_state = None
            if isinstance(current_state, dict):
                return current_state
        return self._sanitize_session_payload(self._session_service.to_persisted_payload(session_id))

    def _load_final_view_state(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if self._game_state_store is not None:
            try:
                view_commit = self._game_state_store.load_view_commit(session_id, "spectator")
            except Exception:
                view_commit = None
            if isinstance(view_commit, dict) and isinstance(view_commit.get("view_state"), dict):
                return dict(view_commit["view_state"])
            try:
                view_state = self._game_state_store.load_view_state(session_id)
            except Exception:
                view_state = None
            if isinstance(view_state, dict):
                return view_state
            try:
                view_state = self._game_state_store.load_projected_view_state(session_id, "public")
            except Exception:
                view_state = None
            if isinstance(view_state, dict):
                return view_state
            try:
                view_commit = self._game_state_store.load_view_commit(session_id, "admin")
            except Exception:
                view_commit = None
            if isinstance(view_commit, dict) and isinstance(view_commit.get("view_state"), dict):
                return dict(view_commit["view_state"])
        return self._latest_view_state(messages)

    def _load_command_stream(self, session_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._command_store is not None:
            try:
                return [self._stream_entry_payload(message) for message in self._command_store.list_commands(session_id)]
            except Exception:
                pass
        return [self._stream_entry_payload(message) for message in messages if message.get("type") == "command"]

    @staticmethod
    def _sanitize_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(payload)
        sanitized["host_token"] = ""
        sanitized["join_tokens"] = {}
        sanitized["session_tokens"] = {}
        return sanitized

    def _write_archive(self, session_id: str, payload: dict[str, Any]) -> None:
        target = self.archive_path_for(session_id)
        tmp_target = target.with_suffix(f"{target.suffix}.tmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tmp_target.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_target, target)
