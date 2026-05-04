from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class TurnBundle:
    round_index: int
    turn_index: int
    player: int
    character: str
    move_roll: int | None
    landing_type: str
    semantic_events: list[dict]
    runtime_events: list[dict]
    resource_deltas: dict[str, float]
    human_summary: str
    turn_row: dict


def _movement_roll(turn_row: dict) -> int | None:
    movement = turn_row.get("movement") or {}
    roll = movement.get("roll")
    if isinstance(roll, (int, float)):
        return int(roll)
    return None


def _landing_type(turn_row: dict) -> str:
    landing = turn_row.get("landing") or {}
    landing_type = landing.get("type")
    if landing_type:
        return str(landing_type)
    cell = turn_row.get("cell")
    return str(cell or "")


def _resource_deltas(turn_row: dict) -> dict[str, float]:
    deltas: dict[str, float] = {}
    field_pairs = {
        "cash": ("cash_before", "cash_after"),
        "tiles": ("tiles_before", "tiles_after"),
        "hand_coins": ("hand_coins_before", "hand_coins_after"),
        "shards": ("shards_before", "shards_after"),
        "f_value": ("f_before", "f_after"),
    }
    for key, (before_key, after_key) in field_pairs.items():
        before = turn_row.get(before_key)
        after = turn_row.get(after_key)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            deltas[key] = float(after) - float(before)
    return deltas


def _human_summary(turn_row: dict) -> str:
    player = turn_row.get("player", "?")
    character = turn_row.get("character") or "unknown"
    landing_type = _landing_type(turn_row) or "unknown"
    deltas = _resource_deltas(turn_row)
    parts = [f"P{player}", str(character), landing_type]
    if deltas:
        delta_bits = ", ".join(f"{name}={value:+g}" for name, value in deltas.items())
        parts.append(delta_bits)
    return " | ".join(parts)


def parse_action_log(action_log: Iterable[dict]) -> list[TurnBundle]:
    bundles: list[TurnBundle] = []
    pending: list[dict] = []
    for row in action_log:
        if row.get("event") != "turn":
            pending.append(dict(row))
            continue
        turn_row = dict(row)
        semantic_events = [event for event in pending if event.get("event_kind") == "semantic_event"]
        runtime_events = [event for event in pending if event.get("event_kind") != "semantic_event"]
        bundles.append(
            TurnBundle(
                round_index=int(turn_row.get("round_index", 0) or 0),
                turn_index=int(turn_row.get("turn_index_global", turn_row.get("turn_index", 0)) or 0),
                player=int(turn_row.get("player", 0) or 0),
                character=str(turn_row.get("character") or ""),
                move_roll=_movement_roll(turn_row),
                landing_type=_landing_type(turn_row),
                semantic_events=semantic_events,
                runtime_events=runtime_events,
                resource_deltas=_resource_deltas(turn_row),
                human_summary=_human_summary(turn_row),
                turn_row=turn_row,
            )
        )
        pending = []
    return bundles


def bundles_for_player(bundles: Iterable[TurnBundle], player: int) -> list[TurnBundle]:
    return [bundle for bundle in bundles if bundle.player == player]


def decision_rows(bundle: TurnBundle, decision_name: str | None = None) -> list[dict]:
    rows = [row for row in bundle.runtime_events if row.get("event") in {"ai_decision_before", "ai_decision_after"}]
    if decision_name is None:
        return rows
    return [row for row in rows if row.get("decision") == decision_name]
