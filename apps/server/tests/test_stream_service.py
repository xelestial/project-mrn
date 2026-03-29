from __future__ import annotations

import asyncio
import unittest

from apps.server.src.services.stream_service import StreamService


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
            await service.unsubscribe("s1", "c1")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
