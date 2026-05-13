from __future__ import annotations

import threading
import unittest

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.batch_collector import BatchCollector
from apps.server.src.services.realtime_persistence import RedisCommandStore
from apps.server.tests.test_redis_realtime_services import _FakeRedis


class BatchCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_redis = _FakeRedis()
        self.connection = RedisConnection(
            RedisConnectionSettings(url="redis://127.0.0.1:6379/10", key_prefix="mrn-batch", socket_timeout_ms=250),
            client_factory=lambda: self.fake_redis,
        )
        self.command_store = RedisCommandStore(self.connection)
        self.collector = BatchCollector(self.connection, self.command_store)

    def test_records_remaining_and_emits_single_batch_complete_command(self) -> None:
        first = self.collector.record_response(
            session_id="s1",
            batch_id="batch_1",
            player_id=1,
            response={"choice_id": "a", "public_player_id": "ply_1"},
            expected_player_ids=[1, 2],
            server_time_ms=100,
        )
        second = self.collector.record_response(
            session_id="s1",
            batch_id="batch_1",
            player_id=2,
            response={"choice_id": "b", "public_player_id": "ply_2"},
            expected_player_ids=[1, 2],
            server_time_ms=101,
        )
        duplicate = self.collector.record_response(
            session_id="s1",
            batch_id="batch_1",
            player_id=2,
            response={"choice_id": "late"},
            expected_player_ids=[1, 2],
            server_time_ms=102,
        )

        self.assertEqual(first.status, "pending")
        self.assertEqual(first.remaining_player_ids, [2])
        self.assertEqual(second.status, "completed")
        self.assertIsNotNone(second.command)
        self.assertEqual(duplicate.status, "duplicate_completed")
        commands = self.command_store.list_commands("s1")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["type"], "batch_complete")
        self.assertEqual(commands[0]["payload"]["responses_by_player_id"]["1"]["choice_id"], "a")
        self.assertEqual(commands[0]["payload"]["responses_by_player_id"]["2"]["choice_id"], "b")
        self.assertEqual(commands[0]["payload"]["responses_by_public_player_id"]["ply_1"]["choice_id"], "a")
        self.assertEqual(commands[0]["payload"]["responses_by_public_player_id"]["ply_2"]["choice_id"], "b")
        self.assertEqual(commands[0]["payload"]["expected_public_player_ids"], ["ply_1", "ply_2"])
        self.assertEqual(self.command_store.load_command_state("s1", 1)["status"], "accepted")

    def test_timeout_and_human_race_closes_batch_once(self) -> None:
        results = []

        def _record(player_id: int, choice_id: str) -> None:
            results.append(
                self.collector.record_response(
                    session_id="s-race",
                    batch_id="batch_race",
                    player_id=player_id,
                    response={"choice_id": choice_id},
                    expected_player_ids=[1, 2],
                    server_time_ms=200 + player_id,
                )
            )

        threads = [
            threading.Thread(target=_record, args=(1, "human")),
            threading.Thread(target=_record, args=(2, "timeout")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(self.command_store.list_commands("s-race")), 1)
        self.assertEqual(sorted(result.status for result in results), ["completed", "pending"])


if __name__ == "__main__":
    unittest.main()
