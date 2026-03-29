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


def select_ai_decision_row(
    rows: list[dict],
    *,
    decision_key: str = "",
    player_id: int | None = None,
    row_index: int = 0,
) -> dict | None:
    filtered = []
    for row in rows:
        if decision_key and str(row.get("decision_key", "")) != decision_key:
            continue
        if player_id is not None and int(row.get("player_id", -1)) != player_id:
            continue
        filtered.append(row)
    if row_index < 0 or row_index >= len(filtered):
        return None
    return filtered[row_index]


def _compact_json(value: object, *, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_trace_mermaid(row: dict) -> str:
    trace = ((row.get("payload") or {}).get("trace") or {})
    decision_key = str(row.get("decision_key", "unknown"))
    player_id = row.get("player_id", "?")
    lines = [
        "flowchart LR",
        f'    root["{decision_key} / P{player_id}"]',
        '    features["features"]',
        '    effects["effect_adjustments"]',
        '    final["final_choice"]',
        "    root --> features",
    ]
    feature_items = list((trace.get("features") or {}).items())
    if feature_items:
        for idx, (key, value) in enumerate(feature_items[:8], start=1):
            node = f"feature_{idx}"
            lines.append(f'    {node}["{key}: {_compact_json(value)}"]')
            lines.append(f"    features --> {node}")
    else:
        lines.append('    feature_empty["(none)"]')
        lines.append("    features --> feature_empty")

    detector_hits = list(trace.get("detector_hits") or [])
    if detector_hits:
        lines.append('    detectors["detector_hits"]')
        lines.append("    features --> detectors")
        for idx, hit in enumerate(detector_hits[:8], start=1):
            key = str(hit.get("key", "?"))
            kind = str(hit.get("kind", "?"))
            severity = hit.get("severity", "")
            node = f"detector_{idx}"
            lines.append(f'    {node}["{key}\\n{kind} / severity={severity}"]')
            lines.append(f"    detectors --> {node}")
            lines.append(f"    {node} --> effects")
    else:
        lines.append("    features --> effects")

    effect_items = list(trace.get("effect_adjustments") or [])
    if effect_items:
        for idx, item in enumerate(effect_items[:8], start=1):
            node = f"effect_{idx}"
            if isinstance(item, dict):
                label = f'{item.get("kind", "effect")}: {_compact_json(item.get("value", item.get("values")))}'
            else:
                label = _compact_json(item)
            lines.append(f'    {node}["{label}"]')
            lines.append(f"    effects --> {node}")
            lines.append(f"    {node} --> final")
    else:
        lines.append("    effects --> final")

    lines.append(f'    choice_value["{_compact_json(trace.get("final_choice"))}"]')
    lines.append("    final --> choice_value")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to ai_decisions.jsonl")
    ap.add_argument("--output", default="", help="Optional path to write summary json")
    ap.add_argument("--decision-key", default="", help="Optional decision key filter for mermaid export")
    ap.add_argument("--player-id", type=int, default=None, help="Optional player id filter for mermaid export")
    ap.add_argument("--row-index", type=int, default=0, help="0-based filtered row index for mermaid export")
    ap.add_argument("--mermaid-output", default="", help="Optional path to write a mermaid graph for one decision row")
    args = ap.parse_args()

    rows = _load_rows(args.input)
    summary = summarize_ai_decisions(rows)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.mermaid_output:
        selected = select_ai_decision_row(
            rows,
            decision_key=args.decision_key,
            player_id=args.player_id,
            row_index=args.row_index,
        )
        if selected is None:
            raise SystemExit("No matching ai_decision row found for mermaid export.")
        mermaid_path = Path(args.mermaid_output)
        mermaid_path.parent.mkdir(parents=True, exist_ok=True)
        mermaid_path.write_text(build_trace_mermaid(selected), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
