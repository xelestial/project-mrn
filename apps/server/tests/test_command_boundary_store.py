from __future__ import annotations

import copy

from apps.server.src.services.command_boundary_store import CommandBoundaryGameStateStore


class _DelegateStoreStub:
    def __init__(self) -> None:
        self.current_state = {"session_id": "s1", "turn_index": 0}
        self.checkpoint = {
            "schema_version": 3,
            "session_id": "s1",
            "runner_kind": "module",
            "has_snapshot": True,
            "base_commit_seq": 3,
            "latest_commit_seq": 4,
        }
        self.view_state = {"viewer": "spectator"}
        self.view_commit_index = {"latest": {"commit_seq": 4}}
        self.view_commit = {"commit_seq": 4, "view_state": {"ok": True}}
        self.commits: list[dict] = []

    def load_current_state(self, session_id: str) -> dict | None:
        if session_id != "s1":
            return None
        return copy.deepcopy(self.current_state)

    def load_checkpoint(self, session_id: str) -> dict | None:
        if session_id != "s1":
            return None
        return copy.deepcopy(self.checkpoint)

    def load_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        del viewer, player_id
        if session_id != "s1":
            return None
        return copy.deepcopy(self.view_state)

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        return self.load_view_state(session_id, viewer, player_id=player_id)

    def load_view_commit_index(self, session_id: str) -> dict | None:
        if session_id != "s1":
            return None
        return copy.deepcopy(self.view_commit_index)

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        del viewer, player_id
        if session_id != "s1":
            return None
        return copy.deepcopy(self.view_commit)

    def commit_transition(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.commits.append({"args": args, "kwargs": copy.deepcopy(kwargs)})


def test_command_boundary_store_stages_internal_state_without_authoritative_commit() -> None:
    delegate = _DelegateStoreStub()
    boundary_store = CommandBoundaryGameStateStore(delegate, session_id="s1", base_commit_seq=4)

    boundary_store.stage_internal_transition("s1", current_state={"session_id": "s1", "turn_index": 1})

    assert delegate.commits == []
    assert boundary_store.internal_state_stage_count == 1
    assert boundary_store.redis_commit_count == 0
    assert boundary_store.view_commit_count == 0
    assert boundary_store.deferred_commit() is None
    assert boundary_store.load_current_state("s1") == {"session_id": "s1", "turn_index": 1}
    assert boundary_store.load_current_state("other") is None


def test_command_boundary_store_defers_terminal_commit_and_hides_staged_checkpoint_seq() -> None:
    delegate = _DelegateStoreStub()
    boundary_store = CommandBoundaryGameStateStore(delegate, session_id="s1", base_commit_seq=4)

    boundary_store.commit_transition(
        "s1",
        current_state={"session_id": "s1", "turn_index": 2},
        checkpoint={
            "schema_version": 3,
            "session_id": "s1",
            "runner_kind": "module",
            "has_snapshot": True,
            "base_commit_seq": 4,
            "latest_commit_seq": 5,
        },
        view_state={"viewer": "spectator", "turn_index": 2},
        view_commits={"spectator": {"commit_seq": 5, "view_state": {"turn_index": 2}}},
        command_consumer_name="runtime-worker",
        command_seq=10,
        runtime_event_payload={"latest_commit_seq": 5},
        expected_previous_commit_seq=4,
    )

    assert delegate.commits == []
    assert boundary_store.redis_commit_count == 1
    assert boundary_store.view_commit_count == 1
    assert boundary_store.load_current_state("s1") == {"session_id": "s1", "turn_index": 2}
    assert boundary_store.load_checkpoint("s1")["latest_commit_seq"] == 4

    deferred = boundary_store.deferred_commit()
    assert deferred is not None
    assert deferred["session_id"] == "s1"
    assert deferred["command_consumer_name"] == "runtime-worker"
    assert deferred["command_seq"] == 10
    assert deferred["expected_previous_commit_seq"] == 4
    deferred["current_state"]["turn_index"] = 99
    assert boundary_store.deferred_commit()["current_state"]["turn_index"] == 2
