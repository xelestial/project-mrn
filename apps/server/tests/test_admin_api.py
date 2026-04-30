from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from apps.server.src.app import app

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    TestClient = None
    app = None
    FASTAPI_AVAILABLE = False

from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService


def _reset_state(*, admin_token: str = "") -> None:
    from apps.server.src import state

    state.session_service = SessionService()
    state.stream_service = StreamService()
    state.prompt_service = PromptService()
    state.runtime_settings = RuntimeSettings(admin_token=admin_token)
    state.runtime_service = RuntimeService(
        session_service=state.session_service,
        stream_service=state.stream_service,
        prompt_service=state.prompt_service,
        game_state_store=_GameStateStoreStub(),
    )


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class AdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_state(admin_token="admin-secret")
        self.client = TestClient(app)

    def test_admin_recovery_requires_configured_admin_token(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        missing = self.client.get(f"/api/v1/admin/sessions/{session.session_id}/recovery")
        wrong = self.client.get(
            f"/api/v1/admin/sessions/{session.session_id}/recovery",
            headers={"X-Admin-Token": "wrong"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json()["error"]["code"], "ADMIN_UNAUTHORIZED")

    def test_admin_recovery_returns_canonical_recovery_with_admin_schema(self) -> None:
        from apps.server.src import state

        session = state.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        response = self.client.get(
            f"/api/v1/admin/sessions/{session.session_id}/recovery",
            headers={"Authorization": "Bearer admin-secret"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["schema_name"], "mrn.admin_recovery")
        self.assertEqual(data["visibility"], "admin")
        self.assertFalse(data["browser_safe"])
        self.assertEqual(data["recovery_checkpoint"]["current_state"]["private_hands"], {"1": ["hidden-card"]})

    def test_admin_recovery_is_disabled_without_configured_token(self) -> None:
        from apps.server.src import state

        _reset_state(admin_token="")
        session = state.session_service.create_session(
            seats=[
                {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
            ],
            config={"seed": 42},
        )

        response = self.client.get(
            f"/api/v1/admin/sessions/{session.session_id}/recovery",
            headers={"X-Admin-Token": "admin-secret"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "ADMIN_AUTH_DISABLED")


class _GameStateStoreStub:
    def load_checkpoint(self, session_id: str) -> dict:
        return {
            "schema_version": 1,
            "session_id": session_id,
            "latest_seq": 12,
            "turn_index": 3,
        }

    def load_current_state(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "turn_index": 3,
            "private_hands": {"1": ["hidden-card"]},
        }

    def load_projected_view_state(self, session_id: str, viewer: str, *, player_id: int | None = None) -> dict:
        del session_id, player_id
        if viewer == "public":
            return {"players": {"items": []}}
        return {}

    def load_view_state(self, session_id: str) -> dict:
        del session_id
        return {"legacy": True}


if __name__ == "__main__":
    unittest.main()
