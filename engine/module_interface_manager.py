from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EngineModuleInterface:
    key: str
    module: str
    attribute: str
    role: str
    expected: str


class EngineModuleInterfaceMismatchError(AssertionError):
    pass


# Engine module interface contract.
# role: why another engine module is allowed to depend on this boundary.
# expected: the behavior tests must update whenever the boundary changes.
ENGINE_MODULE_INTERFACE_CATALOG: tuple[EngineModuleInterface, ...] = (
    EngineModuleInterface(
        key="engine.result.GameResult",
        module="result",
        attribute="GameResult",
        role="Carry the immutable end-of-game summary out of GameEngine.run.",
        expected="Contains winners, end reason, turn counts, final F value, player summaries, and logs.",
    ),
    EngineModuleInterface(
        key="engine.decision_port.DecisionRequest",
        module="decision_port",
        attribute="DecisionRequest",
        role="Describe one policy-facing decision request at the engine boundary.",
        expected="Carries canonical request type, player, round/turn indexes, public context, args, kwargs, and fallback metadata.",
    ),
    EngineModuleInterface(
        key="engine.decision_port.DecisionPort",
        module="decision_port",
        attribute="DecisionPort",
        role="Route engine decisions through the configured policy or injected backend bridge.",
        expected="Calls the named policy method, uses fallback only when the policy method is absent, and otherwise raises AttributeError.",
    ),
    EngineModuleInterface(
        key="engine.decision_port.EngineDecisionResume",
        module="decision_port",
        attribute="EngineDecisionResume",
        role="Carry a backend/frontend decision response back into a suspended engine module.",
        expected="Preserves request id, external player id, request type, choice, resume token, frame/module identity, cursor, and batch id.",
    ),
    EngineModuleInterface(
        key="runtime_modules.contracts.FrameState",
        module="runtime_modules.contracts",
        attribute="FrameState",
        role="Represent a runtime frame that owns a queue of module references.",
        expected="Serializes and hydrates frame id/type, owner, parent, active module, completed modules, status, and creator.",
    ),
    EngineModuleInterface(
        key="runtime_modules.contracts.ModuleRef",
        module="runtime_modules.contracts",
        attribute="ModuleRef",
        role="Represent one queued runtime module and its cursor/idempotency state.",
        expected="Serializes and hydrates module id/type, phase, owner, payload, modifiers, idempotency key, status, cursor, and suspension id.",
    ),
    EngineModuleInterface(
        key="runtime_modules.runner.ModuleRunner",
        module="runtime_modules.runner",
        attribute="ModuleRunner",
        role="Advance exactly one module-runtime transition.",
        expected="Returns a transition status with runner_kind=module and does not bypass frame/module contracts.",
    ),
    EngineModuleInterface(
        key="state.GameState",
        module="state",
        attribute="GameState",
        role="Store canonical mutable engine state and runtime checkpoint fields.",
        expected="Supports create(), to_checkpoint_payload(), and from_checkpoint_payload() for backend persistence.",
    ),
)


def engine_module_interface_catalog() -> tuple[EngineModuleInterface, ...]:
    return ENGINE_MODULE_INTERFACE_CATALOG


def _resolve_attribute(module_name: str, attribute_path: str):
    target = importlib.import_module(module_name)
    for part in attribute_path.split("."):
        target = getattr(target, part)
    return target


def assert_engine_module_interfaces_current(
    catalog: Iterable[EngineModuleInterface] = ENGINE_MODULE_INTERFACE_CATALOG,
) -> None:
    expected_keys = [item.key for item in ENGINE_MODULE_INTERFACE_CATALOG]
    actual = tuple(catalog)
    actual_keys = [item.key for item in actual]
    if actual_keys != expected_keys:
        raise EngineModuleInterfaceMismatchError(
            f"engine module interface keys changed: expected={expected_keys}, actual={actual_keys}"
        )
    for item in actual:
        if not item.role.strip() or not item.expected.strip():
            raise EngineModuleInterfaceMismatchError(f"engine module interface lacks documentation: {item.key}")
        try:
            _resolve_attribute(item.module, item.attribute)
        except (ImportError, AttributeError) as exc:
            raise EngineModuleInterfaceMismatchError(f"engine module interface target missing: {item.key}") from exc

