from __future__ import annotations

from enum import Enum


class CommandState(str, Enum):
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    COMMITTED = "committed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


TERMINAL_COMMAND_STATES = frozenset(
    {
        CommandState.COMMITTED,
        CommandState.REJECTED,
        CommandState.SUPERSEDED,
        CommandState.EXPIRED,
    }
)


def normalize_command_state(value: str | CommandState) -> CommandState:
    if isinstance(value, CommandState):
        return value
    try:
        return CommandState(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown command state: {value!r}") from exc
