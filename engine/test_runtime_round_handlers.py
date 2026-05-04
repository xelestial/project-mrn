from __future__ import annotations


def test_round_frame_handler_registry_covers_native_round_modules() -> None:
    from runtime_modules.handlers.round import ROUND_FRAME_HANDLERS
    from runtime_modules.handlers import build_default_handler_registry
    from runtime_modules.round_modules import ROUND_MODULE_TYPES

    registry = build_default_handler_registry()
    covered = set(ROUND_FRAME_HANDLERS) | {
        module_type for module_type in ROUND_MODULE_TYPES if registry.has(module_type)
    }

    assert set(ROUND_MODULE_TYPES) <= covered
