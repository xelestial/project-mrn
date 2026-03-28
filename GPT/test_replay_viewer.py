from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from viewer.controller import ReplayController
from viewer.replay import ReplayProjection, TurnReplay
from viewer.renderers.html_renderer import render_html
from viewer.renderers.markdown_renderer import render_markdown
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


def _events(seed: int = 42) -> list[dict]:
    return _run_game(seed).to_list()


def test_projection_groups_turns() -> None:
    projection = ReplayProjection.from_list(_events())
    assert projection.turns
    assert projection.rounds
    assert projection.turn_count == len(projection.turns)
    assert projection.round_count == len(projection.rounds)
    assert all(isinstance(turn, TurnReplay) for turn in projection.turns)
    assert all(turn.turn_index > 0 for turn in projection.turns)
    assert all(turn.round_index > 0 for turn in projection.turns)


def test_projection_snapshots_and_board_shape() -> None:
    projection = ReplayProjection.from_list(_events())
    snapshotted_turns = [turn for turn in projection.turns if turn.snapshot is not None]
    assert snapshotted_turns
    for turn in snapshotted_turns:
        assert turn.player_states
        assert turn.board_state is not None
        assert len(turn.board_state.get("tiles", [])) == 40


def test_key_events_exclude_scaffolding() -> None:
    projection = ReplayProjection.from_list(_events())
    skip = {
        "session_start",
        "round_start",
        "turn_start",
        "turn_end_snapshot",
        "trick_window_open",
        "trick_window_closed",
    }
    for turn in projection.turns:
        assert all(event.get("event_type") not in skip for event in turn.key_events)


def test_round_membership_and_prelude_events() -> None:
    projection = ReplayProjection.from_list(_events())
    round_turns = {id(turn) for round_replay in projection.rounds for turn in round_replay.turns}
    assert not [turn for turn in projection.turns if id(turn) not in round_turns]
    assert projection.session.session_start.get("event_type") == "session_start"
    assert any(
        event.get("event_type") == "weather_reveal"
        for round_replay in projection.rounds
        for event in round_replay.prelude_events
    )


def test_controller_navigation() -> None:
    projection = ReplayProjection.from_list(_events())
    controller = ReplayController(projection)

    first_turn = controller.current_turn
    assert first_turn is not None
    assert controller.cursor is not None
    assert controller.go_to_round(1) is not None
    assert controller.next() is not None
    assert controller.prev() is not None
    assert controller.last() is not None
    assert controller.current_position == projection.turn_count - 1
    assert controller.first() is not None
    assert controller.current_turn == first_turn


def test_markdown_renderer_output() -> None:
    projection = ReplayProjection.from_list(_events())
    markdown = render_markdown(projection)
    assert markdown
    assert "# GPT Visual Replay" in markdown
    assert "## Round" in markdown
    assert "### Turn" in markdown


def test_html_renderer_output() -> None:
    projection = ReplayProjection.from_list(_events())
    html = render_html(projection)
    assert html
    assert "<!DOCTYPE html>" in html
    assert "const TURNS = " in html
    assert "const META = " in html

    import re

    turns_match = re.search(r"const TURNS = (\[.*?\]);", html, re.DOTALL)
    assert turns_match is not None
    parsed_turns = json.loads(turns_match.group(1))
    assert isinstance(parsed_turns, list)
    assert any("round_prelude_events" in turn for turn in parsed_turns)


def test_jsonl_roundtrip_preserves_turn_count() -> None:
    events = _events()
    original = ReplayProjection.from_list(events)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8", delete=False) as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        path = f.name

    try:
        loaded = ReplayProjection.from_jsonl(path)
        assert loaded.turn_count == original.turn_count
        assert loaded.round_count == original.round_count
    finally:
        Path(path).unlink(missing_ok=True)


def test_projection_json_roundtrip_preserves_turn_count() -> None:
    projection = ReplayProjection.from_list(_events())
    payload = projection.to_dict()
    assert payload["schema"] == "gpt.phase2.replay.v1"
    assert "raw_events" in payload
    assert "session" in payload

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        path = f.name

    try:
        loaded = ReplayProjection.from_json(path)
        assert loaded.turn_count == projection.turn_count
        assert loaded.round_count == projection.round_count
        assert loaded.session.session_id == projection.session.session_id
    finally:
        Path(path).unlink(missing_ok=True)
