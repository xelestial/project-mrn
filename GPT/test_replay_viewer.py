"""Phase 2 — ReplayProjection + renderer tests.

Tests:
1. ReplayProjection correctly groups events into turns
2. All turns have acting_player_id and round_index
3. Turns with turn_end_snapshot have non-empty player_states and board_state
4. key_events excludes scaffolding events
5. markdown_renderer produces non-empty output with turn headers
6. html_renderer produces valid HTML with embedded JSON
7. Full round-trip: run a game → stream → projection → render (no crash)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from viewer.stream import VisEventStream
from viewer.replay import ReplayProjection, TurnReplay
from viewer.renderers.markdown_renderer import render_markdown
from viewer.renderers.html_renderer import render_html


# ── Helpers ─────────────────────────────────────────────────────────────────

def _run_game(seed: int) -> VisEventStream:
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


# ── Tests ────────────────────────────────────────────────────────────────────

def test_projection_basic(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)

    if not proj.turns:
        errors.append("No turns produced")
        return errors

    for turn in proj.turns:
        if not isinstance(turn, TurnReplay):
            errors.append(f"turn is not TurnReplay: {type(turn)}")
        if turn.turn_index <= 0:
            errors.append(f"Invalid turn_index: {turn.turn_index}")
        if turn.round_index <= 0:
            errors.append(f"Invalid round_index at turn {turn.turn_index}: {turn.round_index}")

    return errors


def test_snapshots(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)

    snapshot_count = 0
    for turn in proj.turns:
        if turn.skipped:
            continue
        if turn.snapshot is not None:
            snapshot_count += 1
            players = turn.player_states
            board = turn.board_state
            if not players:
                errors.append(f"Turn {turn.turn_index}: snapshot has no players")
            if board is None:
                errors.append(f"Turn {turn.turn_index}: snapshot has no board")
            else:
                tiles = board.get("tiles", [])
                if len(tiles) != 40:
                    errors.append(
                        f"Turn {turn.turn_index}: board has {len(tiles)} tiles (expected 40)"
                    )

    if snapshot_count == 0:
        errors.append("No turns have snapshots — turn_end_snapshot events may be missing")

    return errors


def test_key_events(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)
    SKIP = {"session_start", "round_start", "turn_start", "turn_end_snapshot",
            "trick_window_open", "trick_window_closed"}

    for turn in proj.turns:
        for e in turn.key_events:
            if e.get("event_type") in SKIP:
                errors.append(
                    f"key_events includes scaffolding event: {e.get('event_type')} "
                    f"at turn {turn.turn_index}"
                )

    return errors


def test_rounds(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)

    if not proj.rounds:
        errors.append("No rounds produced")
        return errors

    for rnd in proj.rounds:
        if rnd.round_index <= 0:
            errors.append(f"Invalid round_index: {rnd.round_index}")

    # Every turn should belong to a round
    round_turns = {id(t) for r in proj.rounds for t in r.turns}
    orphans = [t for t in proj.turns if id(t) not in round_turns]
    if orphans:
        errors.append(f"{len(orphans)} turns not assigned to any round")

    return errors


def test_markdown_renderer(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)
    md = render_markdown(proj)

    if not md:
        errors.append("markdown output is empty")
        return errors

    if "# 게임 리플레이" not in md:
        errors.append("markdown missing header")
    if "## Round" not in md:
        errors.append("markdown missing round headers")
    if "### Turn" not in md:
        errors.append("markdown missing turn headers")

    return errors


def test_html_renderer(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)
    html = render_html(proj)

    if not html:
        errors.append("HTML output is empty")
        return errors

    if "<!DOCTYPE html>" not in html:
        errors.append("HTML missing DOCTYPE")
    if "const TURNS = " not in html:
        errors.append("HTML missing TURNS JSON")
    if "const META = " not in html:
        errors.append("HTML missing META JSON")

    # Verify embedded JSON is valid
    import re
    turns_match = re.search(r"const TURNS = (\[.*?\]);", html, re.DOTALL)
    if turns_match:
        try:
            parsed = json.loads(turns_match.group(1))
            if not isinstance(parsed, list):
                errors.append("TURNS JSON is not a list")
        except json.JSONDecodeError as exc:
            errors.append(f"TURNS JSON parse error: {exc}")
    else:
        errors.append("Could not extract TURNS JSON from HTML")

    return errors


def test_jsonl_roundtrip(events: list[dict]) -> list[str]:
    """Write to JSONL, reload, check turn count matches."""
    import tempfile, os
    errors: list[str] = []

    proj_orig = ReplayProjection.from_list(events)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                     encoding="utf-8", delete=False) as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp_path = f.name

    try:
        proj_loaded = ReplayProjection.from_jsonl(tmp_path)
        if len(proj_loaded.turns) != len(proj_orig.turns):
            errors.append(
                f"JSONL roundtrip turn count mismatch: "
                f"{len(proj_orig.turns)} vs {len(proj_loaded.turns)}"
            )
    finally:
        os.unlink(tmp_path)

    return errors


# ── Main ─────────────────────────────────────────────────────────────────────

def run_suite(seed: int) -> tuple[bool, list[str]]:
    print(f"  seed={seed}: running game...", end=" ", flush=True)
    stream = _run_game(seed)
    events = stream.to_list()
    summary = stream.summary()
    print(f"OK ({summary['total_events']} events, {len(proj_turns_preview(events))} turns)")

    all_errors: list[str] = []
    tests = [
        ("projection_basic", test_projection_basic),
        ("snapshots", test_snapshots),
        ("key_events", test_key_events),
        ("rounds", test_rounds),
        ("markdown_renderer", test_markdown_renderer),
        ("html_renderer", test_html_renderer),
        ("jsonl_roundtrip", test_jsonl_roundtrip),
    ]
    for name, fn in tests:
        errs = fn(events)
        if errs:
            all_errors += [f"[{name}] {e}" for e in errs]
            print(f"    FAIL {name}: {len(errs)} error(s)")
            for e in errs:
                print(f"      {e}")
        else:
            print(f"    OK   {name}")

    return len(all_errors) == 0, all_errors


def proj_turns_preview(events: list[dict]) -> list:
    return ReplayProjection.from_list(events).turns


def main() -> int:
    seeds = [42, 137, 999]
    all_passed = True
    for seed in seeds:
        print(f"\nSeed {seed}:")
        passed, errors = run_suite(seed)
        if not passed:
            all_passed = False

    if all_passed:
        print("\nPhase 2: ALL TESTS PASSED")
        return 0
    else:
        print("\nPhase 2: TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
