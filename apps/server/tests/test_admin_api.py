from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from apps.server.src.app import app

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    TestClient = None
    app = None
    FASTAPI_AVAILABLE = False

from apps.server.src.config.runtime_settings import RuntimeSettings
from apps.server.src.core.admin_auth import extract_admin_token
from apps.server.src.services.archive_service import LocalJsonArchiveService
from apps.server.src.services.prompt_service import PromptService
from apps.server.src.services.runtime_service import RuntimeService
from apps.server.src.services.session_service import SessionService
from apps.server.src.services.stream_service import StreamService


def _reset_state(*, admin_token: str = "", archive_dir: str | None = None) -> None:
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
    state.archive_service = (
        LocalJsonArchiveService(
            session_service=state.session_service,
            stream_service=state.stream_service,
            archive_dir=archive_dir,
            game_state_store=_GameStateStoreStub(),
            hot_retention_seconds=300,
        )
        if archive_dir
        else None
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

    def test_admin_token_extraction_prefers_explicit_admin_header(self) -> None:
        self.assertEqual(
            extract_admin_token(x_admin_token=" admin-secret ", authorization="Bearer wrong"),
            "admin-secret",
        )
        self.assertEqual(
            extract_admin_token(x_admin_token=None, authorization="Bearer admin-secret"),
            "admin-secret",
        )
        self.assertEqual(extract_admin_token(x_admin_token=None, authorization="Basic x"), "")

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

    def test_admin_archive_returns_canonical_archive_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _reset_state(admin_token="admin-secret", archive_dir=temp_dir)
            from apps.server.src import state

            session = state.session_service.create_session(
                seats=[
                    {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ],
                config={"seed": 42},
            )
            archive_path = Path(temp_dir) / f"{session.session_id}.json"
            archive_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "schema_name": "mrn.canonical_archive",
                        "visibility": "backend_canonical",
                        "browser_safe": False,
                        "session": {"session_id": session.session_id},
                        "final_state": {"private_hands": {"1": ["hidden-card"]}},
                    }
                ),
                encoding="utf-8",
            )

            response = self.client.get(
                f"/api/v1/admin/sessions/{session.session_id}/archive",
                headers={"X-Admin-Token": "admin-secret"},
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()["data"]
            self.assertEqual(data["schema_name"], "mrn.canonical_archive")
            self.assertFalse(data["browser_safe"])
            self.assertEqual(data["final_state"]["private_hands"], {"1": ["hidden-card"]})

    def test_admin_archive_requires_session_and_existing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _reset_state(admin_token="admin-secret", archive_dir=temp_dir)
            from apps.server.src import state

            session = state.session_service.create_session(
                seats=[
                    {"seat": 1, "seat_type": "ai", "ai_profile": "balanced"},
                    {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                ],
                config={"seed": 42},
            )

            missing = self.client.get(
                f"/api/v1/admin/sessions/{session.session_id}/archive",
                headers={"X-Admin-Token": "admin-secret"},
            )
            unknown_session = self.client.get(
                "/api/v1/admin/sessions/sess_missing/archive",
                headers={"X-Admin-Token": "admin-secret"},
            )

            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["error"]["code"], "ARCHIVE_NOT_FOUND")
            self.assertEqual(unknown_session.status_code, 404)
            self.assertEqual(unknown_session.json()["error"]["code"], "SESSION_NOT_FOUND")


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
        return {"view_state_alias": True}


if __name__ == "__main__":
    unittest.main()
