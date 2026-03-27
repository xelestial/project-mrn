"""multi_agent — per-player independent AI module dispatch."""
from .dispatcher import MultiAgentDispatcher
from .agent_loader import make_agent

__all__ = ["MultiAgentDispatcher", "make_agent"]
