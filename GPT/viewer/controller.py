from __future__ import annotations

from dataclasses import dataclass

from .replay import ReplayProjection, RoundReplay, TurnReplay


@dataclass(slots=True)
class ReplayCursor:
    position: int
    turn_index: int
    round_index: int
    acting_player_id: int | None


class ReplayController:
    """Thin step-through controller for replay navigation."""

    def __init__(self, projection: ReplayProjection) -> None:
        self._projection = projection
        self._position = 0 if projection.turns else -1

    @property
    def projection(self) -> ReplayProjection:
        return self._projection

    @property
    def current_position(self) -> int:
        return self._position

    @property
    def has_turns(self) -> bool:
        return self._position >= 0

    @property
    def current_turn(self) -> TurnReplay | None:
        if not self.has_turns:
            return None
        return self._projection.turn_at(self._position)

    @property
    def current_round(self) -> RoundReplay | None:
        turn = self.current_turn
        if turn is None:
            return None
        return self._projection.get_round(turn.round_index)

    @property
    def cursor(self) -> ReplayCursor | None:
        turn = self.current_turn
        if turn is None:
            return None
        return ReplayCursor(
            position=self._position,
            turn_index=turn.turn_index,
            round_index=turn.round_index,
            acting_player_id=turn.acting_player_id,
        )

    @property
    def can_go_prev(self) -> bool:
        return self._position > 0

    @property
    def can_go_next(self) -> bool:
        return self.has_turns and self._position < self._projection.turn_count - 1

    def first(self) -> TurnReplay | None:
        if not self._projection.turns:
            self._position = -1
            return None
        self._position = 0
        return self.current_turn

    def last(self) -> TurnReplay | None:
        if not self._projection.turns:
            self._position = -1
            return None
        self._position = self._projection.turn_count - 1
        return self.current_turn

    def next(self) -> TurnReplay | None:
        if not self.can_go_next:
            return self.current_turn
        self._position += 1
        return self.current_turn

    def prev(self) -> TurnReplay | None:
        if not self.can_go_prev:
            return self.current_turn
        self._position -= 1
        return self.current_turn

    def go_to_position(self, position: int) -> TurnReplay | None:
        if position < 0 or position >= self._projection.turn_count:
            raise IndexError(f"turn position out of range: {position}")
        self._position = position
        return self.current_turn

    def go_to_turn(self, turn_index: int) -> TurnReplay | None:
        turn = self._projection.get_turn(turn_index)
        if turn is None:
            raise KeyError(f"unknown turn_index: {turn_index}")
        for position, candidate in enumerate(self._projection.turns):
            if candidate.turn_index == turn_index:
                self._position = position
                return candidate
        raise KeyError(f"unknown turn_index: {turn_index}")

    def go_to_round(self, round_index: int) -> TurnReplay | None:
        turns = self._projection.turns_for_round(round_index)
        if not turns:
            raise KeyError(f"unknown round_index: {round_index}")
        return self.go_to_turn(turns[0].turn_index)
