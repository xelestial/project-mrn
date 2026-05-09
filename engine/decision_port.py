from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ai_policy import BasePolicy
from state import GameState, PlayerState


@dataclass(slots=True)
class DecisionRequest:
    decision_name: str
    request_type: str
    state: GameState
    player: PlayerState
    player_id: int
    round_index: int | None
    turn_index: int | None
    public_context: dict[str, Any] = field(default_factory=dict)
    fallback_policy: str = "engine_default"
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    fallback: Callable[[], Any] | None = None


class DecisionPort:
    def __init__(self, policy: BasePolicy) -> None:
        self._policy = policy

    def request(self, request: DecisionRequest) -> Any:
        decision_fn = getattr(self._policy, request.decision_name, None)
        if decision_fn is None:
            if request.fallback is not None:
                return request.fallback()
            raise AttributeError(request.decision_name)
        return decision_fn(request.state, request.player, *request.args, **request.kwargs)


@dataclass(frozen=True, slots=True)
class EngineDecisionResume:
    request_id: str
    player_id: int
    request_type: str
    choice_id: str
    choice_payload: dict
    resume_token: str
    frame_id: str
    module_id: str
    module_type: str
    module_cursor: str
    batch_id: str = ""

