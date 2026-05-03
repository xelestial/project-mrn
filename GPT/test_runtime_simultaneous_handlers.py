from __future__ import annotations


def test_simultaneous_handler_registry_covers_native_modules() -> None:
    from runtime_modules.handlers.simultaneous import SIMULTANEOUS_FRAME_HANDLERS
    from runtime_modules.simultaneous import SIMULTANEOUS_MODULE_TYPES

    assert set(SIMULTANEOUS_MODULE_TYPES) <= set(SIMULTANEOUS_FRAME_HANDLERS)

