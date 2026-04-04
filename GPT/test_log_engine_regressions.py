from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_policy import HeuristicPolicy
from config import DEFAULT_CONFIG
from engine import GameEngine
from validate_vis_stream import validate_vis_stream
from viewer.stream import VisEventStream


def _run_game(seed: int) -> tuple[VisEventStream, list[dict]]:
    policy = HeuristicPolicy(
        character_policy_mode="heuristic_v1",
        lap_policy_mode="heuristic_v1",
    )
    stream = VisEventStream()
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    return stream, list(engine._action_log)


def test_turn_start_turn_end_snapshot_regression_seeds() -> None:
    # Repro seeds from log audit where turn_start/turn_end_snapshot counts diverged.
    seeds = [20260437, 20260438, 20260486]
    for seed in seeds:
        stream, _ = _run_game(seed)
        result = validate_vis_stream(stream.to_list(), strict_payload=True)
        assert result["ok"], f"seed={seed} vis stream invalid: {result['errors']}"


def test_swindle_skip_policy_action_log_has_event_key() -> None:
    # Repro seeds from log audit where SWINDLE_SKIP_POLICY rows missed `event`.
    # The rows are policy-gated and can be absent depending on policy/ruleset;
    # when present they must include a normalized `event` key.
    seeds = [20260404, 20260409, 20260410, 20260431, 20260443, 20260467]
    missing_event_rows: list[dict] = []
    for seed in seeds:
        _, action_log = _run_game(seed)
        for row in action_log:
            if row.get("event_kind") == "policy_action" and row.get("type") == "SWINDLE_SKIP_POLICY":
                if row.get("event") != "policy_action":
                    missing_event_rows.append(row)
    assert not missing_event_rows
