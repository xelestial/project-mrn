from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EngineConnectionPath:
    key: str
    owner: str
    method_name: str
    role: str
    expected: str


class EngineConnectionCatalogMismatchError(AssertionError):
    pass


# Backend/engine contract.
# role: why backend code crosses into the engine boundary here.
# expected: the behavior backend tests must keep synchronized with the path.
ENGINE_CONNECTION_CATALOG: tuple[EngineConnectionPath, ...] = (
    EngineConnectionPath(
        key="engine.import_path",
        owner="RuntimeService",
        method_name="_ensure_engine_import_path",
        role="Put the local engine package at the front of sys.path before engine imports.",
        expected="Imports resolve to the workspace engine package for runtime transitions.",
    ),
    EngineConnectionPath(
        key="engine.config",
        owner="EngineConfigFactory",
        method_name="create",
        role="Translate resolved session parameters into an engine configuration object.",
        expected="Returns a config accepted by GameEngine and GameState hydration.",
    ),
    EngineConnectionPath(
        key="engine.hydrate_state",
        owner="RuntimeService",
        method_name="_hydrate_engine_state",
        role="Load a persisted checkpoint before calling the engine.",
        expected="Returns a GameState instance or None when no usable checkpoint exists.",
    ),
    EngineConnectionPath(
        key="engine.transition_once",
        owner="RuntimeService",
        method_name="_run_engine_transition_once_sync",
        role="Create GameEngine and advance exactly one engine transition.",
        expected="Returns transition status and persists checkpoint/view commit data.",
    ),
    EngineConnectionPath(
        key="engine.recovery_transition",
        owner="RuntimeService",
        method_name="_run_engine_transition_once_for_recovery",
        role="Run one guarded engine transition during runtime recovery.",
        expected="Returns running_elsewhere, unavailable, rejected, stale, or transition result.",
    ),
    EngineConnectionPath(
        key="engine.transition_loop",
        owner="RuntimeService",
        method_name="_run_engine_transition_loop_sync",
        role="Drive repeated engine transitions for a started session runtime.",
        expected="Stops on prompt wait, completion, stale state, or runtime error.",
    ),
    EngineConnectionPath(
        key="engine.run_sync",
        owner="RuntimeService",
        method_name="_run_engine_sync",
        role="Run synchronous engine work from the runtime thread boundary.",
        expected="Returns the runtime execution summary for the session.",
    ),
    EngineConnectionPath(
        key="engine.run_async",
        owner="RuntimeService",
        method_name="_run_engine_async",
        role="Bridge async session start into synchronous engine execution.",
        expected="Updates public runtime status and emits stream-visible state changes.",
    ),
)

_OWNER_IMPORTS = {
    "RuntimeService": "apps.server.src.services.runtime_service:RuntimeService",
    "EngineConfigFactory": "apps.server.src.services.engine_config_factory:EngineConfigFactory",
}


def engine_connection_catalog() -> tuple[EngineConnectionPath, ...]:
    return ENGINE_CONNECTION_CATALOG


def _load_owner(owner: str):
    import_path = _OWNER_IMPORTS.get(owner)
    if import_path is None:
        raise EngineConnectionCatalogMismatchError(f"unknown engine connection owner: {owner}")
    module_name, attr_name = import_path.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def assert_engine_connection_catalog_current(
    catalog: Iterable[EngineConnectionPath] = ENGINE_CONNECTION_CATALOG,
) -> None:
    expected_keys = [path.key for path in ENGINE_CONNECTION_CATALOG]
    actual = tuple(catalog)
    actual_keys = [path.key for path in actual]
    if actual_keys != expected_keys:
        raise EngineConnectionCatalogMismatchError(
            f"engine connection catalog keys changed: expected={expected_keys}, actual={actual_keys}"
        )
    for path in actual:
        if not path.role.strip() or not path.expected.strip():
            raise EngineConnectionCatalogMismatchError(f"engine connection path lacks documentation: {path.key}")
        owner = _load_owner(path.owner)
        target = getattr(owner, path.method_name, None)
        if not callable(target):
            raise EngineConnectionCatalogMismatchError(
                f"engine connection target missing: {path.owner}.{path.method_name}"
            )
