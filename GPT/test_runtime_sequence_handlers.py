from __future__ import annotations


def test_sequence_handler_registry_covers_trick_modules_and_payload_boundaries() -> None:
    from runtime_modules.handlers.sequence import SEQUENCE_FRAME_HANDLERS, SEQUENCE_PAYLOAD_HANDLERS
    from runtime_modules.sequence_modules import TRICK_SEQUENCE_MODULE_TYPES

    assert set(TRICK_SEQUENCE_MODULE_TYPES) <= set(SEQUENCE_FRAME_HANDLERS)
    assert "action" in SEQUENCE_PAYLOAD_HANDLERS
    assert "pending_turn_completion" in SEQUENCE_PAYLOAD_HANDLERS

