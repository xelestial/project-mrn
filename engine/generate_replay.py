"""Phase 2 — Replay artifact generator CLI.

Generates offline replay artifacts from a VisEventStream.

Modes:
  --run-seed SEED   Run one game with the given seed and generate artifacts
  --input PATH      Load events from an existing .jsonl or .json file

Outputs (default: all three):
  --format html       → replay.html  (self-contained interactive viewer)
  --format markdown   → replay.md    (human-readable turn-by-turn)
  --format json       → replay.json  (full event list)
  --format all        → all three

Examples:
  python generate_replay.py --run-seed 42
  python generate_replay.py --run-seed 42 --format html --output replay_42.html
  python generate_replay.py --input events.jsonl --format markdown
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def _run_game(seed: int):
    """Run one deterministic game and return the VisEventStream."""
    sys.path.insert(0, str(Path(__file__).parent))
    from viewer.stream import VisEventStream
    from engine import GameEngine
    from config import DEFAULT_CONFIG
    from ai_policy import HeuristicPolicy

    stream = VisEventStream()
    policy = HeuristicPolicy(
        character_policy_mode="heuristic_v1",
        lap_policy_mode="heuristic_v1",
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return stream


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate offline replay artifacts from a game session.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-seed", type=int, metavar="SEED",
                        help="Run a new game with this RNG seed")
    source.add_argument("--input", metavar="PATH",
                        help="Load events from an existing .jsonl or .json file")

    parser.add_argument("--format", choices=["html", "markdown", "json", "all"],
                        default="all", help="Output format (default: all)")
    parser.add_argument("--output", metavar="PATH",
                        help="Output file path (for single-format mode)")
    parser.add_argument("--out-dir", metavar="DIR", default=".",
                        help="Output directory for multi-format mode (default: current dir)")

    args = parser.parse_args(argv)

    # ── Load / run events ────────────────────────────────────────────────
    sys.path.insert(0, str(Path(__file__).parent))
    from viewer.replay import ReplayProjection

    if args.run_seed is not None:
        print(f"Running game seed={args.run_seed}...", end=" ", flush=True)
        stream = _run_game(args.run_seed)
        events = stream.to_list()
        summary = stream.summary()
        print(f"OK ({summary['total_events']} events)")
    else:
        p = Path(args.input)
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 1
        if p.suffix == ".jsonl":
            proj_tmp = ReplayProjection.from_jsonl(p)
        else:
            proj_tmp = ReplayProjection.from_json(p)
        events = proj_tmp.raw_events()
        print(f"Loaded {len(events)} events from {p}")

    proj = ReplayProjection.from_list(events)
    session = proj.session
    print(f"  session {session.session_id[:8]}  turns={len(proj.turns)}  rounds={len(proj.rounds)}")

    # ── Determine outputs ────────────────────────────────────────────────
    out_dir = Path(args.out_dir)
    sid_short = session.session_id[:8] if session.session_id else "replay"
    seed_tag = f"_seed{args.run_seed}" if args.run_seed is not None else ""
    base = f"replay{seed_tag}_{sid_short}"

    fmt = args.format
    outputs: list[tuple[str, str]] = []  # (format, path)

    if fmt == "all":
        outputs = [
            ("json", str(out_dir / f"{base}.json")),
            ("markdown", str(out_dir / f"{base}.md")),
            ("html", str(out_dir / f"{base}.html")),
        ]
    else:
        path = args.output or str(out_dir / f"{base}.{fmt if fmt != 'markdown' else 'md'}")
        outputs = [(fmt, path)]

    # ── Render and write ─────────────────────────────────────────────────
    for fmt_name, out_path in outputs:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if fmt_name == "json":
            with open(p, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            print(f"  OK JSON  -> {p}")

        elif fmt_name == "markdown":
            from viewer.renderers.markdown_renderer import render_markdown
            md = render_markdown(proj)
            with open(p, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"  OK MD    -> {p}")

        elif fmt_name == "html":
            from viewer.renderers.html_renderer import render_html
            html = render_html(proj)
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  OK HTML  -> {p}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
