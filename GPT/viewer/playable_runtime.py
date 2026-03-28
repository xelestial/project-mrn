from __future__ import annotations

import random
from pathlib import Path

from config import DEFAULT_CONFIG
from engine import GameEngine

from .human_adapter import HumanDecisionAdapter
from .live import LiveSpectatorStream
from .live_runtime import write_live_viewer_files
from .prompting import PromptFileChannel, PromptResponseProvider


def run_playable_seed(
    *,
    seed: int,
    out_dir: str | Path,
    human_players: set[int],
    response_provider: PromptResponseProvider,
) -> tuple[LiveSpectatorStream, PromptFileChannel]:
    write_live_viewer_files(out_dir)
    prompt_channel = PromptFileChannel(out_dir)
    stream = LiveSpectatorStream(out_dir)
    policy = HumanDecisionAdapter(
        human_players=human_players,
        response_provider=response_provider,
        prompt_channel=prompt_channel,
    )
    engine = GameEngine(DEFAULT_CONFIG, policy, rng=random.Random(seed), event_stream=stream)
    engine.run()
    stream.mark_completed()
    prompt_channel.clear_prompt()
    return stream, prompt_channel
