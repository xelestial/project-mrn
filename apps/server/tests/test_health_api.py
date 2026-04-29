from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from apps.server.src.app import app
import apps.server.src.state as state


class HealthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_reports_current_storage_backends(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertIn("sessions", payload["data"]["storage"])
        self.assertIn("rooms", payload["data"]["storage"])
        self.assertIn("streams", payload["data"]["storage"])

    def test_health_returns_503_when_redis_is_configured_but_unhealthy(self) -> None:
        before_connection = state.redis_connection
        before_session_backend = state.session_storage_backend
        before_room_backend = state.room_storage_backend
        before_stream_backend = state.stream_storage_backend

        class _BrokenRedisConnection:
            settings = SimpleNamespace(key_prefix="mrn-test")

            def health_check(self) -> dict[str, object]:
                raise RuntimeError("redis_down")

        state.redis_connection = _BrokenRedisConnection()
        state.session_storage_backend = "redis"
        state.room_storage_backend = "redis"
        state.stream_storage_backend = "memory"
        try:
            response = self.client.get("/health")
        finally:
            state.redis_connection = before_connection
            state.session_storage_backend = before_session_backend
            state.room_storage_backend = before_room_backend
            state.stream_storage_backend = before_stream_backend

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertEqual(payload["error"]["code"], "REDIS_UNAVAILABLE")
        self.assertEqual(payload["data"]["redis"]["ok"], False)


if __name__ == "__main__":
    unittest.main()
