from __future__ import annotations

import copy


class CommandBoundaryGameStateStore:
    """Defers transition commits inside one user command until the terminal boundary."""

    defer_authoritative_transition_commit = True

    def __init__(self, delegate: object, *, session_id: str, base_commit_seq: int) -> None:
        self._delegate = delegate
        self._session_id = str(session_id)
        self._base_commit_seq = int(base_commit_seq)
        self._current_state: dict | None = None
        self._checkpoint: dict | None = None
        self._view_state: dict | None = None
        self._view_commits: dict[str, dict] | None = None
        self._deferred_commit: dict | None = None
        self.internal_state_stage_count = 0
        self.redis_commit_count = 0
        self.view_commit_count = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def stage_internal_transition(self, session_id: str, *, current_state: dict) -> None:
        if str(session_id) != self._session_id:
            return
        self._current_state = copy.deepcopy(current_state)
        self.internal_state_stage_count += 1

    def load_current_state(self, session_id: str) -> dict | None:
        if str(session_id) == self._session_id and isinstance(self._current_state, dict):
            return copy.deepcopy(self._current_state)
        loaded = self._delegate.load_current_state(session_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def load_checkpoint(self, session_id: str) -> dict | None:
        if str(session_id) == self._session_id and isinstance(self._checkpoint, dict):
            checkpoint = copy.deepcopy(self._checkpoint)
            checkpoint["latest_commit_seq"] = self._base_commit_seq
            checkpoint["base_commit_seq"] = min(
                int(checkpoint.get("base_commit_seq") or self._base_commit_seq),
                self._base_commit_seq,
            )
            return checkpoint
        loaded = self._delegate.load_checkpoint(session_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def load_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        if str(session_id) == self._session_id and isinstance(self._view_state, dict):
            return copy.deepcopy(self._view_state)
        loaded = self._delegate.load_view_state(session_id, viewer, player_id=player_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        cached = getattr(self._delegate, "load_cached_view_state", None)
        if not callable(cached):
            return self.load_view_state(session_id, viewer, player_id=player_id)
        loaded = cached(session_id, viewer, player_id=player_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def load_view_commit_index(self, session_id: str) -> dict | None:
        loaded = None
        loader = getattr(self._delegate, "load_view_commit_index", None)
        if callable(loader):
            loaded = loader(session_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        loaded = self._delegate.load_view_commit(session_id, viewer, player_id=player_id)
        return copy.deepcopy(loaded) if isinstance(loaded, dict) else loaded

    def commit_transition(
        self,
        session_id: str,
        *,
        current_state: dict,
        checkpoint: dict,
        view_state: dict | None = None,
        view_commits: dict[str, dict] | None = None,
        command_consumer_name: str | None = None,
        command_seq: int | None = None,
        runtime_event_payload: dict | None = None,
        runtime_event_server_time_ms: int | None = None,
        expected_previous_commit_seq: int | None = None,
    ) -> None:
        self._current_state = copy.deepcopy(current_state)
        self._checkpoint = copy.deepcopy(checkpoint)
        self._view_state = copy.deepcopy(view_state or {})
        self._view_commits = copy.deepcopy(view_commits or {})
        self._deferred_commit = {
            "session_id": session_id,
            "current_state": copy.deepcopy(current_state),
            "checkpoint": copy.deepcopy(checkpoint),
            "view_state": copy.deepcopy(view_state or {}),
            "view_commits": copy.deepcopy(view_commits or {}),
            "command_consumer_name": command_consumer_name,
            "command_seq": command_seq,
            "runtime_event_payload": copy.deepcopy(runtime_event_payload or {}),
            "runtime_event_server_time_ms": runtime_event_server_time_ms,
            "expected_previous_commit_seq": self._base_commit_seq
            if expected_previous_commit_seq is not None
            else expected_previous_commit_seq,
        }
        self.redis_commit_count += 1
        if view_commits:
            self.view_commit_count += 1

    def deferred_commit(self) -> dict | None:
        return copy.deepcopy(self._deferred_commit) if isinstance(self._deferred_commit, dict) else None


__all__ = ["CommandBoundaryGameStateStore"]
