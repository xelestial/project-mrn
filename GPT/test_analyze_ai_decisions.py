import json
from pathlib import Path

from analyze_ai_decisions import summarize_ai_decisions


def test_summarize_ai_decisions_groups_detector_hits_and_choices(tmp_path: Path) -> None:
    rows = [
        {
            "decision_key": "movement_decision",
            "player_id": 1,
            "payload": {
                "trace": {
                    "detector_hits": [{"key": "hold_cards_default"}, {"key": "preserve_cards_bias"}],
                    "final_choice": {"use_cards": False, "decision": False},
                }
            },
        },
        {
            "decision_key": "movement_decision",
            "player_id": 1,
            "payload": {
                "trace": {
                    "detector_hits": [{"key": "hold_cards_default"}],
                    "final_choice": {"use_cards": False, "decision": False},
                }
            },
        },
        {
            "decision_key": "purchase_decision",
            "player_id": 2,
            "payload": {
                "trace": {
                    "detector_hits": [{"key": "avoid_cleanup_soft_block"}],
                    "final_choice": {"decision": False},
                }
            },
        },
    ]
    path = tmp_path / "ai_decisions.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    summary = summarize_ai_decisions(rows)

    assert summary["rows"] == 3
    assert summary["decision_counts"]["movement_decision"] == 2
    assert summary["detector_hits"]["hold_cards_default"] == 2
    assert summary["detector_hits_by_decision"]["purchase_decision"]["avoid_cleanup_soft_block"] == 1
