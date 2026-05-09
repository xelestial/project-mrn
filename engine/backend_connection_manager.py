from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class BackendEngineConnection:
    key: str
    module: str
    attribute: str
    role: str
    expected: str


class BackendEngineConnectionMismatchError(AssertionError):
    pass


# Backend/engine connection contract.
# role: why backend code is allowed to cross into this engine boundary.
# expected: the behavior backend and engine tests must update together.
BACKEND_ENGINE_CONNECTION_CATALOG: tuple[BackendEngineConnection, ...] = (
    BackendEngineConnection(
        key="backend.engine.GameEngine",
        module="engine",
        attribute="GameEngine",
        role="Backend constructs a gameplay authority for each runtime transition.",
        expected="Constructor accepts config, policy, rng, event stream, and optional backend decision port.",
    ),
    BackendEngineConnection(
        key="backend.engine.GameEngine.run_next_transition",
        module="engine",
        attribute="GameEngine.run_next_transition",
        role="Backend advances one persisted runtime transition.",
        expected="Returns completed, committed, waiting_input, failed, rejected, stale, or unavailable transition status.",
    ),
    BackendEngineConnection(
        key="backend.state.GameState",
        module="state",
        attribute="GameState",
        role="Backend hydrates and saves engine checkpoints through this state type.",
        expected="Supports checkpoint payload round-trip with runtime frame, prompt, and RNG fields intact.",
    ),
    BackendEngineConnection(
        key="backend.policy.PolicyFactory.create_runtime_policy",
        module="policy.factory",
        attribute="PolicyFactory.create_runtime_policy",
        role="Backend builds the configured runtime policy before constructing GameEngine.",
        expected="Returns a policy accepted by GameEngine and compatible with DecisionPort requests.",
    ),
    BackendEngineConnection(
        key="backend.prompts.validate_resume",
        module="runtime_modules.prompts",
        attribute="validate_resume",
        role="Backend validates submitted decisions against the suspended module continuation.",
        expected="Rejects request, token, frame, module, cursor, player, or choice mismatches before engine resume.",
    ),
)


def backend_engine_connection_catalog() -> tuple[BackendEngineConnection, ...]:
    return BACKEND_ENGINE_CONNECTION_CATALOG


def _resolve_attribute(module_name: str, attribute_path: str):
    target = importlib.import_module(module_name)
    for part in attribute_path.split("."):
        target = getattr(target, part)
    return target


def assert_backend_engine_connection_catalog_current(
    catalog: Iterable[BackendEngineConnection] = BACKEND_ENGINE_CONNECTION_CATALOG,
) -> None:
    expected_keys = [item.key for item in BACKEND_ENGINE_CONNECTION_CATALOG]
    actual = tuple(catalog)
    actual_keys = [item.key for item in actual]
    if actual_keys != expected_keys:
        raise BackendEngineConnectionMismatchError(
            f"backend engine connection keys changed: expected={expected_keys}, actual={actual_keys}"
        )
    for item in actual:
        if not item.role.strip() or not item.expected.strip():
            raise BackendEngineConnectionMismatchError(f"backend engine connection lacks documentation: {item.key}")
        try:
            target = _resolve_attribute(item.module, item.attribute)
        except (ImportError, AttributeError) as exc:
            raise BackendEngineConnectionMismatchError(f"backend engine connection target missing: {item.key}") from exc
        if item.attribute.endswith("run_next_transition") and not callable(target):
            raise BackendEngineConnectionMismatchError(f"backend engine connection target is not callable: {item.key}")

