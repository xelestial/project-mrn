from __future__ import annotations

from dataclasses import dataclass

from policy.decision.scored_choice import run_ranked_choice


@dataclass(frozen=True, slots=True)
class ActiveFlipDebugPayload:
    policy: str
    candidate_scores: dict[str, float]
    chosen_card: int | None
    reasons: list[str]
    chosen_to: str | None = None
    generic_survival_score: float | None = None
    money_distress: float | None = None
    controller_need: float | None = None


@dataclass(frozen=True, slots=True)
class ActiveFlipResolution:
    choice: int | None
    debug_payload: dict[str, object]


def build_active_flip_debug_payload(debug: ActiveFlipDebugPayload) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy": debug.policy,
        "candidate_scores": debug.candidate_scores,
        "chosen_card": debug.chosen_card,
        "reasons": debug.reasons,
    }
    if debug.chosen_to is not None:
        payload["chosen_to"] = debug.chosen_to
    if debug.generic_survival_score is not None:
        payload["generic_survival_score"] = round(debug.generic_survival_score, 3)
    if debug.money_distress is not None:
        payload["money_distress"] = round(debug.money_distress, 3)
    if debug.controller_need is not None:
        payload["controller_need"] = round(debug.controller_need, 3)
    return payload


def resolve_random_active_flip_choice(
    flippable_cards: list[int],
    *,
    policy: str,
    chooser,
) -> ActiveFlipResolution:
    choice = chooser(flippable_cards)
    return ActiveFlipResolution(
        choice=choice,
        debug_payload=build_active_flip_debug_payload(
            ActiveFlipDebugPayload(
                policy=policy,
                candidate_scores={str(c): 0.0 for c in flippable_cards},
                chosen_card=choice,
                reasons=["uniform_random"],
            )
        ),
    )


def resolve_scored_active_flip_choice(
    flippable_cards: list[int],
    *,
    scored: dict[int, float],
    reasons: dict[int, list[str]],
    policy: str,
    chosen_to_resolver,
    generic_survival_score: float,
    money_distress: float,
    controller_need: float,
) -> ActiveFlipResolution:
    choice = run_ranked_choice(flippable_cards, ranker=lambda c: (scored[c], -c)).choice
    chosen_to = None if choice is None else chosen_to_resolver(choice)
    return ActiveFlipResolution(
        choice=choice,
        debug_payload=build_active_flip_debug_payload(
            ActiveFlipDebugPayload(
                policy=policy,
                candidate_scores={str(c): round(scored[c], 3) for c in flippable_cards},
                chosen_card=choice,
                chosen_to=chosen_to,
                reasons=reasons[choice],
                generic_survival_score=generic_survival_score,
                money_distress=money_distress,
                controller_need=controller_need,
            )
        ),
    )
