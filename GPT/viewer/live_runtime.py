from __future__ import annotations

import random
from pathlib import Path

from .live import LiveSpectatorStream
from .renderers.live_html import render_live_html


def write_live_viewer_files(out_dir: str | Path) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    index_path = out_path / "index.html"
    index_path.write_text(render_live_html(), encoding="utf-8")
    return index_path


def run_live_seed(
    *,
    seed: int,
    out_dir: str | Path,
    character_policy_mode: str = "heuristic_v1",
    lap_policy_mode: str = "heuristic_v1",
) -> LiveSpectatorStream:
    from ai_policy import HeuristicPolicy
    from config import DEFAULT_CONFIG
    from engine import GameEngine

    write_live_viewer_files(out_dir)
    stream = LiveSpectatorStream(out_dir)
    policy = HeuristicPolicy(
        character_policy_mode=character_policy_mode,
        lap_policy_mode=lap_policy_mode,
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    stream.mark_completed()
    return stream
