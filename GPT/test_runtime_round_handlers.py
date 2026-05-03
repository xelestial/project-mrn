from __future__ import annotations


def test_round_frame_handler_registry_covers_native_round_modules() -> None:
    from runtime_modules.handlers.round import ROUND_FRAME_HANDLERS
    from runtime_modules.round_modules import ROUND_MODULE_TYPES

    assert set(ROUND_MODULE_TYPES) <= set(ROUND_FRAME_HANDLERS)
