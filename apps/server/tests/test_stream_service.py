from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

import pytest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.services.stream_service import StreamService
from apps.server.tests.prompt_payloads import module_prompt


class FakeProjectionStore:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.view_states: dict[tuple[str, str], dict] = {}
        self.view_commits: dict[tuple[str, str], dict] = {}
        self.checkpoints: dict[str, dict] = {}

    def apply_stream_message(self, message: dict) -> None:
        self.messages.append(message)
        if message.get("type") != "view_commit":
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        viewer = payload.get("viewer")
        viewer = viewer if isinstance(viewer, dict) else {}
        role = str(viewer.get("role") or "spectator")
        player_id = viewer.get("player_id")
        label = f"player:{player_id}" if role in {"player", "seat"} and player_id is not None else role
        self.view_commits[(str(message.get("session_id") or ""), label)] = payload
        checkpoint = self.checkpoints.setdefault(str(message.get("session_id") or ""), {"schema_version": 1})
        checkpoint.update(
            {
                "latest_seq": int(message.get("seq") or 0),
                "latest_commit_seq": int(payload.get("commit_seq") or 0),
                "latest_source_event_seq": int(payload.get("source_event_seq") or 0),
                "has_view_commit": True,
            }
        )

    def save_cached_view_state(self, session_id: str, viewer: str, payload: dict, *, player_id: int | None = None) -> None:
        label = f"player:{player_id}" if viewer == "player" else viewer
        self.view_states[(session_id, label)] = payload

    def load_cached_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        label = f"player:{player_id}" if viewer == "player" else viewer
        return self.view_states.get((session_id, label))

    def load_view_commit_index(self, session_id: str) -> dict | None:
        return self.checkpoints.get(session_id)

    def save_view_commit_index(self, session_id: str, payload: dict) -> None:
        self.checkpoints[session_id] = payload

    def save_view_commit(self, session_id: str, payload: dict, *, viewer: str, player_id: int | None = None) -> None:
        label = f"player:{player_id}" if viewer in {"player", "seat"} and player_id is not None else viewer
        self.view_commits[(session_id, label)] = payload
        checkpoint = self.checkpoints.setdefault(session_id, {"schema_version": 1})
        viewers = set(str(item) for item in checkpoint.get("view_commit_viewers", []))
        viewers.add(label)
        checkpoint["view_commit_viewers"] = sorted(viewers)
        checkpoint["latest_commit_seq"] = max(
            int(checkpoint.get("latest_commit_seq") or 0),
            int(payload.get("commit_seq") or 0),
        )
        checkpoint["latest_source_event_seq"] = max(
            int(checkpoint.get("latest_source_event_seq") or 0),
            int(payload.get("source_event_seq") or 0),
        )
        checkpoint["has_view_commit"] = True

    def load_view_commit(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        label = f"player:{player_id}" if viewer in {"player", "seat"} and player_id is not None else viewer
        return self.view_commits.get((session_id, label))


class FakeExternalStreamBackend:
    def __init__(self) -> None:
        self.records: dict[str, list[dict]] = {}
        self.drop_counts: dict[str, int] = {}
        self.source_snapshot_calls = 0
        self.publish_calls = 0

    def publish(
        self,
        session_id: str,
        msg_type: str,
        payload: dict,
        *,
        server_time_ms: int,
        max_buffer: int,
    ) -> dict:
        self.publish_calls += 1
        records = self.records.setdefault(session_id, [])
        seq = int(records[-1].get("seq") or 0) + 1 if records else 1
        record = {
            "type": msg_type,
            "seq": seq,
            "session_id": session_id,
            "server_time_ms": int(server_time_ms),
            "payload": dict(payload),
        }
        records.append(record)
        if len(records) > max_buffer:
            del records[: len(records) - max_buffer]
        return record

    def snapshot(self, session_id: str) -> list[dict]:
        return list(self.records.get(session_id, []))

    def replay_from(self, session_id: str, last_seq: int) -> list[dict]:
        return [record for record in self.snapshot(session_id) if int(record.get("seq") or 0) > last_seq]

    def source_snapshot(self, session_id: str, through_seq: int | None = None) -> list[dict]:
        self.source_snapshot_calls += 1
        records = [record for record in self.snapshot(session_id) if record.get("type") != "view_commit"]
        if through_seq is None:
            return records
        return [record for record in records if int(record.get("seq") or 0) <= through_seq]

    def replay_window(self, session_id: str) -> tuple[int, int]:
        records = self.snapshot(session_id)
        if not records:
            return (0, 0)
        return (int(records[0].get("seq") or 0), int(records[-1].get("seq") or 0))

    def latest_seq(self, session_id: str) -> int:
        records = self.snapshot(session_id)
        return int(records[-1].get("seq") or 0) if records else 0

    def drop_count(self, session_id: str) -> int:
        return int(self.drop_counts.get(session_id, 0))


def _source_messages(messages: list) -> list:
    return [message for message in messages if message.type != "view_commit"]


def _view_commit_messages(messages: list) -> list:
    return [message for message in messages if message.type == "view_commit"]


class StreamServiceTests(unittest.TestCase):
    def test_stream_service_live_path_does_not_import_replay_projector(self) -> None:
        source = Path(__file__).parents[1].joinpath("src/services/stream_service.py").read_text()
        self.assertNotIn("project_replay_view_state", source)

    def test_publish_increments_seq(self) -> None:
        service = StreamService()

        async def _run() -> None:
            one = await service.publish("s1", "event", {"a": 1})
            two = await service.publish("s1", "event", {"a": 2})
            self.assertEqual(one.seq, 1)
            self.assertEqual(two.seq, 2)
            self.assertIsInstance(one.server_time_ms, int)
            self.assertGreater(one.server_time_ms, 0)

        asyncio.run(_run())

    def test_session_scoped_reads_do_not_wait_on_global_stream_lock(self) -> None:
        service = StreamService()

        async def _run() -> None:
            await service.publish("fast", "event", {"event_type": "turn_start"})
            await service._lock.acquire()
            try:
                latest = await asyncio.wait_for(service.latest_seq("fast"), timeout=0.1)
            finally:
                service._lock.release()
            self.assertEqual(latest, 1)

        asyncio.run(_run())

    def test_backend_reads_and_projection_do_not_wait_on_session_publish_lock(self) -> None:
        backend = FakeExternalStreamBackend()
        backend.records["locked"] = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "locked",
                "server_time_ms": 101,
                "payload": {"event_type": "round_start"},
            },
            {
                "type": "view_commit",
                "seq": 2,
                "session_id": "locked",
                "server_time_ms": 102,
                "payload": {"commit_seq": 9, "source_event_seq": 1},
            },
        ]
        store = FakeProjectionStore()
        store.save_view_commit(
            "locked",
            {
                "commit_seq": 9,
                "source_event_seq": 1,
                "viewer": {"role": "spectator"},
                "view_state": {"turn_stage": {"round_index": 1, "turn_index": 0}},
            },
            viewer="spectator",
        )
        service = StreamService(stream_backend=backend, game_state_store=store)

        async def _run() -> None:
            lock = service._lock_for_session("locked")
            await lock.acquire()
            try:
                viewer = ViewerContext(role="spectator", session_id="locked")
                latest = await asyncio.wait_for(service.latest_seq("locked"), timeout=0.25)
                latest_commit = await asyncio.wait_for(
                    service.latest_view_commit_message_for_viewer("locked", viewer),
                    timeout=0.25,
                )
                projected = await asyncio.wait_for(
                    service.project_message_for_viewer(backend.records["locked"][1], viewer),
                    timeout=0.25,
                )
            finally:
                lock.release()
            self.assertEqual(latest, 2)
            self.assertEqual(latest_commit.get("payload", {}).get("commit_seq"), 9)
            self.assertEqual(projected.get("payload", {}).get("commit_seq"), 9)

        asyncio.run(_run())

    def test_decision_ack_publish_skips_authoritative_source_history_scan(self) -> None:
        backend = FakeExternalStreamBackend()
        backend.records["s1"] = [
            {
                "type": "event",
                "seq": 1,
                "session_id": "s1",
                "server_time_ms": 101,
                "payload": {"event_type": "round_start"},
            },
            {
                "type": "view_commit",
                "seq": 2,
                "session_id": "s1",
                "server_time_ms": 102,
                "payload": {"commit_seq": 1, "source_event_seq": 1},
            },
        ]
        service = StreamService(stream_backend=backend)

        async def _run() -> None:
            ack = await service.publish_decision_ack(
                "s1",
                {
                    "request_id": "r_ack_1",
                    "status": "accepted",
                    "player_id": 1,
                    "provider": "human",
                },
            )

            self.assertEqual(ack.type, "decision_ack")
            self.assertEqual(ack.seq, 3)
            self.assertEqual(backend.publish_calls, 1)
            self.assertEqual(backend.source_snapshot_calls, 0)
            self.assertRegex(ack.payload["event_id"], r"^evt_[0-9a-f-]{36}$")

        asyncio.run(_run())

    def test_publish_adds_source_event_id(self) -> None:
        service = StreamService()

        async def _run() -> None:
            event = await service.publish("s1", "event", {"event_type": "round_start"})
            prompt = await service.publish("s1", "prompt", module_prompt({"request_id": "r1"}))
            commit = await service.publish_view_commit("s1", {"commit_seq": 1, "source_event_seq": event.seq})

            self.assertRegex(event.payload["event_id"], r"^evt_[0-9a-f-]{36}$")
            self.assertRegex(prompt.payload["event_id"], r"^evt_[0-9a-f-]{36}$")
            self.assertNotIn("event_id", commit.payload)

        asyncio.run(_run())

    def test_replay_from_returns_tail(self) -> None:
        service = StreamService()

        async def _run() -> None:
            await service.publish("s1", "event", {"n": 1})
            await service.publish("s1", "event", {"n": 2})
            await service.publish("s1", "event", {"n": 3})
            replay = await service.replay_from("s1", 1)
            self.assertEqual([m.seq for m in replay], [2, 3])

        asyncio.run(_run())

    def test_subscriber_receives_published_messages(self) -> None:
        service = StreamService()

        async def _run() -> None:
            queue = await service.subscribe("s1", "c1")
            await service.publish("s1", "event", {"n": 1})
            message = await asyncio.wait_for(queue.get(), timeout=0.5)
            self.assertEqual(message["type"], "event")
            self.assertEqual(message["seq"], 1)
            self.assertIn("server_time_ms", message)
            await service.unsubscribe("s1", "c1")

        asyncio.run(_run())

    def test_snapshot_returns_all_buffered_messages(self) -> None:
        service = StreamService()

        async def _run() -> None:
            await service.publish("s1", "event", {"n": 1})
            await service.publish("s1", "prompt", module_prompt({"request_id": "r1"}))
            snapshot = await service.snapshot("s1")
            self.assertEqual([message.seq for message in _source_messages(snapshot)], [1, 2])
            self.assertEqual(_view_commit_messages(snapshot), [])

        asyncio.run(_run())

    def test_publish_deduplicates_prompt_and_decision_requested_by_request_id(self) -> None:
        service = StreamService()

        async def _run() -> None:
            first_prompt = await service.publish("s1", "prompt", module_prompt({"request_id": "r1", "request_type": "movement"}))
            second_prompt = await service.publish("s1", "prompt", module_prompt({"request_id": "r1", "request_type": "movement"}))
            first_requested = await service.publish(
                "s1",
                "event",
                {"event_type": "decision_requested", "request_id": "r1", "request_type": "movement"},
            )
            second_requested = await service.publish(
                "s1",
                "event",
                {"event_type": "decision_requested", "request_id": "r1", "request_type": "movement"},
            )
            snapshot = await service.snapshot("s1")

            self.assertEqual(first_prompt.seq, second_prompt.seq)
            self.assertEqual(first_requested.seq, second_requested.seq)
            self.assertEqual(len(_source_messages(snapshot)), 2)
            self.assertEqual(_view_commit_messages(snapshot), [])

        asyncio.run(_run())

    def test_publish_deduplicates_runtime_module_idempotency_key(self) -> None:
        service = StreamService()

        async def _run() -> None:
            first = await service.publish(
                "s1",
                "event",
                {
                    "event_type": "dice_roll",
                    "runtime_module": {
                        "module_type": "DiceRollModule",
                        "idempotency_key": "idem:dice:1",
                    },
                },
            )
            second = await service.publish(
                "s1",
                "event",
                {
                    "event_type": "dice_roll",
                    "dice": [6],
                    "runtime_module": {
                        "module_type": "DiceRollModule",
                        "idempotency_key": "idem:dice:1",
                    },
                },
            )
            snapshot = await service.snapshot("s1")

            self.assertEqual(first.seq, second.seq)
            self.assertEqual(len(_source_messages(snapshot)), 1)
            self.assertEqual(_view_commit_messages(snapshot), [])

        asyncio.run(_run())

    def test_publish_keeps_distinct_runtime_idempotency_keys(self) -> None:
        service = StreamService()

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "dice_roll",
                    "runtime_module": {
                        "module_type": "DiceRollModule",
                        "idempotency_key": "idem:dice:1",
                    },
                },
            )
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "dice_roll",
                    "runtime_module": {
                        "module_type": "DiceRollModule",
                        "idempotency_key": "idem:dice:2",
                    },
                },
            )
            snapshot = await service.snapshot("s1")

            self.assertEqual(len(_source_messages(snapshot)), 2)
            self.assertEqual(_view_commit_messages(snapshot), [])

        asyncio.run(_run())

    def test_publish_rejects_runtime_impossible_module_placement(self) -> None:
        service = StreamService()

        async def _run() -> None:
            with pytest.raises(Exception, match="DraftModule"):
                await service.publish(
                    "s1",
                    "event",
                    {
                        "event_type": "draft_pick",
                        "runtime_module": {
                            "frame_type": "turn",
                            "frame_id": "turn:1:p0",
                            "module_type": "DraftModule",
                            "module_id": "mod:draft",
                        },
                    },
                )

        asyncio.run(_run())

    def test_publish_attaches_public_safe_view_state_only(self) -> None:
        service = StreamService()

        async def _run() -> None:
            prompt = await service.publish(
                "s1",
                "prompt",
                module_prompt({
                    "request_id": "req_trick",
                    "request_type": "trick_to_use",
                    "player_id": 1,
                    "legal_choices": [{"choice_id": "card-11"}],
                    "public_context": {
                        "full_hand": [{"deck_index": 11, "name": "재뿌리기"}],
                        "hidden_trick_deck_index": 11,
                    },
                }),
            )

            view_state = prompt.payload.get("view_state")
            if isinstance(view_state, dict):
                self.assertNotIn("prompt", view_state)
                self.assertNotIn("hand_tray", view_state)
            self.assertIn("legal_choices", prompt.payload)
            self.assertIn("full_hand", prompt.payload["public_context"])

        asyncio.run(_run())

    def test_latest_view_commit_for_target_uses_cached_player_commit(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.view_commits[("s1", "player:1")] = {
                "schema_version": 1,
                "commit_seq": 8,
                "source_event_seq": 7,
                "viewer": {"role": "seat", "player_id": 1, "seat": 1},
                "runtime": {"status": "waiting_input"},
                "view_state": {
                    "prompt": {"active": {"request_id": "req_trick"}},
                    "hand_tray": {"cards": [{"name": "재뿌리기"}]},
                },
            }

            target = await service.latest_view_commit_message_for_viewer("s1", ViewerContext(role="seat", session_id="s1", player_id=1))
            other = await service.latest_view_commit_message_for_viewer("s1", ViewerContext(role="seat", session_id="s1", player_id=2))

            self.assertIsNotNone(target)
            view_state = target["payload"]["view_state"]
            self.assertEqual(view_state["prompt"]["active"]["request_id"], "req_trick")
            self.assertEqual(view_state["hand_tray"]["cards"][0]["name"], "재뿌리기")
            self.assertIsNone(other)

        asyncio.run(_run())

    def test_latest_view_commit_for_target_falls_back_to_public_snapshot_when_player_commit_missing(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 8,
                    "source_event_seq": 7,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"turn_stage": {"current_beat_event_code": "turn_start"}},
                },
                viewer="spectator",
            )

            latest = await service.latest_view_commit_message_for_viewer(
                "s1",
                ViewerContext(role="seat", session_id="s1", player_id=2),
            )

            self.assertIsNotNone(latest)
            self.assertEqual(latest["payload"]["viewer"]["role"], "spectator")
            self.assertEqual(latest["payload"]["commit_seq"], 8)
            self.assertEqual(latest["payload"]["view_state"]["turn_stage"]["current_beat_event_code"], "turn_start")

        asyncio.run(_run())

    def test_latest_view_commit_for_target_ignores_stale_player_commit_when_public_is_newer(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 8,
                    "source_event_seq": 7,
                    "viewer": {"role": "seat", "player_id": 1},
                    "runtime": {"status": "waiting_input"},
                    "view_state": {
                        "prompt": {"active": {"request_id": "stale_req"}},
                        "hand_tray": {"cards": [{"name": "낡은 패"}]},
                    },
                },
                viewer="player",
                player_id=1,
            )
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 9,
                    "source_event_seq": 8,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"prompt": {"active": None}, "board": {"tile_count": 40}},
                },
                viewer="spectator",
            )

            latest = await service.latest_view_commit_message_for_viewer(
                "s1",
                ViewerContext(role="seat", session_id="s1", player_id=1),
            )

            self.assertIsNotNone(latest)
            self.assertEqual(latest["payload"]["viewer"]["role"], "spectator")
            self.assertEqual(latest["payload"]["commit_seq"], 9)
            self.assertEqual(latest["payload"]["view_state"], {"prompt": {"active": None}, "board": {"tile_count": 40}})

        asyncio.run(_run())

    def test_publish_does_not_write_live_game_state(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "state_snapshot",
                    "snapshot": {
                        "players": [{"player_id": 1, "position": 3, "alive": True}],
                        "board": {
                            "f_value": 7,
                            "tiles": [{"tile_index": 3, "owner_player_id": None, "score_coin_count": 0}],
                        },
                    },
                },
            )

            self.assertNotIn(("s1", "spectator"), store.view_commits)
            self.assertEqual(store.messages, [])

        asyncio.run(_run())

    def test_project_message_for_viewer_uses_cached_player_commit_without_rebuild(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            commit = await service.publish_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 4,
                    "source_event_seq": 3,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "waiting_input"},
                    "view_state": {
                        "prompt": {"active": {"request_id": "spectator"}},
                    },
                },
            )
            store.view_commits[("s1", "player:1")] = {
                "schema_version": 1,
                "commit_seq": 4,
                "source_event_seq": 3,
                "viewer": {"role": "seat", "player_id": 1},
                "runtime": {"status": "waiting_input"},
                "view_state": {"prompt": {"active": {"request_id": "req_trick"}}},
            }

            target = await service.project_message_for_viewer(commit.to_dict(), ViewerContext(role="seat", session_id="s1", player_id=1))

            self.assertIsNotNone(target)
            self.assertEqual(target["payload"]["view_state"]["prompt"]["active"]["request_id"], "req_trick")

        asyncio.run(_run())

    def test_latest_view_commit_for_viewer_uses_cached_commit(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "turn_end_snapshot",
                    "snapshot": {
                        "players": [{"player_id": 1, "position": 3, "alive": True}],
                        "board": {"tiles": [{"tile_index": 3}]},
                    },
                },
            )
            store.view_commits[("s1", "spectator")] = {
                "schema_version": 1,
                "commit_seq": 99,
                "source_event_seq": 1,
                "viewer": {"role": "spectator"},
                "runtime": {"status": "running"},
                "view_state": {"cached": True},
            }

            latest = await service.latest_view_commit_message_for_viewer("s1", ViewerContext(role="spectator", session_id="s1"))

            self.assertEqual(latest["payload"]["commit_seq"], 99)
            self.assertEqual(latest["payload"]["view_state"], {"cached": True})

        asyncio.run(_run())

    def test_latest_view_commit_uses_emitted_stream_seq_when_available(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 1,
                    "turn_index": 1,
                    "acting_player_id": 1,
                },
            )
            store.view_commits[("s1", "spectator")] = {
                "schema_version": 1,
                "commit_seq": 7,
                "source_event_seq": 1,
                "viewer": {"role": "spectator"},
                "runtime": {"status": "running"},
                "view_state": {"cached": True},
            }
            emitted = await service.emit_latest_view_commit("s1")

            latest = await service.latest_view_commit_message_for_viewer(
                "s1",
                ViewerContext(role="spectator", session_id="s1"),
            )

            self.assertIsNotNone(emitted)
            self.assertEqual(latest["seq"], emitted.seq)
            self.assertNotEqual(latest["seq"], latest["payload"]["commit_seq"])

        asyncio.run(_run())

    def test_latest_view_commit_keeps_cached_commit_even_when_source_stream_advanced(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 7,
                    "turn_index": 14,
                    "acting_player_id": 1,
                    "character": "산적",
                },
            )
            stale = {
                "schema_version": 1,
                "commit_seq": 2,
                "source_event_seq": 1,
                "viewer": {"role": "spectator"},
                "runtime": {"status": "running"},
                "view_state": {"turn_stage": {"current_beat_event_code": "turn_start"}},
            }
            async with service._lock:  # Deliberately simulate a Redis-direct runtime event.
                service._append_stream_message_no_lock(
                    "s1",
                    "event",
                    {"event_type": "engine_transition", "status": "completed", "reason": "end_rule"},
                    server_time_ms=2000,
                )
            store.view_commits[("s1", "spectator")] = stale

            latest = await service.latest_view_commit_message_for_viewer("s1", ViewerContext(role="spectator", session_id="s1"))

            self.assertEqual(latest["payload"]["source_event_seq"], 1)
            self.assertEqual(latest["payload"]["runtime"]["status"], "running")
            self.assertEqual(latest["payload"]["view_state"]["turn_stage"]["current_beat_event_code"], "turn_start")

        asyncio.run(_run())

    def test_emit_latest_view_commit_broadcasts_cached_commit_only(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "turn_start",
                    "round_index": 7,
                    "turn_index": 14,
                    "acting_player_id": 1,
                    "character": "산적",
                },
            )
            self.assertIsNone(await service.emit_latest_view_commit("s1"))
            store.view_commits[("s1", "spectator")] = {
                "schema_version": 1,
                "commit_seq": 5,
                "source_event_seq": 4,
                "viewer": {"role": "spectator"},
                "runtime": {"status": "completed"},
                "view_state": {"turn_stage": {"current_beat_event_code": "game_end"}},
            }

            emitted = await service.emit_latest_view_commit("s1")
            snapshot = await service.snapshot("s1")

            self.assertIsNotNone(emitted)
            self.assertEqual(emitted.type, "view_commit")
            self.assertEqual(emitted.payload["source_event_seq"], 4)
            self.assertEqual(emitted.payload["runtime"]["status"], "completed")
            self.assertEqual(snapshot[-1].type, "view_commit")
            self.assertEqual(store.view_commits[("s1", "spectator")]["source_event_seq"], 4)

        asyncio.run(_run())

    def test_emit_snapshot_pulse_broadcasts_pointer_without_raw_commit_payload(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 12,
                    "source_event_seq": 9,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"turn_stage": {"round_index": 2}},
                },
                viewer="spectator",
            )

            emitted = await service.emit_snapshot_pulse("s1", reason="round_start_guardrail")
            snapshot = await service.snapshot("s1")

            self.assertIsNotNone(emitted)
            self.assertEqual(emitted.type, "snapshot_pulse")
            self.assertEqual(emitted.payload["reason"], "round_start_guardrail")
            self.assertNotIn("view_state", emitted.payload)
            self.assertNotIn("commit_seq", emitted.payload)
            self.assertEqual(snapshot[-1].type, "snapshot_pulse")

        asyncio.run(_run())

    def test_snapshot_pulse_projects_latest_cached_commit_for_viewer(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 12,
                    "source_event_seq": 9,
                    "viewer": {"role": "seat", "player_id": 1},
                    "runtime": {"status": "waiting_input"},
                    "view_state": {"prompt": {"active": {"request_id": "req_turn_start"}}},
                },
                viewer="player",
                player_id=1,
            )

            emitted = await service.emit_snapshot_pulse(
                "s1",
                reason="turn_start_guardrail",
                target_player_id=1,
            )
            self.assertIsNotNone(emitted)
            projected = await service.project_message_for_viewer(
                emitted.to_dict(),
                ViewerContext(role="seat", session_id="s1", player_id=1),
            )

            self.assertIsNotNone(projected)
            self.assertEqual(projected["type"], "snapshot_pulse")
            self.assertEqual(projected["seq"], emitted.seq)
            self.assertEqual(projected["payload"]["commit_seq"], 12)
            self.assertEqual(projected["payload"]["snapshot_pulse"]["reason"], "turn_start_guardrail")
            self.assertEqual(projected["payload"]["view_state"]["prompt"]["active"]["request_id"], "req_turn_start")

        asyncio.run(_run())

    def test_targeted_snapshot_pulse_is_hidden_from_other_players_and_spectators(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 12,
                    "source_event_seq": 9,
                    "viewer": {"role": "seat", "player_id": 1},
                    "runtime": {"status": "waiting_input"},
                    "view_state": {"prompt": {"active": {"request_id": "req_turn_start"}}},
                },
                viewer="player",
                player_id=1,
            )
            store.save_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 12,
                    "source_event_seq": 9,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"prompt": {"active": None}},
                },
                viewer="spectator",
            )

            emitted = await service.emit_snapshot_pulse(
                "s1",
                reason="turn_start_guardrail",
                target_player_id=1,
            )
            self.assertIsNotNone(emitted)

            other = await service.project_message_for_viewer(
                emitted.to_dict(),
                ViewerContext(role="seat", session_id="s1", player_id=2),
            )
            spectator = await service.project_message_for_viewer(
                emitted.to_dict(),
                ViewerContext(role="spectator", session_id="s1"),
            )

            self.assertIsNone(other)
            self.assertIsNone(spectator)

        asyncio.run(_run())

    def test_project_message_for_viewer_does_not_rebuild_view_commit(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            commit = await service.publish_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 2,
                    "source_event_seq": 1,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"prompt": {"active": {"request_id": "spectator"}}},
                },
            )
            viewer = ViewerContext(role="seat", session_id="s1", player_id=1)
            store.view_commits[("s1", "player:1")] = {
                "schema_version": 1,
                "commit_seq": 2,
                "source_event_seq": 1,
                "viewer": {"role": "seat", "player_id": 1},
                "runtime": {"status": "running"},
                "view_state": {"prompt": {"last_feedback": {"request_id": "old"}}},
            }

            rebuilt = await service.project_message_for_viewer(commit.to_dict(), viewer)

            self.assertEqual(rebuilt["payload"]["view_state"]["prompt"]["last_feedback"]["request_id"], "old")
            self.assertNotIn("active", store.view_commits[("s1", "player:1")]["view_state"]["prompt"])

        asyncio.run(_run())

    def test_latest_view_commit_for_viewer_requires_cached_commit(self) -> None:
        service = StreamService()

        async def _run() -> None:
            await service.publish_view_commit(
                "s1",
                {
                    "schema_version": 1,
                    "commit_seq": 4,
                    "source_event_seq": 3,
                    "viewer": {"role": "spectator"},
                    "runtime": {"status": "running"},
                    "view_state": {"players": {"items": [{"player_id": 1}]}},
                },
            )
            await service.publish("s1", "event", {"event_type": "turn_start", "acting_player_id": 1})

            latest = await service.latest_view_commit_message_for_viewer("s1", ViewerContext(role="spectator", session_id="s1"))

            self.assertIsNone(latest)

        asyncio.run(_run())

    def test_replay_window_tracks_oldest_and_latest_seq(self) -> None:
        service = StreamService(max_buffer=2)

        async def _run() -> None:
            empty_window = await service.replay_window("s1")
            self.assertEqual(empty_window, (0, 0))
            await service.publish("s1", "event", {"n": 1})
            await service.publish("s1", "event", {"n": 2})
            await service.publish("s1", "event", {"n": 3})
            window = await service.replay_window("s1")
            self.assertEqual(window, (2, 3))

        asyncio.run(_run())

    def test_slow_subscriber_drops_oldest_message_when_queue_is_full(self) -> None:
        service = StreamService(queue_size=2)

        async def _run() -> None:
            queue = await service.subscribe("s1", "c1")
            await service.publish("s1", "event", {"n": 1})
            await service.publish("s1", "event", {"n": 2})
            await service.publish("s1", "event", {"n": 3})

            first = await asyncio.wait_for(queue.get(), timeout=0.5)
            second = await asyncio.wait_for(queue.get(), timeout=0.5)

            self.assertEqual([first["seq"], second["seq"]], [2, 3])
            stats = await service.backpressure_stats("s1")
            self.assertEqual(stats["subscriber_count"], 1)
            self.assertEqual(stats["queue_size"], 2)
            self.assertGreaterEqual(stats["drop_count"], 1)
            await service.unsubscribe("s1", "c1")

        asyncio.run(_run())

    def test_replay_window_remains_monotonic_under_large_publish_volume(self) -> None:
        service = StreamService(max_buffer=50)

        async def _run() -> None:
            for n in range(1, 301):
                await service.publish("s1", "event", {"n": n})
            oldest, latest = await service.replay_window("s1")
            self.assertEqual((oldest, latest), (251, 300))
            replay = await service.replay_from("s1", 295)
            self.assertEqual([m.seq for m in replay], [296, 297, 298, 299, 300])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
