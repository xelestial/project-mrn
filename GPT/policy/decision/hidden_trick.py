from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from policy.character_traits import is_builder_character, is_route_runner_character, is_shard_hunter_character
from policy.decision.scored_choice import run_ranked_choice


COMBO_PRIORITY_TRICKS = {
    "도움 닫기",
    "뇌절왕",
    "아주 큰 화목 난로",
    "과속",
    "이럇!",
    "극심한 분리불안",
    "재뿌리기",
    "성물 수집가",
    "저속",
}


@dataclass(frozen=True, slots=True)
class HiddenTrickResolution:
    choice_name: str | None
    score_map: dict[str, float]


@dataclass(frozen=True, slots=True)
class HiddenTrickChoiceRun:
    choice: object | None
    debug_payload: dict[str, object]


def score_hidden_trick_card(
    *,
    actor_name: str | None,
    card_name: str,
    is_burden: bool,
    burden_cost: int,
    is_anytime: bool,
) -> float:
    score = 0.0
    if is_burden:
        score += 5.0 + burden_cost
    if card_name in COMBO_PRIORITY_TRICKS:
        score += 3.5
    if is_builder_character(actor_name) and card_name in {"도움 닫기", "뇌절왕"}:
        score += 2.0
    if is_route_runner_character(actor_name) and card_name in {"과속", "이럇!", "극심한 분리불안"}:
        score += 1.5
    if is_shard_hunter_character(actor_name) and card_name == "저속":
        score += 1.5
    if is_anytime:
        score += 0.5
    return score


def resolve_hidden_trick_choice(
    hand: Sequence,
    *,
    actor_name: str | None,
) -> HiddenTrickResolution:
    def ranker(card) -> tuple[float, int, int]:
        score = score_hidden_trick_card(
            actor_name=actor_name,
            card_name=card.name,
            is_burden=card.is_burden,
            burden_cost=card.burden_cost,
            is_anytime=card.is_anytime,
        )
        return (score, card.burden_cost, card.deck_index)

    choice_run = run_ranked_choice(hand, ranker=ranker)
    score_map = {
        card.name: round(
            score_hidden_trick_card(
                actor_name=actor_name,
                card_name=card.name,
                is_burden=card.is_burden,
                burden_cost=card.burden_cost,
                is_anytime=card.is_anytime,
            ),
            3,
        )
        for card in hand
    }
    return HiddenTrickResolution(
        choice_name=None if choice_run.choice is None else choice_run.choice.name,
        score_map=score_map,
    )


def build_hidden_trick_debug_payload(
    *,
    hand: Sequence,
    resolution: HiddenTrickResolution,
) -> dict[str, object]:
    return {
        "choices": [card.name for card in hand],
        "chosen": resolution.choice_name,
        "scores": resolution.score_map,
    }


def resolve_hidden_trick_choice_run(
    hand: Sequence,
    *,
    actor_name: str | None,
) -> HiddenTrickChoiceRun:
    resolution = resolve_hidden_trick_choice(hand, actor_name=actor_name)
    selected = next((card for card in hand if card.name == resolution.choice_name), None)
    return HiddenTrickChoiceRun(
        choice=selected,
        debug_payload=build_hidden_trick_debug_payload(hand=hand, resolution=resolution),
    )
