from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ScoredChoiceRun(Generic[T]):
    choice: T | None
    score_map: dict[str, float]


@dataclass(frozen=True, slots=True)
class RankedChoiceRun(Generic[T]):
    choice: T | None


def run_scored_choice(
    options: list[T],
    *,
    scorer: Callable[[T], float],
    label_for_option: Callable[[T], str],
    minimum_score: float | None = None,
) -> ScoredChoiceRun[T]:
    score_map = {
        label_for_option(option): round(float(scorer(option)), 3)
        for option in options
    }
    best_option = max(options, key=lambda option: score_map[label_for_option(option)], default=None)
    if best_option is None:
        return ScoredChoiceRun(choice=None, score_map=score_map)
    if minimum_score is not None and score_map[label_for_option(best_option)] <= minimum_score:
        return ScoredChoiceRun(choice=None, score_map=score_map)
    return ScoredChoiceRun(choice=best_option, score_map=score_map)


def run_ranked_choice(
    options: list[T],
    *,
    ranker: Callable[[T], tuple],
) -> RankedChoiceRun[T]:
    best_option = max(options, key=ranker, default=None)
    return RankedChoiceRun(choice=best_option)
