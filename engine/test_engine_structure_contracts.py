from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


from backend_connection_manager import (
    BACKEND_ENGINE_CONNECTION_CATALOG,
    assert_backend_engine_connection_catalog_current,
    backend_engine_connection_catalog,
)
from module_interface_manager import (
    ENGINE_MODULE_INTERFACE_CATALOG,
    assert_engine_module_interfaces_current,
    engine_module_interface_catalog,
)


EXPECTED_ENGINE_MODULE_INTERFACES = {
    "engine.result.GameResult": {
        "module": "result",
        "attribute": "GameResult",
        "role": "Carry the immutable end-of-game summary out of GameEngine.run.",
        "expected": "Contains winners, end reason, turn counts, final F value, player summaries, and logs.",
    },
    "engine.decision_port.DecisionRequest": {
        "module": "decision_port",
        "attribute": "DecisionRequest",
        "role": "Describe one policy-facing decision request at the engine boundary.",
        "expected": "Carries canonical request type, player, round/turn indexes, public context, args, kwargs, and fallback metadata.",
    },
    "engine.decision_port.DecisionPort": {
        "module": "decision_port",
        "attribute": "DecisionPort",
        "role": "Route engine decisions through the configured policy or injected backend bridge.",
        "expected": "Calls the named policy method, uses fallback only when the policy method is absent, and otherwise raises AttributeError.",
    },
    "engine.decision_port.EngineDecisionResume": {
        "module": "decision_port",
        "attribute": "EngineDecisionResume",
        "role": "Carry a backend/frontend decision response back into a suspended engine module.",
        "expected": "Preserves request id, external player id, request type, choice, resume token, frame/module identity, cursor, and batch id.",
    },
    "runtime_modules.contracts.FrameState": {
        "module": "runtime_modules.contracts",
        "attribute": "FrameState",
        "role": "Represent a runtime frame that owns a queue of module references.",
        "expected": "Serializes and hydrates frame id/type, owner, parent, active module, completed modules, status, and creator.",
    },
    "runtime_modules.contracts.ModuleRef": {
        "module": "runtime_modules.contracts",
        "attribute": "ModuleRef",
        "role": "Represent one queued runtime module and its cursor/idempotency state.",
        "expected": "Serializes and hydrates module id/type, phase, owner, payload, modifiers, idempotency key, status, cursor, and suspension id.",
    },
    "runtime_modules.runner.ModuleRunner": {
        "module": "runtime_modules.runner",
        "attribute": "ModuleRunner",
        "role": "Advance exactly one module-runtime transition.",
        "expected": "Returns a transition status with runner_kind=module and does not bypass frame/module contracts.",
    },
    "state.GameState": {
        "module": "state",
        "attribute": "GameState",
        "role": "Store canonical mutable engine state and runtime checkpoint fields.",
        "expected": "Supports create(), to_checkpoint_payload(), and from_checkpoint_payload() for backend persistence.",
    },
}


EXPECTED_BACKEND_ENGINE_CONNECTIONS = {
    "backend.engine.GameEngine": {
        "module": "engine",
        "attribute": "GameEngine",
        "role": "Backend constructs a gameplay authority for each runtime transition.",
        "expected": "Constructor accepts config, policy, rng, event stream, and optional backend decision port.",
    },
    "backend.engine.GameEngine.run_next_transition": {
        "module": "engine",
        "attribute": "GameEngine.run_next_transition",
        "role": "Backend advances one persisted runtime transition.",
        "expected": "Returns completed, committed, waiting_input, failed, rejected, stale, or unavailable transition status.",
    },
    "backend.state.GameState": {
        "module": "state",
        "attribute": "GameState",
        "role": "Backend hydrates and saves engine checkpoints through this state type.",
        "expected": "Supports checkpoint payload round-trip with runtime frame, prompt, and RNG fields intact.",
    },
    "backend.policy.PolicyFactory.create_runtime_policy": {
        "module": "policy.factory",
        "attribute": "PolicyFactory.create_runtime_policy",
        "role": "Backend builds the configured runtime policy before constructing GameEngine.",
        "expected": "Returns a policy accepted by GameEngine and compatible with DecisionPort requests.",
    },
    "backend.prompts.validate_resume": {
        "module": "runtime_modules.prompts",
        "attribute": "validate_resume",
        "role": "Backend validates submitted decisions against the suspended module continuation.",
        "expected": "Rejects request, token, frame, module, cursor, player, or choice mismatches before engine resume.",
    },
}


def _catalog_dict(catalog):
    return {
        item.key: {
            "module": item.module,
            "attribute": item.attribute,
            "role": item.role,
            "expected": item.expected,
        }
        for item in catalog
    }


def test_engine_module_interface_catalog_documents_expected_boundaries() -> None:
    assert _catalog_dict(ENGINE_MODULE_INTERFACE_CATALOG) == EXPECTED_ENGINE_MODULE_INTERFACES


def test_engine_module_interface_catalog_targets_exist() -> None:
    assert ENGINE_MODULE_INTERFACE_CATALOG == engine_module_interface_catalog()
    assert_engine_module_interfaces_current()


def test_backend_engine_connection_catalog_documents_backend_entrypoints() -> None:
    assert _catalog_dict(BACKEND_ENGINE_CONNECTION_CATALOG) == EXPECTED_BACKEND_ENGINE_CONNECTIONS


def test_backend_engine_connection_catalog_targets_exist() -> None:
    assert BACKEND_ENGINE_CONNECTION_CATALOG == backend_engine_connection_catalog()
    assert_backend_engine_connection_catalog_current()

