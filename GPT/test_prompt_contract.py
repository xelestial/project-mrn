from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from viewer.prompt_contract import build_prompt_envelope, extract_choice_id


def test_extract_choice_id_prefers_choice_id_over_legacy_option_id() -> None:
    payload = {"choice_id": "canonical_move", "option_id": "legacy_move"}
    assert extract_choice_id(payload) == "canonical_move"


def test_extract_choice_id_uses_legacy_option_id_as_fallback() -> None:
    payload = {"option_id": "legacy_move"}
    assert extract_choice_id(payload) == "legacy_move"


def test_build_prompt_envelope_preserves_choice_identity_without_label_coupling() -> None:
    envelope = build_prompt_envelope(
        request_type="movement",
        player_id=1,
        legal_choices=[
            {"choice_id": "move_card_1", "label": "이동 카드 1", "value": {"card": 1}},
            {"choice_id": "move_dice", "label": "주사위 굴리기", "value": {"roll": True}},
        ],
        public_context={"round_index": 2},
        can_pass=False,
        timeout_ms=30000,
        fallback_policy="ai",
    )
    choice_ids = [choice.get("choice_id") for choice in envelope["legal_choices"]]
    assert choice_ids == ["move_card_1", "move_dice"]
