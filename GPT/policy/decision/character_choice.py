from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Mapping, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CharacterChoiceCandidate(Generic[T]):
    key: T
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False
    hard_block_detail: dict[str, object] | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class CharacterChoiceDecision(Generic[T]):
    candidates: tuple[CharacterChoiceCandidate[T], ...]
    candidate_pool: tuple[T, ...]
    choice: T


@dataclass(frozen=True, slots=True)
class CharacterChoiceEvaluation(Generic[T]):
    decision: CharacterChoiceDecision[T]
    scores: dict[T, float]
    reasons: dict[T, tuple[str, ...]]
    hard_blocked_keys: tuple[T, ...]
    hard_block_details: dict[T, dict[str, object]]
    metadata: dict[T, dict[str, object]]


@dataclass(frozen=True, slots=True)
class CharacterChoiceDebugSummary(Generic[T]):
    score_map: dict[str, float]
    reason_map: dict[str, list[str]]
    hard_blocked_map: dict[str, dict[str, object]]
    metadata_map: dict[str, dict[str, object]]


@dataclass(frozen=True, slots=True)
class CharacterChoiceRun(Generic[T]):
    evaluation: CharacterChoiceEvaluation[T]
    debug_summary: CharacterChoiceDebugSummary[T]
    choice: T


@dataclass(frozen=True, slots=True)
class NamedCharacterChoicePolicy(Generic[T]):
    resolve_name: Callable[[T], str]
    base_breakdown: Callable[[str], tuple[float, list[str]]]
    survival_policy_advice: Callable[[str], tuple[float, list[str], bool, dict[str, object]]]
    survival_adjustment: Callable[[str], tuple[float, list[str]]]
    marker_bonus_by_name: Mapping[str, float]
    weighted_marker_names: set[str]
    survival_first: bool
    weight_multiplier: float


def build_named_character_choice_policy(
    *,
    resolve_name: Callable[[T], str],
    base_breakdown: Callable[[str], tuple[float, list[str]]],
    survival_policy_advice: Callable[[str], tuple[float, list[str], bool, dict[str, object]]],
    survival_adjustment: Callable[[str], tuple[float, list[str]]],
    marker_bonus_by_name: Mapping[str, float],
    weighted_marker_names: set[str],
    survival_first: bool,
    weight_multiplier: float,
) -> NamedCharacterChoicePolicy[T]:
    return NamedCharacterChoicePolicy(
        resolve_name=resolve_name,
        base_breakdown=base_breakdown,
        survival_policy_advice=survival_policy_advice,
        survival_adjustment=survival_adjustment,
        marker_bonus_by_name=marker_bonus_by_name,
        weighted_marker_names=weighted_marker_names,
        survival_first=survival_first,
        weight_multiplier=weight_multiplier,
    )


def decide_character_choice(
    candidates: list[CharacterChoiceCandidate[T]],
    *,
    tiebreak_desc: bool = False,
) -> CharacterChoiceDecision[T]:
    if not candidates:
        raise ValueError("candidates must not be empty")
    offered = [candidate.key for candidate in candidates]
    candidate_pool = [candidate.key for candidate in candidates if not candidate.hard_blocked]
    if not candidate_pool:
        candidate_pool = list(offered)

    score_map = {candidate.key: candidate.score for candidate in candidates}

    def _key(value: T):
        if tiebreak_desc:
            return (score_map[value], value)
        return (score_map[value], -value)  # type: ignore[operator]

    choice = max(candidate_pool, key=_key)
    return CharacterChoiceDecision(
        candidates=tuple(candidates),
        candidate_pool=tuple(candidate_pool),
        choice=choice,
    )


def evaluate_character_choice(
    keys: list[T],
    *,
    evaluator: Callable[[T], CharacterChoiceCandidate[T]],
    tiebreak_desc: bool = False,
) -> CharacterChoiceEvaluation[T]:
    candidates = [evaluator(key) for key in keys]
    decision = decide_character_choice(candidates, tiebreak_desc=tiebreak_desc)
    scores = {candidate.key: candidate.score for candidate in candidates}
    reasons = {candidate.key: candidate.reasons for candidate in candidates}
    hard_block_details = {
        candidate.key: dict(candidate.hard_block_detail or {})
        for candidate in candidates
        if candidate.hard_blocked
    }
    hard_blocked_keys = tuple(candidate.key for candidate in candidates if candidate.hard_blocked)
    metadata = {
        candidate.key: dict(candidate.metadata or {})
        for candidate in candidates
        if candidate.metadata
    }
    return CharacterChoiceEvaluation(
        decision=decision,
        scores=scores,
        reasons=reasons,
        hard_blocked_keys=hard_blocked_keys,
        hard_block_details=hard_block_details,
        metadata=metadata,
    )


def evaluate_named_character_choice(
    keys: list[T],
    *,
    resolve_name: Callable[[T], str],
    base_breakdown: Callable[[str], tuple[float, list[str]]],
    survival_policy_advice: Callable[[str], tuple[float, list[str], bool, dict[str, object]]],
    survival_adjustment: Callable[[str], tuple[float, list[str]]],
    marker_bonus_by_name: Mapping[str, float],
    weighted_marker_names: set[str],
    survival_first: bool,
    weight_multiplier: float,
    tiebreak_desc: bool = False,
) -> CharacterChoiceEvaluation[T]:
    policy = build_named_character_choice_policy(
        resolve_name=resolve_name,
        base_breakdown=base_breakdown,
        survival_policy_advice=survival_policy_advice,
        survival_adjustment=survival_adjustment,
        marker_bonus_by_name=marker_bonus_by_name,
        weighted_marker_names=weighted_marker_names,
        survival_first=survival_first,
        weight_multiplier=weight_multiplier,
    )
    return evaluate_named_character_choice_with_policy(
        keys,
        policy=policy,
        tiebreak_desc=tiebreak_desc,
    )


