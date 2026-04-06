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


class ExternalAiWorkerService:
    """Contract-driven external AI worker.

    The worker consumes canonical request envelopes and chooses one `choice_id`
    from `legal_choices`. It is connected to the existing policy stack through
    `PolicyFactory` so worker runtime uses the same policy-mode vocabulary as
    the in-process AI path, while decision selection itself stays based on the
    external transport contract.
    """

    def __init__(self, *, worker_id: str = "external-ai-worker", policy_mode: str = "heuristic_v3_gpt") -> None:
        self._worker_id = str(worker_id).strip() or "external-ai-worker"
        self._policy_mode = str(policy_mode).strip() or "heuristic_v3_gpt"
        self._runtime_policy = self._create_runtime_policy(self._policy_mode)
        self._supported_request_types = [
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

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def policy_mode(self) -> str:
        return self._policy_mode

    def _create_runtime_policy(self, policy_mode: str):
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

        by_id = {str(choice.get("choice_id", "")).strip(): choice for choice in legal_choices}
        ids = [choice_id for choice_id in by_id.keys() if choice_id]
        if len(ids) == 1:
            return ids[0]

        def first_non_secondary() -> str:
            for choice_id in ids:
                if choice_id not in {"none", "no"}:
                    return choice_id
            return ids[0]

        if request_type == "movement":
            return "dice" if "dice" in by_id else first_non_secondary()

        if request_type == "purchase_tile":
            cost = _as_int(public_context.get("cost")) or _as_int(public_context.get("tile_purchase_cost")) or 0
            cash = _as_int(public_context.get("player_cash")) or 0
            if "yes" in by_id and cash >= cost:
                return "yes"
            if "no" in by_id:
                return "no"
            return first_non_secondary()

        if request_type == "lap_reward":
            for preferred in ("coins", "shards", "cash"):
                if preferred in by_id:
                    return preferred
            return first_non_secondary()

        if request_type == "geo_bonus":
            for preferred in ("coins", "shards", "cash"):
                if preferred in by_id:
                    return preferred
            return first_non_secondary()

        if request_type == "pabal_dice_mode":
            if "plus_one" in by_id:
                return "plus_one"
            if "minus_one" in by_id:
                return "minus_one"
            return first_non_secondary()

        if request_type == "burden_exchange":
            burden_cost = _as_int(public_context.get("burden_cost"))
            cash = _as_int(public_context.get("player_cash")) or 0
            if burden_cost is not None and "yes" in by_id and burden_cost <= max(0, cash // 3):
                return "yes"
            if "no" in by_id:
                return "no"
            return first_non_secondary()

        if request_type == "runaway_step_choice":
            if "yes" in by_id:
                return "yes"
            if "take_bonus" in by_id:
                return "take_bonus"
            return first_non_secondary()

        return first_non_secondary()

    @staticmethod
    def _choice_payload(choice_id: str, legal_choices: list[dict[str, Any]]) -> dict[str, Any] | None:
        for choice in legal_choices:
            if str(choice.get("choice_id", "")).strip() == choice_id:
                return dict(choice)
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "worker_id": self._worker_id,
            "policy_mode": self._policy_mode,
            "policy_class": type(self._runtime_policy).__name__,
            "worker_contract_version": "v1",
            "decision_style": "contract_heuristic",
            "supported_transports": ["http"],
            "capabilities": ["choice_id_response", "choice_payload_echo", "healthcheck", "contract_v1"],
            "supported_request_types": list(self._supported_request_types),
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
        if request_type not in self._supported_request_types:
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
            "policy_class": type(self._runtime_policy).__name__,
            "worker_contract_version": metadata["worker_contract_version"],
            "capabilities": metadata["capabilities"],
            "supported_request_types": metadata["supported_request_types"],
            "required_capabilities": list(required_capabilities),
        }
