from __future__ import annotations

import asyncio
import unittest

from apps.server.src.domain.visibility import ViewerContext
from apps.server.src.services.stream_service import StreamService


class FakeProjectionStore:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.view_states: dict[tuple[str, str], dict] = {}
        self.checkpoints: dict[str, dict] = {}

    def apply_stream_message(self, message: dict) -> None:
        self.messages.append(message)

    def save_projected_view_state(self, session_id: str, viewer: str, payload: dict, *, player_id: int | None = None) -> None:
        label = f"player:{player_id}" if viewer == "player" else viewer
        self.view_states[(session_id, label)] = payload

    def load_projected_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict | None:
        label = f"player:{player_id}" if viewer == "player" else viewer
        return self.view_states.get((session_id, label))

    def load_projection_checkpoint(self, session_id: str) -> dict | None:
        return self.checkpoints.get(session_id)

    def save_projection_checkpoint(self, session_id: str, payload: dict) -> None:
        self.checkpoints[session_id] = payload


class StreamServiceTests(unittest.TestCase):
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
            await service.publish("s1", "prompt", {"request_id": "r1"})
            snapshot = await service.snapshot("s1")
            self.assertEqual(len(snapshot), 2)
            self.assertEqual(snapshot[0].seq, 1)
            self.assertEqual(snapshot[1].seq, 2)

        asyncio.run(_run())

    def test_publish_deduplicates_prompt_and_decision_requested_by_request_id(self) -> None:
        service = StreamService()

        async def _run() -> None:
            first_prompt = await service.publish("s1", "prompt", {"request_id": "r1", "request_type": "movement"})
            second_prompt = await service.publish("s1", "prompt", {"request_id": "r1", "request_type": "movement"})
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
            self.assertEqual(len(snapshot), 2)

        asyncio.run(_run())

    def test_publish_attaches_public_safe_view_state_only(self) -> None:
        service = StreamService()

        async def _run() -> None:
            prompt = await service.publish(
                "s1",
                "prompt",
                {
                    "request_id": "req_trick",
                    "request_type": "trick_to_use",
                    "player_id": 1,
                    "legal_choices": [{"choice_id": "card-11"}],
                    "public_context": {
                        "full_hand": [{"deck_index": 11, "name": "재뿌리기"}],
                        "hidden_trick_deck_index": 11,
                    },
                },
            )

            view_state = prompt.payload.get("view_state")
            if isinstance(view_state, dict):
                self.assertNotIn("prompt", view_state)
                self.assertNotIn("hand_tray", view_state)
            self.assertIn("legal_choices", prompt.payload)
            self.assertIn("full_hand", prompt.payload["public_context"])

        asyncio.run(_run())

    def test_project_message_for_target_rebuilds_private_view_state(self) -> None:
        service = StreamService()

        async def _run() -> None:
            prompt = await service.publish(
                "s1",
                "prompt",
                {
                    "request_id": "req_trick",
                    "request_type": "trick_to_use",
                    "player_id": 1,
                    "legal_choices": [
                        {
                            "choice_id": "card-11",
                            "title": "재뿌리기",
                            "value": {"deck_index": 11},
                        }
                    ],
                    "public_context": {
                        "full_hand": [
                            {
                                "deck_index": 11,
                                "name": "재뿌리기",
                                "card_description": "이번 턴 임대료를 0으로 만듭니다.",
                                "is_usable": True,
                            }
                        ],
                    },
                },
            )

            target = await service.project_message_for_viewer(prompt.to_dict(), ViewerContext(role="seat", session_id="s1", player_id=1))
            other = await service.project_message_for_viewer(prompt.to_dict(), ViewerContext(role="seat", session_id="s1", player_id=2))

            self.assertIsNotNone(target)
            view_state = target["payload"]["view_state"]
            self.assertEqual(view_state["prompt"]["active"]["request_id"], "req_trick")
            self.assertEqual(view_state["hand_tray"]["cards"][0]["name"], "재뿌리기")
            self.assertIsNone(other)

        asyncio.run(_run())

    def test_publish_caches_spectator_projection(self) -> None:
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

            cached = store.view_states[("s1", "spectator")]
            self.assertEqual(cached["board"]["f_value"], 7)
            self.assertEqual(store.checkpoints["s1"]["latest_seq"], 1)
            self.assertEqual(store.checkpoints["s1"]["projected_viewers"], ["spectator"])

        asyncio.run(_run())

    def test_project_message_for_target_caches_player_projection(self) -> None:
        store = FakeProjectionStore()
        service = StreamService(game_state_store=store)

        async def _run() -> None:
            prompt = await service.publish(
                "s1",
                "prompt",
                {
                    "request_id": "req_trick",
                    "request_type": "trick_to_use",
                    "player_id": 1,
                    "legal_choices": [{"choice_id": "card-11", "title": "재뿌리기"}],
                    "public_context": {
                        "full_hand": [{"deck_index": 11, "name": "재뿌리기", "is_usable": True}],
                    },
                },
            )

            target = await service.project_message_for_viewer(prompt.to_dict(), ViewerContext(role="seat", session_id="s1", player_id=1))

            self.assertIsNotNone(target)
            cached = store.view_states[("s1", "player:1")]
            self.assertEqual(cached["prompt"]["active"]["request_id"], "req_trick")
            self.assertEqual(cached["hand_tray"]["cards"][0]["name"], "재뿌리기")
            self.assertEqual(store.checkpoints["s1"]["projected_viewers"], ["player:1", "spectator"])
            self.assertEqual(store.checkpoints["s1"]["projected_viewer_seqs"], {"player:1": 1, "spectator": 1})

        asyncio.run(_run())

    def test_latest_view_state_for_viewer_uses_fresh_cache(self) -> None:
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
            store.view_states[("s1", "spectator")] = {"cached": True}
            store.checkpoints["s1"]["projected_viewer_seqs"]["spectator"] = 1

            latest = await service.latest_view_state_for_viewer("s1", ViewerContext(role="spectator", session_id="s1"))

            self.assertEqual(latest, {"cached": True})

        asyncio.run(_run())

    def test_latest_view_state_for_viewer_rebuilds_stale_cache(self) -> None:
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
            await service.publish("s1", "event", {"event_type": "turn_start", "acting_player_id": 1})
            store.view_states[("s1", "spectator")] = {"cached": "stale"}
            store.checkpoints["s1"]["projected_viewer_seqs"]["spectator"] = 1

            latest = await service.latest_view_state_for_viewer("s1", ViewerContext(role="spectator", session_id="s1"))

            self.assertNotEqual(latest, {"cached": "stale"})
            self.assertEqual(store.checkpoints["s1"]["projected_viewer_seqs"]["spectator"], 2)
            self.assertIn("players", latest)

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
