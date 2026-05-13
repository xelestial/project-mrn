from __future__ import annotations

import pytest

from apps.server.src.app import app
from apps.server.src.infra.backend_connection_manager import (
    BackendConnectionCatalogMismatchError,
    assert_backend_route_catalog_matches_app,
    frontend_backend_route_catalog,
)
from apps.server.src.testing.backend_test_adapter import (
    BACKEND_TEST_ADAPTER_ROUTE_CATALOG,
    assert_backend_test_adapter_catalog_current,
)


EXPECTED_FRONTEND_BACKEND_ROUTES = {
    "health.get": (
        "GET",
        "/health",
        "Expose server and storage health to clients and local gates.",
        "Returns ok/data/error with status ok or degraded.",
    ),
    "admin.recovery": (
        "GET",
        "/api/v1/admin/sessions/{session_id}/recovery",
        "Expose a protected recovery checkpoint for backend operators.",
        "Returns admin-only recovery payload for an existing session.",
    ),
    "admin.archive": (
        "GET",
        "/api/v1/admin/sessions/{session_id}/archive",
        "Expose a protected archived session payload for backend operators.",
        "Returns the archived JSON object or a typed admin error.",
    ),
    "debug.frontend_log": (
        "POST",
        "/api/v1/debug/frontend-log",
        "Accept frontend diagnostics for correlation with backend logs.",
        "Returns 202 and accepted true after normalizing any JSON payload.",
    ),
    "sessions.create": (
        "POST",
        "/api/v1/sessions",
        "Create a game session from frontend seat and config payload.",
        "Returns host token, join tokens, seats, and parameter manifest data.",
    ),
    "sessions.list": (
        "GET",
        "/api/v1/sessions",
        "List current sessions for lobby and diagnostics.",
        "Returns public session summaries without private identifiers.",
    ),
    "sessions.get": (
        "GET",
        "/api/v1/sessions/{session_id}",
        "Load public session metadata by id.",
        "Returns a public session payload or SESSION_NOT_FOUND.",
    ),
    "sessions.join": (
        "POST",
        "/api/v1/sessions/{session_id}/join",
        "Attach a frontend player to a reserved session seat.",
        "Returns player identity and seat auth data or a typed join error.",
    ),
    "sessions.start": (
        "POST",
        "/api/v1/sessions/{session_id}/start",
        "Start the game runtime for a prepared session.",
        "Publishes initial stream events and returns public session state.",
    ),
    "sessions.runtime_status": (
        "GET",
        "/api/v1/sessions/{session_id}/runtime-status",
        "Report runtime status and trigger authenticated recovery checks.",
        "Returns public runtime status scoped to the supplied session token.",
    ),
    "sessions.view_commit": (
        "GET",
        "/api/v1/sessions/{session_id}/view-commit",
        "Fetch the latest redacted authoritative view commit.",
        "Returns the latest viewer-safe commit or VIEW_COMMIT_NOT_FOUND.",
    ),
    "sessions.replay": (
        "GET",
        "/api/v1/sessions/{session_id}/replay",
        "Export viewer-safe replay events for a session.",
        "Returns redacted replay events for the authenticated viewer.",
    ),
    "rooms.create": (
        "POST",
        "/api/v1/rooms",
        "Create a multiplayer lobby room before session creation.",
        "Returns public room state and host member token.",
    ),
    "rooms.list": (
        "GET",
        "/api/v1/rooms",
        "List lobby rooms for frontend room discovery.",
        "Returns public room summaries.",
    ),
    "rooms.get": (
        "GET",
        "/api/v1/rooms/{room_no}",
        "Load one lobby room by room number.",
        "Returns public room state or ROOM_NOT_FOUND.",
    ),
    "rooms.join": (
        "POST",
        "/api/v1/rooms/{room_no}/join",
        "Join a lobby room seat before the session starts.",
        "Returns updated room state and member token.",
    ),
    "rooms.ready": (
        "POST",
        "/api/v1/rooms/{room_no}/ready",
        "Toggle a room member ready state.",
        "Returns updated public room state.",
    ),
    "rooms.leave": (
        "POST",
        "/api/v1/rooms/{room_no}/leave",
        "Remove a member from a lobby room.",
        "Returns updated public room state.",
    ),
    "rooms.resume": (
        "GET",
        "/api/v1/rooms/{room_no}/resume",
        "Recover lobby membership from a room member token.",
        "Returns resume payload or a typed room resume error.",
    ),
    "rooms.start": (
        "POST",
        "/api/v1/rooms/{room_no}/start",
        "Convert a ready room into a started game session.",
        "Publishes initial stream events and returns room start result.",
    ),
    "stream.capability": (
        "GET",
        "/api/v1/sessions/{session_id}/stream-capability",
        "Describe stream reconnect and client protocol capabilities.",
        "Returns stream capability metadata for the session.",
    ),
    "stream.connect": (
        "WEBSOCKET",
        "/api/v1/sessions/{session_id}/stream",
        "Carry realtime game events and frontend decisions.",
        "Accepts authenticated viewers and emits viewer-safe stream messages.",
    ),
    "prompts.debug": (
        "POST",
        "/api/v1/sessions/{session_id}/prompts/debug",
        "Inject protected prompt diagnostics for admin-only debugging.",
        "Returns created debug prompt metadata or typed admin errors.",
    ),
    "external_ai.decisions": (
        "POST",
        "/api/v1/sessions/{session_id}/external-ai/decisions",
        "Accept protected external AI decisions into the durable command path.",
        "Returns the decision acceptance status and wakes the session loop after accepted commands.",
    ),
}


def test_frontend_backend_route_catalog_documents_roles_and_expectations() -> None:
    actual = {
        route.key: (route.method, route.path, route.role, route.expected)
        for route in frontend_backend_route_catalog()
    }

    assert actual == EXPECTED_FRONTEND_BACKEND_ROUTES


def test_backend_connection_manager_matches_registered_fastapi_routes() -> None:
    assert_backend_route_catalog_matches_app(app)


def test_backend_test_adapter_is_derived_from_backend_connection_manager() -> None:
    assert BACKEND_TEST_ADAPTER_ROUTE_CATALOG == frontend_backend_route_catalog()
    assert_backend_test_adapter_catalog_current()

    stale_catalog = BACKEND_TEST_ADAPTER_ROUTE_CATALOG[:-1]
    with pytest.raises(BackendConnectionCatalogMismatchError):
        assert_backend_test_adapter_catalog_current(stale_catalog)
