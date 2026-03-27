from __future__ import annotations
"""agent_loader — spec 문자열로 AbstractPlayerAgent를 생성하는 팩토리."""

from .base_agent import AbstractPlayerAgent
from .claude_agent import ClaudePlayerAgent
from .gpt_agent import GptPlayerAgent


_CLAUDE_V2_PROFILES = {
    "control", "growth", "balanced", "avoid_control",
    "aggressive", "token_opt", "v3_claude",
}


def make_agent(spec: str) -> AbstractPlayerAgent:
    """
    spec 형식: "<source>:<profile>" 또는 "<source>"

    Examples:
        "claude:v3_claude"   → ClaudePlayerAgent("heuristic_v2_v3_claude")
        "claude:balanced"    → ClaudePlayerAgent("heuristic_v2_balanced")
        "claude"             → ClaudePlayerAgent("heuristic_v2_v3_claude")  # 기본값
        "gpt:v3_gpt"         → GptPlayerAgent("heuristic_v3_gpt")
        "gpt"                → GptPlayerAgent("heuristic_v3_gpt")           # 기본값
    """
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
            mode = profile  # 이미 full canonical name인 경우
        return ClaudePlayerAgent(mode)

    elif source == "gpt":
        if profile is None:
            mode = "heuristic_v3_gpt"
        elif profile == "v3_gpt":
            mode = "heuristic_v3_gpt"
        else:
            mode = profile
        return GptPlayerAgent(mode)

    else:
        raise ValueError(
            f"Unknown agent source: '{source}'. "
            f"Supported: 'claude', 'gpt'. "
            f"Full spec example: 'claude:v3_claude', 'gpt:v3_gpt'"
        )
