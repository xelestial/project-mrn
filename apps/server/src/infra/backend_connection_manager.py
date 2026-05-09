from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute


@dataclass(frozen=True)
class BackendFrontendRoute:
    key: str
    method: str
    path: str
    role: str
    expected: str


class BackendConnectionCatalogMismatchError(AssertionError):
    pass


# Frontend/backend URL contract.
# role: why this URL exists in the game/client protocol.
# expected: the stable response or behavior a test adapter should assert.
FRONTEND_BACKEND_ROUTE_CATALOG: tuple[BackendFrontendRoute, ...] = (
    BackendFrontendRoute(
        key="health.get",
        method="GET",
        path="/health",
        role="Expose server and storage health to clients and local gates.",
        expected="Returns ok/data/error with status ok or degraded.",
    ),
    BackendFrontendRoute(
        key="admin.recovery",
        method="GET",
        path="/api/v1/admin/sessions/{session_id}/recovery",
        role="Expose a protected recovery checkpoint for backend operators.",
        expected="Returns admin-only recovery payload for an existing session.",
    ),
    BackendFrontendRoute(
        key="admin.archive",
        method="GET",
        path="/api/v1/admin/sessions/{session_id}/archive",
        role="Expose a protected archived session payload for backend operators.",
        expected="Returns the archived JSON object or a typed admin error.",
    ),
    BackendFrontendRoute(
        key="debug.frontend_log",
        method="POST",
        path="/api/v1/debug/frontend-log",
        role="Accept frontend diagnostics for correlation with backend logs.",
        expected="Returns 202 and accepted true after normalizing any JSON payload.",
    ),
    BackendFrontendRoute(
        key="sessions.create",
        method="POST",
        path="/api/v1/sessions",
        role="Create a game session from frontend seat and config payload.",
        expected="Returns host token, join tokens, seats, and parameter manifest data.",
    ),
    BackendFrontendRoute(
        key="sessions.list",
        method="GET",
        path="/api/v1/sessions",
        role="List current sessions for lobby and diagnostics.",
        expected="Returns public session summaries without private identifiers.",
    ),
    BackendFrontendRoute(
        key="sessions.get",
        method="GET",
        path="/api/v1/sessions/{session_id}",
        role="Load public session metadata by id.",
        expected="Returns a public session payload or SESSION_NOT_FOUND.",
    ),
    BackendFrontendRoute(
        key="sessions.join",
        method="POST",
        path="/api/v1/sessions/{session_id}/join",
        role="Attach a frontend player to a reserved session seat.",
        expected="Returns player identity and seat auth data or a typed join error.",
    ),
    BackendFrontendRoute(
        key="sessions.start",
        method="POST",
        path="/api/v1/sessions/{session_id}/start",
        role="Start the game runtime for a prepared session.",
        expected="Publishes initial stream events and returns public session state.",
    ),
    BackendFrontendRoute(
        key="sessions.runtime_status",
        method="GET",
        path="/api/v1/sessions/{session_id}/runtime-status",
        role="Report runtime status and trigger authenticated recovery checks.",
        expected="Returns public runtime status scoped to the supplied session token.",
    ),
    BackendFrontendRoute(
        key="sessions.view_commit",
        method="GET",
        path="/api/v1/sessions/{session_id}/view-commit",
        role="Fetch the latest redacted authoritative view commit.",
        expected="Returns the latest viewer-safe commit or VIEW_COMMIT_NOT_FOUND.",
    ),
    BackendFrontendRoute(
        key="sessions.replay",
        method="GET",
        path="/api/v1/sessions/{session_id}/replay",
        role="Export viewer-safe replay events for a session.",
        expected="Returns redacted replay events for the authenticated viewer.",
    ),
    BackendFrontendRoute(
        key="rooms.create",
        method="POST",
        path="/api/v1/rooms",
        role="Create a multiplayer lobby room before session creation.",
        expected="Returns public room state and host member token.",
    ),
    BackendFrontendRoute(
        key="rooms.list",
        method="GET",
        path="/api/v1/rooms",
        role="List lobby rooms for frontend room discovery.",
        expected="Returns public room summaries.",
    ),
    BackendFrontendRoute(
        key="rooms.get",
        method="GET",
        path="/api/v1/rooms/{room_no}",
        role="Load one lobby room by room number.",
        expected="Returns public room state or ROOM_NOT_FOUND.",
    ),
    BackendFrontendRoute(
        key="rooms.join",
        method="POST",
        path="/api/v1/rooms/{room_no}/join",
        role="Join a lobby room seat before the session starts.",
        expected="Returns updated room state and member token.",
    ),
    BackendFrontendRoute(
        key="rooms.ready",
        method="POST",
        path="/api/v1/rooms/{room_no}/ready",
        role="Toggle a room member ready state.",
        expected="Returns updated public room state.",
    ),
    BackendFrontendRoute(
        key="rooms.leave",
        method="POST",
        path="/api/v1/rooms/{room_no}/leave",
        role="Remove a member from a lobby room.",
        expected="Returns updated public room state.",
    ),
    BackendFrontendRoute(
        key="rooms.resume",
        method="GET",
        path="/api/v1/rooms/{room_no}/resume",
        role="Recover lobby membership from a room member token.",
        expected="Returns resume payload or a typed room resume error.",
    ),
    BackendFrontendRoute(
        key="rooms.start",
        method="POST",
        path="/api/v1/rooms/{room_no}/start",
        role="Convert a ready room into a started game session.",
        expected="Publishes initial stream events and returns room start result.",
    ),
    BackendFrontendRoute(
        key="stream.capability",
        method="GET",
        path="/api/v1/sessions/{session_id}/stream-capability",
        role="Describe stream reconnect and client protocol capabilities.",
        expected="Returns stream capability metadata for the session.",
    ),
    BackendFrontendRoute(
        key="stream.connect",
        method="WEBSOCKET",
        path="/api/v1/sessions/{session_id}/stream",
        role="Carry realtime game events and frontend decisions.",
        expected="Accepts authenticated viewers and emits viewer-safe stream messages.",
    ),
    BackendFrontendRoute(
        key="prompts.debug",
        method="POST",
        path="/api/v1/sessions/{session_id}/prompts/debug",
        role="Inject protected prompt diagnostics for admin-only debugging.",
        expected="Returns created debug prompt metadata or typed admin errors.",
    ),
)


def frontend_backend_route_catalog() -> tuple[BackendFrontendRoute, ...]:
    return FRONTEND_BACKEND_ROUTE_CATALOG


def route_signature(route: BackendFrontendRoute) -> tuple[str, str]:
    return (route.method, route.path)


def catalog_signature_set(
    catalog: Iterable[BackendFrontendRoute] = FRONTEND_BACKEND_ROUTE_CATALOG,
) -> set[tuple[str, str]]:
    return {route_signature(route) for route in catalog}


def app_route_signature_set(app) -> set[tuple[str, str]]:  # noqa: ANN001
    signatures: set[tuple[str, str]] = set()
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        if isinstance(route, APIRoute):
            for method in sorted(route.methods or set()):
                if method not in {"HEAD", "OPTIONS"}:
                    signatures.add((method, path))
            continue
        if isinstance(route, WebSocketRoute):
            signatures.add(("WEBSOCKET", path))
    return signatures


def assert_backend_route_catalog_matches_app(app) -> None:  # noqa: ANN001
    expected = catalog_signature_set()
    actual = app_route_signature_set(app)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise BackendConnectionCatalogMismatchError(
            f"backend route catalog mismatch: missing={missing}, extra={extra}"
        )
