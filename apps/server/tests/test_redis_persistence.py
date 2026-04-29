from __future__ import annotations

import unittest

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.persistence import RedisRoomStore, RedisSessionStore
from apps.server.src.services.room_service import RoomService
from apps.server.src.services.session_service import SessionService


def _seats() -> list[dict]:
    return [
        {"seat": 1, "seat_type": "human"},
        {"seat": 2, "seat_type": "human"},
        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
    ]


class RedisPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_redis = _FakeRedis()
        self.connection = RedisConnection(
            RedisConnectionSettings(
                url="redis://127.0.0.1:6379/9",
                key_prefix="mrn-test",
                socket_timeout_ms=250,
            ),
            client_factory=lambda: self.fake_redis,
        )

    def test_health_check_reports_version_and_database(self) -> None:
        health = self.connection.health_check()
        self.assertEqual(health["configured"], True)
        self.assertEqual(health["ok"], True)
        self.assertEqual(health["version"], "7.4.8")
        self.assertEqual(health["database"], 9)
        self.assertEqual(health["key_prefix"], "mrn-test")

    def test_session_store_survives_service_reconstruction(self) -> None:
        store = RedisSessionStore(self.connection)
        first = SessionService(session_store=store, restart_recovery_policy="keep")
        created = first.create_session(_seats(), config={"seed": 42})
        joined = first.join_session(created.session_id, 1, created.join_tokens[1], "Host")
        first.join_session(created.session_id, 2, created.join_tokens[2], "Guest")
        first.start_session(created.session_id, created.host_token)

        second = SessionService(session_store=store, restart_recovery_policy="keep")
        restored = second.get_session(created.session_id)
        self.assertEqual(restored.status.value, "in_progress")
        self.assertEqual(restored.seats[0].display_name, "Host")
        self.assertEqual(restored.seats[1].display_name, "Guest")
        self.assertEqual(restored.session_tokens[1], joined["session_token"])

    def test_room_store_survives_service_reconstruction(self) -> None:
        session_store = RedisSessionStore(self.connection)
        room_store = RedisRoomStore(self.connection)

        first_sessions = SessionService(session_store=session_store, restart_recovery_policy="keep")
        first_rooms = RoomService(session_service=first_sessions, room_store=room_store)
        created = first_rooms.create_room(
            room_title="Redis Room",
            seats=_seats(),
            host_seat=1,
            nickname="Host",
            config={"seed": 7},
        )
        host_token = created["room_member_token"]
        guest = first_rooms.join_room(room_no=1, seat=2, nickname="Guest")
        guest_token = guest["room_member_token"]
        first_rooms.set_ready(room_no=1, room_member_token=host_token, ready=True)
        first_rooms.set_ready(room_no=1, room_member_token=guest_token, ready=True)
        started = first_rooms.start_room(room_no=1, room_member_token=host_token)

        second_sessions = SessionService(session_store=session_store, restart_recovery_policy="keep")
        second_rooms = RoomService(session_service=second_sessions, room_store=room_store)

        restored_room = second_rooms.get_room(1)
        self.assertEqual(restored_room.status.value, "in_progress")
        self.assertEqual(restored_room.session_id, started["session_id"])
        self.assertEqual(restored_room.seats[0].nickname, "Host")
        self.assertEqual(restored_room.seats[1].nickname, "Guest")

        second_created = second_rooms.create_room(
            room_title="Redis Room 2",
            seats=_seats(),
            host_seat=1,
            nickname="Another Host",
            config={"seed": 11},
        )
        self.assertEqual(second_created["room"]["room_no"], 2)


class _FakeRedisPipeline:
    def __init__(self, client: "_FakeRedis") -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def delete(self, *keys: str) -> "_FakeRedisPipeline":
        self._ops.append(("delete", keys, {}))
        return self

    def hset(self, name: str, key: str | None = None, value: str | None = None, mapping: dict[str, str] | None = None) -> "_FakeRedisPipeline":
        self._ops.append(("hset", (name,), {"key": key, "value": value, "mapping": mapping}))
        return self

    def set(self, name: str, value: str) -> "_FakeRedisPipeline":
        self._ops.append(("set", (name, value), {}))
        return self

    def execute(self) -> list[object]:
        results: list[object] = []
        for name, args, kwargs in self._ops:
            method = getattr(self._client, name)
            results.append(method(*args, **kwargs))
        self._ops.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}

    def ping(self) -> bool:
        return True

    def info(self, section: str | None = None) -> dict[str, object]:
        return {"redis_version": "7.4.8"}

    def close(self) -> None:
        return None

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._strings:
                del self._strings[key]
                removed += 1
            if key in self._hashes:
                del self._hashes[key]
                removed += 1
        return removed

    def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        bucket = self._hashes.setdefault(name, {})
        written = 0
        if mapping:
            for item_key, item_value in mapping.items():
                bucket[str(item_key)] = str(item_value)
                written += 1
        elif key is not None and value is not None:
            bucket[str(key)] = str(value)
            written += 1
        return written

    def hgetall(self, name: str) -> dict[str, str]:
        return dict(self._hashes.get(name, {}))

    def set(self, name: str, value: str) -> bool:
        self._strings[name] = str(value)
        return True

    def get(self, name: str) -> str | None:
        return self._strings.get(name)


if __name__ == "__main__":
    unittest.main()
