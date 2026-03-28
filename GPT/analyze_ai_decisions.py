from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _load_rows(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize_ai_decisions(rows: list[dict]) -> dict:
    by_decision = Counter()
    by_player = Counter()
    detector_hits = Counter()
    detector_hits_by_decision: dict[str, Counter] = defaultdict(Counter)
    final_choice_names: dict[str, Counter] = defaultdict(Counter)

    for row in rows:
        decision_key = str(row.get("decision_key", ""))
        if not decision_key:
            continue
        by_decision[decision_key] += 1
        by_player[str(row.get("player_id", "?"))] += 1
        trace = (row.get("payload") or {}).get("trace") or {}
        for hit in trace.get("detector_hits", []):
            key = str(hit.get("key", ""))
            if not key:
                continue
            detector_hits[key] += 1
            detector_hits_by_decision[decision_key][key] += 1
        final_choice = trace.get("final_choice")
        if isinstance(final_choice, dict):
            label = (
                final_choice.get("name")
                or final_choice.get("key")
                or final_choice.get("decision")
                or final_choice.get("card_values")
            )
            if label is not None:
                final_choice_names[decision_key][json.dumps(label, ensure_ascii=False)] += 1
        elif final_choice is not None:
            final_choice_names[decision_key][json.dumps(final_choice, ensure_ascii=False)] += 1

    return {
        "rows": len(rows),
        "decision_counts": dict(by_decision.most_common()),
        "player_counts": dict(by_player.most_common()),
        "detector_hits": dict(detector_hits.most_common()),
        "detector_hits_by_decision": {
            key: dict(counter.most_common())
            for key, counter in detector_hits_by_decision.items()
        },
        "top_final_choices_by_decision": {
            key: dict(counter.most_common(10))
            for key, counter in final_choice_names.items()
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to ai_decisions.jsonl")
    ap.add_argument("--output", default="", help="Optional path to write summary json")
    args = ap.parse_args()

    rows = _load_rows(args.input)
    summary = summarize_ai_decisions(rows)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
