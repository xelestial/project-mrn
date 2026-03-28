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
    elif "remaining_dice_cards" not in players[0]:
        errors.append("session_start missing remaining_dice_cards")

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

    if "# GPT 시각 리플레이" not in md:
        errors.append("markdown missing header")
    if "## 1 라운드" not in md:
        errors.append("markdown missing round headers")
    if "### 1 턴" not in md:
        errors.append("markdown missing turn headers")
    if "주사위 카드" not in md and "주사위 " not in md:
        errors.append("markdown missing human-readable dice summary")
    if "플레이어 공개 상태" not in md:
        errors.append("markdown missing Korean snapshot heading")
    if "공개/비공개 잔꾀" not in md:
        errors.append("markdown missing trick visibility columns")

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
                if first.get("title") != "게임 시작":
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
                elif not str(first_weather.get("title", "")).startswith("날씨 공개 - "):
                    errors.append("weather_reveal frame title is not populated")
                elif str(first_weather.get("title", "")).strip() == "날씨 공개 - -":
                    errors.append("weather_reveal frame title still missing actual weather name")
                elif not str(first_weather.get("weather", "")).strip():
                    errors.append("weather_reveal frame missing carried weather field")
                elif not str(first_weather.get("weather_effect", "")).strip():
                    errors.append("weather_reveal frame missing weather effect text")
                first_dice = next(
                    (frame for frame in parsed if frame.get("event_type") == "dice_roll"),
                    None,
                )
                if first_dice is None:
                    errors.append("missing dice_roll frame in replay HTML")
                elif str(first_dice.get("subtitle", "")).startswith("[] ->"):
                    errors.append("dice_roll frame still shows empty dice array placeholder")
                elif "주사위 카드" not in str(first_dice.get("subtitle", "")) and "주사위 " not in str(first_dice.get("subtitle", "")):
                    errors.append("dice_roll frame does not show actual dice card or dice usage")
                first_trick = next(
                    (frame for frame in parsed if frame.get("event_type") == "trick_used"),
                    None,
                )
                if any(event.get("event_type") == "trick_used" for event in events):
                    if first_trick is None:
                        errors.append("trick_used events exist but replay HTML does not show them")
                    elif " - " not in str(first_trick.get("subtitle", "")):
                        errors.append("trick_used frame missing readable name and description")
                first_move = next(
                    (frame for frame in parsed if frame.get("event_type") == "player_move"),
                    None,
                )
                if first_move is None:
                    errors.append("missing player_move frame in replay HTML")
                elif "?" in str(first_move.get("subtitle", "")):
                    errors.append("player_move frame still shows unresolved tile positions")
                else:
                    raw_first_move = next(
                        (event for event in events if event.get("event_type") == "player_move"),
                        None,
                    )
                    if raw_first_move is not None:
                        actor = raw_first_move.get("acting_player_id")
                        target = raw_first_move.get(
                            "to_tile_index",
                            raw_first_move.get("to_tile", raw_first_move.get("to_pos")),
                        )
                        player_state = next(
                            (
                                player
                                for player in first_move.get("players", [])
                                if player.get("player_id") == actor
                            ),
                            None,
                        )
                        if isinstance(target, int) and player_state is not None:
                            if player_state.get("position") != target:
                                errors.append(
                                    "player_move frame does not update the actor position in frame state"
                                )
                first_marker = next(
                    (frame for frame in parsed if frame.get("event_type") == "marker_transferred"),
                    None,
                )
                if first_marker is None:
                    errors.append("missing marker_transferred frame in replay HTML")
                elif "P?" in str(first_marker.get("subtitle", "")):
                    errors.append("marker_transferred frame still shows unresolved owner")
                first_flip = next(
                    (frame for frame in parsed if frame.get("event_type") == "marker_flip"),
                    None,
                )
                if any(event.get("event_type") == "marker_flip" for event in events):
                    if first_flip is None:
                        errors.append("marker_flip events exist but replay HTML does not show them")
                    elif "뒤집힘" not in str(first_flip.get("subtitle", "")):
                        errors.append("marker_flip frame missing readable flip detail")
                first_lap = next(
                    (frame for frame in parsed if frame.get("event_type") == "lap_reward_chosen"),
                    None,
                )
                if first_lap is None:
                    errors.append("missing lap_reward_chosen frame in replay HTML")
                else:
                    lap_subtitle = str(first_lap.get("subtitle", ""))
                    if not any(token in lap_subtitle for token in ("현금 +", "조각 +", "승점 +")):
                        errors.append("lap_reward_chosen frame still hides reward amounts")
                grouped_indices: dict[tuple[int, int], dict[str, int]] = {}
                for idx, frame in enumerate(parsed):
                    turn_key = (
                        int(frame.get("round_index", 0) or 0),
                        int(frame.get("turn_index", 0) or 0),
                    )
                    grouped_indices.setdefault(turn_key, {})
                    grouped_indices[turn_key].setdefault(str(frame.get("event_type")), idx)
                ordered_turn = next(
                    (
                        etypes
                        for etypes in grouped_indices.values()
                        if "player_move" in etypes
                        and "landing_resolved" in etypes
                        and "tile_purchased" in etypes
                    ),
                    None,
                )
                if ordered_turn is None:
                    errors.append("could not find a turn containing move, landing, and purchase frames")
                elif not (
                    ordered_turn["player_move"]
                    < ordered_turn["landing_resolved"]
                    < ordered_turn["tile_purchased"]
                ):
                    errors.append(
                        "replay frames do not follow player_move -> landing_resolved -> tile_purchased order"
                    )
        except json.JSONDecodeError as exc:
            errors.append(f"FRAMES JSON parse error: {exc}")
    else:
        errors.append("Could not extract FRAMES JSON from HTML")

    if "현재 상황" not in html:
        errors.append("HTML missing Korean situation heading")
    if "종료 시간" not in html:
        errors.append("HTML missing end-time label")
    if "남은 주사위 카드:" not in html:
        errors.append("HTML missing remaining dice cards in player panel")

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
