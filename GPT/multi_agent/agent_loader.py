from __future__ import annotations

from .base_agent import AbstractPlayerAgent
from .claude_agent import ClaudePlayerAgent
from .gpt_agent import GptPlayerAgent

_CLAUDE_V2_PROFILES = {
    "control",
    "growth",
    "balanced",
    "avoid_control",
    "aggressive",
    "token_opt",
    "v3_claude",
}


def make_agent(spec: str) -> AbstractPlayerAgent:
    """Create an agent from '<source>:<profile>' or '<source>' syntax."""

    if ":" in spec:
        source, profile = spec.split(":", 1)
    else:
        source, profile = spec, None

    source = source.strip().lower()

    if source == "claude":
        if profile is None:
            mode = "heuristic_v2_v3_claude"
        elif profile in _CLAUDE_V2_PROFILES:
            mode = f"heuristic_v2_{profile}" if profile != "v3_claude" else "heuristic_v2_v3_claude"
        else:
            mode = profile
        return ClaudePlayerAgent(mode)

    if source == "gpt":
        if profile is None or profile == "v3_gpt":
            mode = "heuristic_v3_gpt"
        else:
            mode = profile
        return GptPlayerAgent(mode)

    raise ValueError(
        f"Unknown agent source: '{source}'. Supported: 'claude', 'gpt'. "
        "Full spec example: 'claude:v3_claude', 'gpt:v3_gpt'"
    )
