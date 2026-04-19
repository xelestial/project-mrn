
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DOC_MTIME_EPSILON_SECONDS = 1.0
_MODULE_DIR = Path(__file__).resolve().parent

SOURCE_DOC_PAIRS = {
    "ai_policy.py": "ai_policy.md",
    "analyze_strategy_logs.py": "analyze_strategy_logs.md",
    "board_layout_creator.py": "board_layout_creator.md",
    "characters.py": "characters.md",
    "compare_lap_policies.py": "compare_lap_policies.md",
    "compare_mixed_lap_policies.py": "compare_mixed_lap_policies.md",
    "compare_policies.py": "compare_policies.md",
    "config.py": "config.md",
    "engine.py": "engine.md",
    "fortune_cards.py": "fortune_cards.md",
    "game_rules.py": "game_rules.md",
    "game_rules_loader.py": "game_rules_loader.md",
    "main.py": "main.md",
    "metadata.py": "metadata.md",
    "print_settings.py": "print_settings.md",
    "simulate_with_logs.py": "simulate_with_logs.md",
    "state.py": "state.md",
    "stats_utils.py": "stats_utils.md",
    "test_board_layout_creator.py": "test_board_layout_creator.md",
    "test_config_settings.py": "test_config_settings.md",
    "test_draft_three_players.py": "test_draft_three_players.md",
    "test_rule_fixes.py": "test_rule_fixes.md",
    "test_rules_injection.py": "test_rules_injection.md",
    "test_ruleset_loader.py": "test_ruleset_loader.md",
    "trick_cards.py": "trick_cards.md",
    "weather_cards.py": "weather_cards.md",
    "survival_common.py": "survival_common.md",

}

@dataclass(slots=True)
class IntegrityItem:
    source: str
    doc: str
    source_mtime: float | None
    doc_mtime: float | None
    ok: bool
    reason: str


def iter_integrity_items(root: str | Path = ".") -> list[IntegrityItem]:
    root = _MODULE_DIR if str(root) == "." else Path(root)
    items: list[IntegrityItem] = []
    for source_name, doc_name in SOURCE_DOC_PAIRS.items():
        src = root / source_name
        doc = root / doc_name
        if not src.exists():
            items.append(IntegrityItem(source_name, doc_name, None, None, False, "missing_source"))
            continue
        if not doc.exists():
            items.append(IntegrityItem(source_name, doc_name, src.stat().st_mtime, None, False, "missing_doc"))
            continue
        src_m = src.stat().st_mtime
        doc_m = doc.stat().st_mtime
        ok = doc_m + DOC_MTIME_EPSILON_SECONDS >= src_m
        items.append(IntegrityItem(source_name, doc_name, src_m, doc_m, ok, "ok" if ok else "doc_older_than_source"))
    return items


def summarize_integrity(root: str | Path = ".") -> dict:
    items = iter_integrity_items(root)
    failing = [
        {
            "source": i.source,
            "doc": i.doc,
            "reason": i.reason,
            "source_mtime": i.source_mtime,
            "doc_mtime": i.doc_mtime,
        }
        for i in items if not i.ok
    ]
    return {
        "checked_pairs": len(items),
        "ok": not failing,
        "failures": failing,
    }
