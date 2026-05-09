from __future__ import annotations

import pytest

from apps.server.src.services.engine_connection_manager import (
    ENGINE_CONNECTION_CATALOG,
    EngineConnectionCatalogMismatchError,
    assert_engine_connection_catalog_current,
    engine_connection_catalog,
)


EXPECTED_ENGINE_CONNECTION_PATHS = {
    "engine.import_path": (
        "RuntimeService",
        "_ensure_engine_import_path",
        "Put the local engine package at the front of sys.path before engine imports.",
        "Imports resolve to the workspace engine package for runtime transitions.",
    ),
    "engine.config": (
        "EngineConfigFactory",
        "create",
        "Translate resolved session parameters into an engine configuration object.",
        "Returns a config accepted by GameEngine and GameState hydration.",
    ),
    "engine.hydrate_state": (
        "RuntimeService",
        "_hydrate_engine_state",
        "Load a persisted checkpoint before calling the engine.",
        "Returns a GameState instance or None when no usable checkpoint exists.",
    ),
    "engine.transition_once": (
        "RuntimeService",
        "_run_engine_transition_once_sync",
        "Create GameEngine and advance exactly one engine transition.",
        "Returns transition status and persists checkpoint/view commit data.",
    ),
    "engine.recovery_transition": (
        "RuntimeService",
        "_run_engine_transition_once_for_recovery",
        "Run one guarded engine transition during runtime recovery.",
        "Returns running_elsewhere, unavailable, rejected, stale, or transition result.",
    ),
    "engine.transition_loop": (
        "RuntimeService",
        "_run_engine_transition_loop_sync",
        "Drive repeated engine transitions for a started session runtime.",
        "Stops on prompt wait, completion, stale state, or runtime error.",
    ),
    "engine.run_sync": (
        "RuntimeService",
        "_run_engine_sync",
        "Run synchronous engine work from the runtime thread boundary.",
        "Returns the runtime execution summary for the session.",
    ),
    "engine.run_async": (
        "RuntimeService",
        "_run_engine_async",
        "Bridge async session start into synchronous engine execution.",
        "Updates public runtime status and emits stream-visible state changes.",
    ),
}


def test_engine_connection_catalog_documents_roles_and_expectations() -> None:
    actual = {
        path.key: (path.owner, path.method_name, path.role, path.expected)
        for path in engine_connection_catalog()
    }

    assert actual == EXPECTED_ENGINE_CONNECTION_PATHS


def test_engine_connection_catalog_targets_existing_backend_methods() -> None:
    assert ENGINE_CONNECTION_CATALOG == engine_connection_catalog()
    assert_engine_connection_catalog_current()

    stale_catalog = ENGINE_CONNECTION_CATALOG[:-1]
    with pytest.raises(EngineConnectionCatalogMismatchError):
        assert_engine_connection_catalog_current(stale_catalog)
