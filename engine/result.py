from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class GameResult:
    winner_ids: List[int]
    end_reason: str
    total_turns: int
    rounds_completed: int
    alive_count: int
    bankrupt_players: int
    final_f_value: float
    total_placed_coins: int
    player_summary: List[dict] = field(default_factory=list)
    strategy_summary: List[dict] = field(default_factory=list)
    weather_history: List[str] = field(default_factory=list)
    action_log: List[dict] = field(default_factory=list)
    ai_decision_log: List[dict] = field(default_factory=list)
    bankruptcy_events: List[dict] = field(default_factory=list)

