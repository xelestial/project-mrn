from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from policy.character_traits import (
    is_builder_character,
    is_route_runner_character,
    is_shard_hunter_character,
    is_token_window_character,
)
from policy.context.turn_plan import PlayerIntentState
from policy.decision.scored_choice import ScoredChoiceRun, run_scored_choice
from trick_cards import TrickCard


def apply_trick_preserve_rules(
    *,
    card_name: str,
    actor_name: str,
    hand_names: set[str],
    rounds_completed: int,
    strategic_mode: float,
    intent: PlayerIntentState | None,
    survival_urgency: float,
    cleanup_cash_gap: float,
    has_relic_collector_window: bool,
    has_help_run_window: bool,
    has_neojeol_chain_window: bool,
    short_range_frontier_is_better: bool,
) -> float:
    adjustment = 0.0
    if strategic_mode <= 0.0:
        if card_name in {"무료 증정", "마당발"} and (
            is_builder_character(actor_name) or {"무료 증정", "마당발"}.issubset(hand_names)
        ):
            adjustment -= 0.85
        if card_name in {"과속", "이럇!", "도움 닫기", "극심한 분리불안"}:
            adjustment -= 0.55
        if card_name in {"성물 수집가", "무역의 선물"} and is_shard_hunter_character(actor_name):
            adjustment -= 0.30
    if survival_urgency < 1.0 and cleanup_cash_gap <= 0.0:
        if card_name in {"도움 닫기", "극심한 분리불안"} and (
            is_route_runner_character(actor_name) or is_token_window_character(actor_name)
        ):
            adjustment -= 0.35
    if intent is not None and intent.resource_intent == "card_preserve":
        if card_name in {"과속", "이럇!", "도움 닫기", "극심한 분리불안", "가벼운 분리불안", "뇌절왕"}:
            adjustment -= 0.55
    if card_name == "성물 수집가" and not has_relic_collector_window:
        adjustment -= 2.4
    if card_name == "도움 닫기" and not has_help_run_window:
        adjustment -= 2.0 if rounds_completed <= 1 else 1.3
    if card_name == "뇌절왕" and not has_neojeol_chain_window:
        adjustment -= 2.3
    if card_name == "저속" and not (short_range_frontier_is_better or survival_urgency >= 1.0):
        adjustment -= 1.8
    return adjustment


def build_trick_use_debug_payload(
    *,
    score_map: dict[str, float],
    chosen_name: str | None,
    generic_survival_score: float,
    survival_urgency: float,
    strategic_mode: float,
) -> dict[str, object]:
    return {
        "scores": score_map,
        "chosen": chosen_name,
        "generic_survival_score": round(generic_survival_score, 3),
        "survival_urgency": round(survival_urgency, 3),
        "strategic_mode": round(strategic_mode, 3),
    }


@dataclass(frozen=True, slots=True)
class TrickUseResolution:
    choice: TrickCard | None
    score_map: dict[str, float]


def resolve_trick_use_choice(
    hand: Sequence[TrickCard],
    *,
    scorer: Callable[[TrickCard], float],
) -> TrickUseResolution:
    choice_run: ScoredChoiceRun[TrickCard] = run_scored_choice(
        hand,
        scorer=scorer,
        label_for_option=lambda card: card.name,
        minimum_score=0.0,
    )
    return TrickUseResolution(
        choice=choice_run.choice,
        score_map=choice_run.score_map,
    )
