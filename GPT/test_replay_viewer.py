"""Phase 2 replay projection and renderer tests."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from viewer.renderers.html_renderer import render_html
from viewer.renderers.markdown_renderer import render_markdown
from viewer.replay import ReplayProjection, TurnReplay
from viewer.stream import VisEventStream


def _run_game(seed: int) -> VisEventStream:
    from ai_policy import HeuristicPolicy
    from config import DEFAULT_CONFIG
    from engine import GameEngine

    stream = VisEventStream()
    policy = HeuristicPolicy(
        character_policy_mode="heuristic_v1",
        lap_policy_mode="heuristic_v1",
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return stream


def test_projection_basic(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)

    session_start = proj.session.session_start
    players = session_start.get("players", [])
    if not players:
        errors.append("session_start missing initial public players")
    elif len(players) != session_start.get("player_count"):
        errors.append("session_start players length does not match player_count")

    if not proj.turns:
        errors.append("No turns produced")
        return errors

    if proj.turn_count != len(proj.turns):
        errors.append("turn_count property mismatch")
    if proj.round_count != len(proj.rounds):
        errors.append("round_count property mismatch")

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
        errors.append("No turns have snapshots")

    return errors


def test_key_events(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)
    skip = {
        "session_start",
        "round_start",
        "turn_start",
        "turn_end_snapshot",
        "trick_window_open",
        "trick_window_closed",
    }

    for turn in proj.turns:
        for event in turn.key_events:
            if event.get("event_type") in skip:
                errors.append(
                    f"key_events includes scaffolding event: {event.get('event_type')} at turn {turn.turn_index}"
                )

    return errors


def test_rounds(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)

    if not proj.rounds:
        errors.append("No rounds produced")
        return errors

    round_turns = {id(t) for rnd in proj.rounds for t in rnd.turns}
    orphans = [t for t in proj.turns if id(t) not in round_turns]
    if orphans:
        errors.append(f"{len(orphans)} turns not assigned to any round")

    for rnd in proj.rounds:
        if rnd.round_index <= 0:
            errors.append(f"Invalid round_index: {rnd.round_index}")
        if rnd.weather_name != rnd.weather:
            errors.append(f"weather alias mismatch in round {rnd.round_index}")
        if rnd.round_index == 1 and not rnd.weather_name:
            errors.append("round 1 weather name missing")

    return errors


def test_markdown_renderer(events: list[dict]) -> list[str]:
    errors: list[str] = []
    proj = ReplayProjection.from_list(events)
    md = render_markdown(proj)

    if not md:
        errors.append("markdown output is empty")
        return errors

    if "# GPT Visual Replay" not in md:
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
    if "const FRAMES = " not in html:
        errors.append("HTML missing FRAMES JSON")
    if "const META = " not in html:
        errors.append("HTML missing META JSON")
    if "board-track" not in html:
        errors.append("HTML missing perimeter board container")
    if 'id="legend-weather"' not in html:
        errors.append("HTML missing weather legend slot")

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

    frames_match = re.search(r"const FRAMES = (\[.*?\]);", html, re.DOTALL)
    if frames_match:
        try:
            parsed = json.loads(frames_match.group(1))
            if not isinstance(parsed, list):
                errors.append("FRAMES JSON is not a list")
            elif not parsed:
                errors.append("FRAMES JSON is empty")
            else:
                first = parsed[0]
                if first.get("event_type") != "session_start":
                    errors.append(
                        f"first replay frame is not session_start: {first.get('event_type')}"
                    )
                if first.get("title") != "Session Start":
                    errors.append(f"unexpected first frame title: {first.get('title')}")
                first_draft = next(
                    (frame for frame in parsed if frame.get("event_type") == "draft_pick"),
                    None,
                )
                if first_draft is None:
                    errors.append("missing draft_pick frame in replay HTML")
                else:
                    subtitle = str(first_draft.get("subtitle", "")).strip()
                    if subtitle.isdigit():
                        errors.append("draft_pick frame still shows raw numeric card only")
                first_weather = next(
                    (frame for frame in parsed if frame.get("event_type") == "weather_reveal"),
                    None,
                )
                if first_weather is None:
                    errors.append("missing weather_reveal frame in replay HTML")
                elif not str(first_weather.get("title", "")).startswith("Weather: "):
                    errors.append("weather_reveal frame title is not populated")
                elif str(first_weather.get("title", "")).strip() == "Weather: -":
                    errors.append("weather_reveal frame title still missing actual weather name")
                elif not str(first_weather.get("weather", "")).strip():
                    errors.append("weather_reveal frame missing carried weather field")
                first_dice = next(
                    (frame for frame in parsed if frame.get("event_type") == "dice_roll"),
                    None,
                )
                if first_dice is None:
                    errors.append("missing dice_roll frame in replay HTML")
                elif str(first_dice.get("subtitle", "")).startswith("[] ->"):
                    errors.append("dice_roll frame still shows empty dice array placeholder")
                first_move = next(
                    (frame for frame in parsed if frame.get("event_type") == "player_move"),
                    None,
                )
                if first_move is None:
                    errors.append("missing player_move frame in replay HTML")
                elif "?" in str(first_move.get("subtitle", "")):
                    errors.append("player_move frame still shows unresolved tile positions")
        except json.JSONDecodeError as exc:
            errors.append(f"FRAMES JSON parse error: {exc}")
    else:
        errors.append("Could not extract FRAMES JSON from HTML")

    return errors


def test_jsonl_roundtrip(events: list[dict]) -> list[str]:
    import os
    import tempfile

    errors: list[str] = []
    proj_orig = ReplayProjection.from_list(events)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8", delete=False) as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        tmp_path = f.name

    try:
        proj_loaded = ReplayProjection.from_jsonl(tmp_path)
        if len(proj_loaded.turns) != len(proj_orig.turns):
            errors.append(
                f"JSONL roundtrip turn count mismatch: {len(proj_orig.turns)} vs {len(proj_loaded.turns)}"
            )
    finally:
        os.unlink(tmp_path)

    return errors


def proj_turns_preview(events: list[dict]) -> list[TurnReplay]:
    return ReplayProjection.from_list(events).turns


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
            for err in errs:
                print(f"      {err}")
        else:
            print(f"    OK   {name}")

    return len(all_errors) == 0, all_errors


def main() -> int:
    seeds = [42, 137, 999]
    all_passed = True
    for seed in seeds:
        print(f"\nSeed {seed}:")
        passed, _errors = run_suite(seed)
        if not passed:
            all_passed = False

    if all_passed:
        print("\nPhase 2: ALL TESTS PASSED")
        return 0
    print("\nPhase 2: TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
