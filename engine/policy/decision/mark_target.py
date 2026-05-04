from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Callable

from characters import CHARACTERS


def filter_public_mark_candidates(
    actor_name: str,
    raw_candidates: Iterable[str],
    active_public_names: Iterable[str],
) -> list[str]:
    actor_priority = CHARACTERS[actor_name].priority if actor_name in CHARACTERS else 99
    candidates = [
        name
        for name in raw_candidates
        if name in CHARACTERS and CHARACTERS[name].priority >= actor_priority
    ]
    if candidates:
        return candidates
    fallback = sorted(
        {
            name
            for name in active_public_names
            if name
            and name != actor_name
            and name in CHARACTERS
            and CHARACTERS[name].priority >= actor_priority
        }
    )
    return fallback or list(raw_candidates)


@dataclass(frozen=True, slots=True)
class PublicMarkChoiceDebug:
    policy: str
    actor_name: str
    candidate_scores: dict[str, float]
    candidate_probabilities: dict[str, float]
    chosen_target: str | None
    reasons: list[str]
    top_candidate: str | None = None
    uniform_mix: float | None = None
    ambiguity: float | None = None
    top_probability: float | None = None
    second_probability: float | None = None


@dataclass(frozen=True, slots=True)
class PublicMarkChoiceEvaluation:
    scored: dict[str, float]
    reasons: dict[str, list[str]]
    probabilities: dict[str, float]
    top_candidate: str
    top_probability: float
    second_probability: float
    uniform_mix: float
    ambiguity: float


@dataclass(frozen=True, slots=True)
class PublicMarkChoiceResolution:
    choice: str
    debug_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class PublicMarkChoiceRun:
    choice: str | None
    debug_payload: dict[str, object]


def build_public_mark_choice_debug_payload(debug: PublicMarkChoiceDebug) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy": debug.policy,
        "actor_name": debug.actor_name,
        "candidate_scores": debug.candidate_scores,
        "candidate_probabilities": debug.candidate_probabilities,
        "chosen_target": debug.chosen_target,
        "reasons": debug.reasons,
    }
    if debug.top_candidate is not None:
        payload["top_candidate"] = debug.top_candidate
    if debug.uniform_mix is not None:
        payload["uniform_mix"] = round(debug.uniform_mix, 3)
    if debug.ambiguity is not None:
        payload["ambiguity"] = round(debug.ambiguity, 3)
    if debug.top_probability is not None:
        payload["top_probability"] = round(debug.top_probability, 3)
    if debug.second_probability is not None:
        payload["second_probability"] = round(debug.second_probability, 3)
    return payload


def build_empty_public_mark_choice_debug_payload(
    *,
    policy: str,
    actor_name: str,
    reason: str,
) -> dict[str, object]:
    return build_public_mark_choice_debug_payload(
        PublicMarkChoiceDebug(
            policy=policy,
            actor_name=actor_name,
            candidate_scores={},
            candidate_probabilities={},
            chosen_target=None,
            reasons=[reason],
        )
    )


def resolve_random_public_mark_choice(
    candidates: list[str],
    *,
    policy: str,
    actor_name: str,
    chooser: Callable[[list[str]], str],
) -> PublicMarkChoiceResolution:
    choice = chooser(candidates)
    probability = round(1.0 / len(candidates), 3)
    return PublicMarkChoiceResolution(
        choice=choice,
        debug_payload=build_public_mark_choice_debug_payload(
            PublicMarkChoiceDebug(
                policy=policy,
                actor_name=actor_name,
                candidate_scores={c: 0.0 for c in candidates},
                candidate_probabilities={c: probability for c in candidates},
                chosen_target=choice,
                reasons=["uniform_random_public_guess"],
            )
        ),
    )


def evaluate_public_mark_candidates(
    candidates: list[str],
    *,
    legal_target_count: int,
    scorer: Callable[[str], tuple[float, list[str]]],
    distribution_builder: Callable[[dict[str, float], int], tuple[dict[str, float], dict[str, float]]],
) -> PublicMarkChoiceEvaluation:
    scored: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for target_name in candidates:
        score, why = scorer(target_name)
        scored[target_name] = score
        reasons[target_name] = why
    probabilities, dist_meta = distribution_builder(scored, legal_target_count)
    ordered = sorted(candidates, key=lambda name: (probabilities[name], scored[name], name), reverse=True)
    top_candidate = ordered[0]
    return PublicMarkChoiceEvaluation(
        scored=scored,
        reasons=reasons,
        probabilities=probabilities,
        top_candidate=top_candidate,
        top_probability=float(dist_meta["top_probability"]),
        second_probability=float(dist_meta["second_probability"]),
        uniform_mix=float(dist_meta["uniform_mix"]),
        ambiguity=float(dist_meta["ambiguity"]),
    )


def resolve_public_mark_choice(
    candidates: list[str],
    *,
    policy: str,
    actor_name: str,
    legal_target_count: int,
    scorer: Callable[[str], tuple[float, list[str]]],
    distribution_builder: Callable[[dict[str, float], int], tuple[dict[str, float], dict[str, float]]],
    chooser: Callable[[list[str], list[float]], str],
) -> PublicMarkChoiceResolution:
    evaluation = evaluate_public_mark_candidates(
        candidates,
        legal_target_count=legal_target_count,
        scorer=scorer,
        distribution_builder=distribution_builder,
    )
    choice = chooser(candidates, [evaluation.probabilities[name] for name in candidates])
    debug_payload = build_public_mark_choice_debug_payload(
        PublicMarkChoiceDebug(
            policy=policy,
            actor_name=actor_name,
            candidate_scores={name: round(val, 3) for name, val in evaluation.scored.items()},
            candidate_probabilities={name: round(evaluation.probabilities[name], 3) for name in candidates},
            chosen_target=choice,
            top_candidate=evaluation.top_candidate,
            uniform_mix=evaluation.uniform_mix,
            ambiguity=evaluation.ambiguity,
            top_probability=evaluation.top_probability,
            second_probability=evaluation.second_probability,
            reasons=evaluation.reasons[choice],
        )
    )
    return PublicMarkChoiceResolution(choice=choice, debug_payload=debug_payload)


def run_public_mark_choice(
    candidates: list[str],
    *,
    policy: str,
    actor_name: str,
    legal_target_count: int,
    is_random_mode: bool,
    scorer: Callable[[str], tuple[float, list[str]]],
    distribution_builder: Callable[[dict[str, float], int], tuple[dict[str, float], dict[str, float]]],
    chooser: Callable[[list[str], list[float]], str],
    random_chooser: Callable[[list[str]], str],
) -> PublicMarkChoiceRun:
    if legal_target_count <= 0 or not candidates:
        return PublicMarkChoiceRun(
            choice=None,
            debug_payload=build_empty_public_mark_choice_debug_payload(
                policy=policy,
                actor_name=actor_name,
                reason="no_public_guess_candidates" if legal_target_count > 0 else "no_legal_targets",
            ),
        )
    if is_random_mode:
        resolution = resolve_random_public_mark_choice(
            candidates,
            policy=policy,
            actor_name=actor_name,
            chooser=random_chooser,
        )
        return PublicMarkChoiceRun(choice=resolution.choice, debug_payload=resolution.debug_payload)
    resolution = resolve_public_mark_choice(
        candidates,
        policy=policy,
        actor_name=actor_name,
        legal_target_count=legal_target_count,
        scorer=scorer,
        distribution_builder=distribution_builder,
        chooser=chooser,
    )
    return PublicMarkChoiceRun(choice=resolution.choice, debug_payload=resolution.debug_payload)
