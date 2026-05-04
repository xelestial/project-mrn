from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from config import CellKind
from policy.character_traits import is_gakju
from policy.context.turn_plan import PlayerIntentState


def generic_land_spend_penalty(
    *,
    current_character: str | None,
    rounds_completed: int,
    cell_kind: CellKind,
    owner: int | None,
    crosses_start: bool,
    use_cards: bool,
    card_count: int,
    intent: PlayerIntentState,
) -> float:
    if not use_cards or card_count < 2:
        return 0.0
    if is_gakju(current_character) and intent.plan_key == "lap_engine":
        if owner is None and cell_kind in {CellKind.T2, CellKind.T3} and not crosses_start:
            return -6.5
    if rounds_completed < 2 and owner is None and cell_kind in {CellKind.T2, CellKind.T3} and not crosses_start:
        return -1.4
    return 0.0


def apply_movement_intent_adjustment(
    *,
    current_character: str | None,
    rounds_completed: int,
    cell_kind: CellKind,
    owner: int | None,
    crosses_start: bool,
    use_cards: bool,
    card_count: int,
    intent: PlayerIntentState,
) -> float:
    adjustment = 0.0
    if use_cards and intent.resource_intent == "card_preserve":
        adjustment -= 0.55 * card_count
    adjustment += generic_land_spend_penalty(
        current_character=current_character,
        rounds_completed=rounds_completed,
        cell_kind=cell_kind,
        owner=owner,
        crosses_start=crosses_start,
        use_cards=use_cards,
        card_count=card_count,
        intent=intent,
    )
    return adjustment


@dataclass(frozen=True, slots=True)
class MovementChoiceResolution:
    use_cards: bool
    card_values: tuple[int, ...]
    score: float
    avg_no_cards: float = 0.0
    single_card_scores: tuple[tuple[int, float], ...] = ()
    double_card_scores: tuple[tuple[tuple[int, int], float], ...] = ()


def resolve_movement_choice(
    *,
    avg_no_cards: float,
    remaining_cards: tuple[int, ...],
    single_card_scorer,
    double_card_scorer,
    leader_trigger_value,
) -> MovementChoiceResolution:
    best_score = avg_no_cards
    best = MovementChoiceResolution(False, (), avg_no_cards)
    single_card_scores: list[tuple[int, float]] = []
    double_card_scores: list[tuple[tuple[int, int], float]] = []
    for card_value in remaining_cards:
        vals = [single_card_scorer(card_value, die_roll) for die_roll in range(1, 7)]
        mean_score = sum(vals) / len(vals)
        best_outcome = max(vals)
        worst_outcome = min(vals)
        threshold = avg_no_cards + 4.0
        decisive_hits = sum(1 for value in vals if value >= threshold)
        decisive_prob = decisive_hits / len(vals)
        score = (
            mean_score
            + 0.12 * (best_outcome - mean_score)
            + 0.75 * decisive_prob
            + 0.02 * worst_outcome
            + leader_trigger_value(best_outcome, avg_no_cards)
        )
        single_card_scores.append((card_value, score))
        if score > best_score:
            best_score = score
            best = MovementChoiceResolution(True, (card_value,), score)
    for first, second in combinations(remaining_cards, 2):
        score = double_card_scorer(first, second)
        double_card_scores.append(((first, second), score))
        if score > best_score:
            best_score = score
            best = MovementChoiceResolution(True, (first, second), score)
    return MovementChoiceResolution(
        use_cards=best.use_cards,
        card_values=best.card_values,
        score=best.score,
        avg_no_cards=avg_no_cards,
        single_card_scores=tuple(single_card_scores),
        double_card_scores=tuple(double_card_scores),
    )