def evaluate_named_character_choice_with_policy(
    keys: list[T],
    *,
    policy: NamedCharacterChoicePolicy[T],
    tiebreak_desc: bool = False,
) -> CharacterChoiceEvaluation[T]:
    def _evaluate(key: T) -> CharacterChoiceCandidate[T]:
        name = policy.resolve_name(key)
        score, why = policy.base_breakdown(name)
        survival_policy_bonus, survival_policy_why, survival_hard_block, survival_detail = policy.survival_policy_advice(name)
        if survival_policy_bonus != 0.0:
            score += survival_policy_bonus
            why = [*why, *survival_policy_why]
        bonus = float(policy.marker_bonus_by_name.get(name, 0.0))
        if bonus > 0.0:
            if policy.survival_first and name in policy.weighted_marker_names:
                bonus *= max(1.0, policy.weight_multiplier)
            score += bonus
            why = [*why, f"distress_marker_bonus={bonus:.2f}"]
        survival_bonus, survival_why = policy.survival_adjustment(name)
        if survival_bonus != 0.0:
            score += survival_bonus
            why = [*why, *survival_why]
        return CharacterChoiceCandidate(
            key=key,
            score=score,
            reasons=tuple(why),
            hard_blocked=survival_hard_block,
            hard_block_detail=dict(survival_detail) if survival_hard_block else None,
            metadata={"survival_severity": dict(survival_detail)} if survival_detail else None,
        )

    return evaluate_character_choice(keys, evaluator=_evaluate, tiebreak_desc=tiebreak_desc)


def summarize_character_choice_debug(
    keys: list[T],
    evaluation: CharacterChoiceEvaluation[T],
    *,
    label_for_key: Callable[[T], str],
) -> CharacterChoiceDebugSummary[T]:
    return CharacterChoiceDebugSummary(
        score_map={label_for_key(key): round(evaluation.scores[key], 3) for key in keys},
        reason_map={label_for_key(key): list(evaluation.reasons[key]) for key in keys},
        hard_blocked_map={
            label_for_key(key): dict(evaluation.hard_block_details[key])
            for key in evaluation.hard_blocked_keys
        },
        metadata_map={
            label_for_key(key): dict(evaluation.metadata[key])
            for key in keys
            if key in evaluation.metadata
        },
    )


def build_character_choice_debug_payload(
    *,
    policy_name: str,
    offered_cards: list[int] | None,
    debug_summary: CharacterChoiceDebugSummary[T],
    generic_survival_score: float,
    survival_urgency: float,
    survival_first: bool,
    survival_weight_multiplier: float,
    chosen_key: T,
    chosen_name: str,
    reasons_for_choice: list[str],
    hard_blocked_map: Mapping[str, dict[str, object]] | None = None,
    character_names_by_key: Mapping[str, str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy": policy_name,
        "candidate_scores": debug_summary.score_map,
        "generic_survival_score": round(generic_survival_score, 3),
        "survival_urgency": round(survival_urgency, 3),
        "survival_first": survival_first,
        "survival_weight_multiplier": round(survival_weight_multiplier, 3),
        "survival_severity_by_candidate": {
            key: debug_summary.metadata_map.get(key, {}).get("survival_severity", {})
            for key in debug_summary.score_map
        },
        "chosen_character": chosen_name,
        "reasons": reasons_for_choice,
    }
    if hard_blocked_map is not None:
        payload["survival_hard_blocked_candidates"] = dict(hard_blocked_map)
    if offered_cards is not None:
        payload["offered_cards"] = offered_cards
        payload["chosen_card"] = chosen_key
    if character_names_by_key is not None:
        payload["candidate_characters"] = dict(character_names_by_key)
    return payload


def build_uniform_random_character_choice_debug_payload(
    *,
    policy_name: str,
    offered_cards: list[int] | None,
    candidate_labels: list[str],
    chosen_key: T,
    chosen_name: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy": policy_name,
        "candidate_scores": {label: 0.0 for label in candidate_labels},
        "chosen_character": chosen_name,
        "reasons": ["uniform_random"],
    }
    if offered_cards is not None:
        payload["offered_cards"] = offered_cards
        payload["chosen_card"] = chosen_key
    return payload


def run_named_character_choice_with_policy(
    keys: list[T],
    *,
    policy: NamedCharacterChoicePolicy[T],
    label_for_key: Callable[[T], str],
    tiebreak_desc: bool = False,
) -> CharacterChoiceRun[T]:
    evaluation = evaluate_named_character_choice_with_policy(
        keys,
        policy=policy,
        tiebreak_desc=tiebreak_desc,
    )
    debug_summary = summarize_character_choice_debug(
        keys,
        evaluation,
        label_for_key=label_for_key,
    )
    return CharacterChoiceRun(
        evaluation=evaluation,
        debug_summary=debug_summary,
        choice=evaluation.decision.choice,
    )
