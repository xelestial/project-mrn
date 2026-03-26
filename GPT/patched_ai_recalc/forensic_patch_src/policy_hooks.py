from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict

PolicyHook = Callable[..., Any]


class PolicyHookDispatcher:
    """Lightweight hook bus for policy decision tracing and customization."""

    def __init__(self) -> None:
        self._hooks: DefaultDict[str, list[PolicyHook]] = defaultdict(list)

    def register(self, hook_name: str, hook: PolicyHook) -> None:
        self._hooks[hook_name].append(hook)

    def emit(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [hook(*args, **kwargs) for hook in self._hooks.get(hook_name, [])]


class PolicyDecisionTraceRecorder:
    """Stores latest before/after decision payloads per player/category for debugging."""

    def __init__(self, sink: dict[tuple[str, int], dict[str, Any]] | None = None) -> None:
        self.sink = sink if sink is not None else {}

    def before_decision(self, policy, decision_name: str, state, player, args, kwargs) -> None:
        if player is None:
            return
        self.sink[(decision_name, player.player_id)] = {
            "phase": "before",
            "decision": decision_name,
            "player": player.player_id + 1,
            "round": getattr(state, "rounds_completed", 0) + 1 if state is not None else None,
        }

    def after_decision(self, policy, decision_name: str, state, player, result, args, kwargs) -> None:
        if player is None:
            return
        self.sink[(decision_name, player.player_id)] = {
            "phase": "after",
            "decision": decision_name,
            "player": player.player_id + 1,
            "round": getattr(state, "rounds_completed", 0) + 1 if state is not None else None,
            "result": repr(result),
        }


class PolicyDecisionLogHook:
    """Appends AI decision traces into the engine action log when logging is enabled."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def before_decision(self, policy, decision_name: str, state, player, args, kwargs) -> None:
        if player is None:
            return
        self.engine._log({
            "event": "ai_decision_before",
            "decision": decision_name,
            "player": player.player_id + 1,
            "round_index": getattr(state, "rounds_completed", 0) + 1 if state is not None else None,
        })

    def after_decision(self, policy, decision_name: str, state, player, result, args, kwargs) -> None:
        if player is None:
            return
        self.engine._log({
            "event": "ai_decision_after",
            "decision": decision_name,
            "player": player.player_id + 1,
            "round_index": getattr(state, "rounds_completed", 0) + 1 if state is not None else None,
            "result": repr(result),
        })
