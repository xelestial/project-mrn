from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from trick_cards import TrickCard
from policy.decision.scored_choice import ScoredChoiceRun, run_scored_choice


@dataclass(frozen=True, slots=True)
class TrickRewardResolution:
    choice: TrickCard | None
    score_map: dict[str, float]


@dataclass(frozen=True, slots=True)
class TrickRewardChoiceRun:
    choice: TrickCard | None
    debug_payload: dict[str, object]


def resolve_trick_reward_choice(
    choices: Sequence[TrickCard],
    *,
    scorer: Callable[[TrickCard], float],
) -> TrickRewardResolution:
    choice_run: ScoredChoiceRun[TrickCard] = run_scored_choice(
        choices,
        scorer=scorer,
        label_for_option=lambda card: card.name,
    )
    return TrickRewardResolution(
        choice=choice_run.choice,
        score_map=choice_run.score_map,
    )


def build_trick_reward_debug_payload(
    *,
    choices: Sequence[TrickCard],
    chosen: TrickCard | None,
    score_map: dict[str, float],
    generic_survival_score: float,
    survival_urgency: float,
) -> dict[str, object]:
    return {
        "choices": [c.name for c in choices],
        "chosen": None if chosen is None else chosen.name,
        "scores": score_map,
        "generic_survival_score": round(generic_survival_score, 3),
        "survival_urgency": round(survival_urgency, 3),
    }


def resolve_trick_reward_choice_run(
    *,
    choices: Sequence[TrickCard],
    scorer: Callable[[TrickCard], float],
    generic_survival_score: float,
    survival_urgency: float,
) -> TrickRewardChoiceRun:
    resolution = resolve_trick_reward_choice(choices, scorer=scorer)
    return TrickRewardChoiceRun(
        choice=resolution.choice,
        debug_payload=build_trick_reward_debug_payload(
            choices=choices,
            chosen=resolution.choice,
            score_map=resolution.score_map,
            generic_survival_score=generic_survival_score,
            survival_urgency=survival_urgency,
        ),
    )
