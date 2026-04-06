from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _ensure_gpt_import_path() -> None:
    root = Path(__file__).resolve().parents[4]
    gpt_dir = root / "GPT"
    gpt_text = str(gpt_dir)
    if gpt_text not in sys.path:
        sys.path.insert(0, gpt_text)


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _choice_index(legal_choices: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_id = {str(choice.get("choice_id", "")).strip(): choice for choice in legal_choices}
    ids = [choice_id for choice_id in by_id.keys() if choice_id]
    return by_id, ids


def _is_secondary_choice(by_id: dict[str, dict[str, Any]], choice_id: str) -> bool:
    choice = by_id.get(choice_id) or {}
    return bool(choice.get("secondary") is True or choice.get("priority") in {"secondary", "passive"})


def _is_usable_choice(by_id: dict[str, dict[str, Any]], choice_id: str) -> bool:
    choice = by_id.get(choice_id) or {}
    value = choice.get("value")
    if isinstance(value, dict) and "is_usable" in value:
        return bool(value.get("is_usable"))
    return True


def _priority_score_for_choice(by_id: dict[str, dict[str, Any]], choice_id: str) -> float | None:
    choice = by_id.get(choice_id) or {}
    raw = choice.get("priority_score")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    value = choice.get("value")
    if isinstance(value, dict):
        nested = value.get("priority_score")
        if isinstance(nested, (int, float)) and not isinstance(nested, bool):
            return float(nested)
    return None


def _preferred_choice_id_from_context(public_context: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str | None:
    preferred = public_context.get("preferred_choice_id")
    if isinstance(preferred, str) and preferred.strip() and preferred.strip() in by_id:
        return preferred.strip()
    return None


def _first_non_secondary_choice_id(by_id: dict[str, dict[str, Any]], ids: list[str]) -> str:
    for choice_id in ids:
        if choice_id not in {"none", "no"} and not _is_secondary_choice(by_id, choice_id):
            return choice_id
    return ids[0]


def _first_usable_non_secondary_choice_id(by_id: dict[str, dict[str, Any]], ids: list[str]) -> str:
    for choice_id in ids:
        if choice_id not in {"none", "no"} and not _is_secondary_choice(by_id, choice_id) and _is_usable_choice(by_id, choice_id):
            return choice_id
    return _first_non_secondary_choice_id(by_id, ids)


def _best_scored_usable_non_secondary_choice_id(by_id: dict[str, dict[str, Any]], ids: list[str]) -> str | None:
    candidates: list[tuple[float, str]] = []
    for choice_id in ids:
        if choice_id in {"none", "no"} or _is_secondary_choice(by_id, choice_id) or not _is_usable_choice(by_id, choice_id):
            continue
        score = _priority_score_for_choice(by_id, choice_id)
        if score is not None:
            candidates.append((score, choice_id))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]


WORKER_PROFILE_TO_ADAPTER_ID: dict[str, str] = {
    "reference_heuristic": "reference_heuristic_v1",
    "priority_scored": "priority_score_v1",
}


def _normalize_worker_profile(worker_profile: str | None) -> str | None:
    if worker_profile is None:
        return None
    normalized = str(worker_profile).strip().lower()
    return normalized or None


def worker_profile_for_adapter_id(adapter_id: str | None) -> str | None:
    normalized_adapter = str(adapter_id or "").strip().lower()
    for profile, mapped_adapter in WORKER_PROFILE_TO_ADAPTER_ID.items():
        if normalized_adapter == mapped_adapter:
            return profile
    return None


class ReferenceHeuristicDecisionAdapter:
    adapter_id = "reference_heuristic_v1"
    decision_style = "contract_heuristic"
    supported_transports = ["http"]
    supported_request_types = [
        "movement",
        "runaway_step_choice",
        "lap_reward",
        "draft_card",
        "final_character",
        "trick_to_use",
        "purchase_tile",
        "hidden_trick_card",
        "mark_target",
        "coin_placement",
        "geo_bonus",
        "doctrine_relief",
        "active_flip",
        "specific_trick_reward",
        "burden_exchange",
        "pabal_dice_mode",
    ]
    capabilities = [
        "choice_id_response",
        "choice_payload_echo",
        "healthcheck",
        "contract_v1",
        "failure_code_response",
        "worker_identity",
        "priority_scored_choice",
        "preferred_choice_context",
        "adapter_registry_v1",
    ]

    def build_runtime_policy(self, policy_mode: str):
        _ensure_gpt_import_path()
        from policy.factory import PolicyFactory

        return PolicyFactory.create_runtime_policy(policy_mode=policy_mode, lap_policy_mode=policy_mode)

    def choose_choice_id(
        self,
        *,
        request_type: str,
        public_context: dict[str, Any],
        legal_choices: list[dict[str, Any]],
    ) -> str:
        if not legal_choices:
            raise ValueError("no_legal_choices")

        by_id, ids = _choice_index(legal_choices)
        if len(ids) == 1:
            return ids[0]

        preferred_choice_id = _preferred_choice_id_from_context(public_context, by_id)
        if preferred_choice_id is not None:
            return preferred_choice_id

        if request_type == "movement":
            return "dice" if "dice" in by_id else _first_non_secondary_choice_id(by_id, ids)

        if request_type in {"draft_card", "final_character", "hidden_trick_card", "trick_to_use"}:
            return _best_scored_usable_non_secondary_choice_id(by_id, ids) or _first_usable_non_secondary_choice_id(by_id, ids)

        if request_type == "purchase_tile":
            cost = _as_int(public_context.get("cost")) or _as_int(public_context.get("tile_purchase_cost")) or 0
            cash = _as_int(public_context.get("player_cash")) or 0
            if "yes" in by_id and cash >= cost:
                return "yes"
            if "no" in by_id:
                return "no"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "lap_reward":
            scored = _best_scored_usable_non_secondary_choice_id(by_id, ids)
            if scored is not None:
                return scored
            for preferred in ("coins", "shards", "cash"):
                if preferred in by_id:
                    return preferred
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "geo_bonus":
            scored = _best_scored_usable_non_secondary_choice_id(by_id, ids)
            if scored is not None:
                return scored
            for preferred in ("coins", "shards", "cash"):
                if preferred in by_id:
                    return preferred
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "pabal_dice_mode":
            if "plus_one" in by_id:
                return "plus_one"
            if "minus_one" in by_id:
                return "minus_one"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "burden_exchange":
            burden_cost = _as_int(public_context.get("burden_cost"))
            cash = _as_int(public_context.get("player_cash")) or 0
            if burden_cost is not None and "yes" in by_id and burden_cost <= max(0, cash // 3):
                return "yes"
            if "no" in by_id:
                return "no"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "runaway_step_choice":
            if "yes" in by_id:
                return "yes"
            if "take_bonus" in by_id:
                return "take_bonus"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "mark_target":
            preferred_target = _as_int(public_context.get("preferred_target_player_id"))
            if preferred_target is not None:
                preferred_choice_id = str(preferred_target)
                if preferred_choice_id in by_id:
                    return preferred_choice_id
            scored = _best_scored_usable_non_secondary_choice_id(by_id, ids)
            if scored is not None:
                return scored
            for choice_id in ids:
                if choice_id not in {"none", "no"}:
                    return choice_id
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "coin_placement":
            owned_tile_indices = public_context.get("owned_tile_indices")
            if isinstance(owned_tile_indices, list):
                for tile_index in owned_tile_indices:
                    normalized = _as_int(tile_index)
                    if normalized is None:
                        continue
                    choice_id = str(normalized)
                    if choice_id in by_id:
                        return choice_id
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "active_flip":
            for choice_id in ids:
                if choice_id not in {"none", "no"}:
                    return choice_id
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "specific_trick_reward":
            preferred_reward = _as_int(public_context.get("preferred_reward_id"))
            if preferred_reward is not None and str(preferred_reward) in by_id:
                return str(preferred_reward)
            return _best_scored_usable_non_secondary_choice_id(by_id, ids) or _first_non_secondary_choice_id(by_id, ids)

        if request_type == "doctrine_relief":
            preferred_target = _as_int(public_context.get("preferred_target_player_id"))
            if preferred_target is not None and str(preferred_target) in by_id:
                return str(preferred_target)
            return _best_scored_usable_non_secondary_choice_id(by_id, ids) or _first_non_secondary_choice_id(by_id, ids)

        return _first_non_secondary_choice_id(by_id, ids)


class PriorityScoredDecisionAdapter:
    adapter_id = "priority_score_v1"
    decision_style = "priority_scored_contract"
    supported_transports = ["http"]
    supported_request_types = list(ReferenceHeuristicDecisionAdapter.supported_request_types)
    capabilities = [
        "choice_id_response",
        "choice_payload_echo",
        "healthcheck",
        "contract_v1",
        "failure_code_response",
        "worker_identity",
        "priority_scored_choice",
        "preferred_choice_context",
        "adapter_registry_v1",
        "scored_choice_strategy_v1",
    ]

    def build_runtime_policy(self, policy_mode: str):
        class PriorityScoredPolicy:
            def __init__(self, mode: str) -> None:
                self.policy_mode = mode

        return PriorityScoredPolicy(policy_mode)

    def choose_choice_id(
        self,
        *,
        request_type: str,
        public_context: dict[str, Any],
        legal_choices: list[dict[str, Any]],
    ) -> str:
        if not legal_choices:
            raise ValueError("no_legal_choices")

        by_id, ids = _choice_index(legal_choices)
        if len(ids) == 1:
            return ids[0]

        preferred_choice_id = _preferred_choice_id_from_context(public_context, by_id)
        if preferred_choice_id is not None:
            return preferred_choice_id

        scored_choice = _best_scored_usable_non_secondary_choice_id(by_id, ids)

        if request_type == "purchase_tile":
            cost = _as_int(public_context.get("cost")) or _as_int(public_context.get("tile_purchase_cost")) or 0
            cash = _as_int(public_context.get("player_cash")) or 0
            if "yes" in by_id and cash >= cost:
                return "yes"
            if "no" in by_id:
                return "no"
            return scored_choice or _first_non_secondary_choice_id(by_id, ids)

        if request_type == "movement":
            if "dice" in by_id:
                return "dice"
            return scored_choice or _first_non_secondary_choice_id(by_id, ids)

        if request_type in {"lap_reward", "geo_bonus", "draft_card", "final_character", "hidden_trick_card", "trick_to_use"}:
            return scored_choice or _first_usable_non_secondary_choice_id(by_id, ids)

        if request_type in {"specific_trick_reward", "doctrine_relief", "mark_target", "coin_placement", "active_flip"}:
            return scored_choice or _first_non_secondary_choice_id(by_id, ids)

        if request_type == "pabal_dice_mode":
            if scored_choice is not None:
                return scored_choice
            if "plus_one" in by_id:
                return "plus_one"
            if "minus_one" in by_id:
                return "minus_one"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "burden_exchange":
            burden_cost = _as_int(public_context.get("burden_cost"))
            cash = _as_int(public_context.get("player_cash")) or 0
            if burden_cost is not None and "yes" in by_id and burden_cost <= max(0, cash // 2):
                return "yes"
            if scored_choice is not None:
                return scored_choice
            if "no" in by_id:
                return "no"
            return _first_non_secondary_choice_id(by_id, ids)

        if request_type == "runaway_step_choice":
            if scored_choice is not None:
                return scored_choice
            if "take_bonus" in by_id:
                return "take_bonus"
            if "yes" in by_id:
                return "yes"
            return _first_non_secondary_choice_id(by_id, ids)

        return scored_choice or _first_non_secondary_choice_id(by_id, ids)


def build_external_ai_decision_adapter(adapter_id: str | None = None):
    normalized = str(adapter_id or "").strip().lower() or ReferenceHeuristicDecisionAdapter.adapter_id
    if normalized in {
        ReferenceHeuristicDecisionAdapter.adapter_id,
        "contract_heuristic",
        "reference",
    }:
        return ReferenceHeuristicDecisionAdapter()
    if normalized in {
        PriorityScoredDecisionAdapter.adapter_id,
        "priority_scored",
        "scored",
    }:
        return PriorityScoredDecisionAdapter()
    raise ValueError("unsupported_worker_adapter")


class ExternalAiWorkerService:
    """Contract-driven external AI worker.

    The worker consumes canonical request envelopes and chooses one `choice_id`
    from `legal_choices`. It is connected to the existing policy stack through
    `PolicyFactory` so worker runtime uses the same policy-mode vocabulary as
    the in-process AI path, while decision selection itself stays based on the
    external transport contract.
    """

    def __init__(
        self,
        *,
        worker_id: str = "external-ai-worker",
        policy_mode: str = "heuristic_v3_gpt",
        worker_profile: str | None = None,
        worker_adapter: str | None = ReferenceHeuristicDecisionAdapter.adapter_id,
        adapter=None,
    ) -> None:
        self._worker_id = str(worker_id).strip() or "external-ai-worker"
        self._policy_mode = str(policy_mode).strip() or "heuristic_v3_gpt"
        normalized_profile = _normalize_worker_profile(worker_profile)
        if normalized_profile is not None and normalized_profile not in WORKER_PROFILE_TO_ADAPTER_ID:
            raise ValueError("unsupported_worker_profile")
        resolved_worker_adapter = worker_adapter
        if normalized_profile is not None and worker_adapter in {None, "", ReferenceHeuristicDecisionAdapter.adapter_id}:
            resolved_worker_adapter = WORKER_PROFILE_TO_ADAPTER_ID[normalized_profile]
        self._adapter = adapter or build_external_ai_decision_adapter(resolved_worker_adapter)
        self._worker_adapter = str(getattr(self._adapter, "adapter_id", resolved_worker_adapter)).strip() or str(resolved_worker_adapter)
        inferred_profile = worker_profile_for_adapter_id(self._worker_adapter)
        if normalized_profile is not None and inferred_profile is not None and normalized_profile != inferred_profile:
            raise ValueError("worker_profile_adapter_mismatch")
        self._worker_profile = normalized_profile or inferred_profile or "custom"
        self._runtime_policy = self._adapter.build_runtime_policy(self._policy_mode)

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def policy_mode(self) -> str:
        return self._policy_mode

    @property
    def worker_adapter(self) -> str:
        return self._worker_adapter

    @property
    def worker_profile(self) -> str:
        return self._worker_profile

    def choose_choice_id(
        self,
        *,
        request_type: str,
        public_context: dict[str, Any],
        legal_choices: list[dict[str, Any]],
    ) -> str:
        return self._adapter.choose_choice_id(
            request_type=request_type,
            public_context=public_context,
            legal_choices=legal_choices,
        )

    @staticmethod
    def _choice_payload(choice_id: str, legal_choices: list[dict[str, Any]]) -> dict[str, Any] | None:
        for choice in legal_choices:
            if str(choice.get("choice_id", "")).strip() == choice_id:
                return dict(choice)
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "worker_id": self._worker_id,
            "ready": True,
            "policy_mode": self._policy_mode,
            "policy_class": type(self._runtime_policy).__name__,
            "worker_contract_version": "v1",
            "worker_profile": self._worker_profile,
            "worker_adapter": self._worker_adapter,
            "decision_style": str(getattr(self._adapter, "decision_style", "contract_heuristic")),
            "supported_transports": list(getattr(self._adapter, "supported_transports", ["http"])),
            "capabilities": list(getattr(self._adapter, "capabilities", [])),
            "supported_request_types": list(getattr(self._adapter, "supported_request_types", [])),
        }

    def decide(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        request_type = str(request_payload.get("request_type") or "").strip()
        if not request_type:
            raise ValueError("missing_request_type")
        required_capabilities = request_payload.get("required_capabilities") or []
        if not isinstance(required_capabilities, list):
            raise ValueError("invalid_required_capabilities")
        contract_version = str(request_payload.get("worker_contract_version") or "v1").strip().lower()
        if contract_version != "v1":
            raise ValueError("unsupported_contract_version")
        supported_request_types = list(getattr(self._adapter, "supported_request_types", []))
        if request_type not in supported_request_types:
            raise ValueError("unsupported_request_type")
        public_context = dict(request_payload.get("public_context") or {})
        legal_choices = list(request_payload.get("legal_choices") or [])
        choice_id = self.choose_choice_id(
            request_type=request_type,
            public_context=public_context,
            legal_choices=legal_choices,
        )
        metadata = self.describe()
        return {
            "choice_id": choice_id,
            "choice_payload": self._choice_payload(choice_id, legal_choices),
            "worker_id": self._worker_id,
            "policy_mode": self._policy_mode,
            "worker_profile": self._worker_profile,
            "worker_adapter": self._worker_adapter,
            "policy_class": type(self._runtime_policy).__name__,
            "worker_contract_version": metadata["worker_contract_version"],
            "capabilities": metadata["capabilities"],
            "supported_request_types": metadata["supported_request_types"],
            "supported_transports": metadata["supported_transports"],
            "decision_style": metadata["decision_style"],
            "required_capabilities": list(required_capabilities),
            "ready": metadata.get("ready"),
        }
