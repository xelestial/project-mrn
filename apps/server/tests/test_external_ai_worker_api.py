from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from apps.server.src.external_ai_app import create_app
    from apps.server.src.services.external_ai_worker_service import ExternalAiWorkerService

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    TestClient = None
    create_app = None
    ExternalAiWorkerService = None
    FASTAPI_AVAILABLE = False


def _purchase_tile_payload(*, cash: int = 8, cost: int = 4) -> dict[str, object]:
    return {
        "request_id": "req_worker_1",
        "session_id": "sess_worker_1",
        "seat": 1,
        "player_id": 1,
        "decision_name": "choose_purchase_tile",
        "request_type": "purchase_tile",
        "fallback_policy": "local_ai",
        "public_context": {
            "player_cash": cash,
            "cost": cost,
            "tile_index": 9,
        },
        "legal_choices": [
            {"choice_id": "yes", "title": "Buy tile", "value": {"purchased": True}},
            {"choice_id": "no", "title": "Skip", "value": {"purchased": False}},
        ],
        "transport": "http",
    }


def _mark_target_payload() -> dict[str, object]:
    return {
        "request_id": "req_worker_mark_1",
        "session_id": "sess_worker_mark_1",
        "seat": 1,
        "player_id": 1,
        "decision_name": "choose_mark_target",
        "request_type": "mark_target",
        "fallback_policy": "local_ai",
        "public_context": {
            "actor_name": "Bandit",
        },
        "legal_choices": [
            {"choice_id": "2", "title": "Target P2", "value": {"target_player_id": 2}},
            {"choice_id": "3", "title": "Target P3", "value": {"target_player_id": 3}},
        ],
        "transport": "http",
    }


def _specific_trick_reward_payload() -> dict[str, object]:
    return {
        "request_id": "req_worker_reward_1",
        "session_id": "sess_worker_reward_1",
        "seat": 1,
        "player_id": 1,
        "decision_name": "choose_specific_trick_reward",
        "request_type": "specific_trick_reward",
        "fallback_policy": "local_ai",
        "public_context": {
            "preferred_reward_id": 102,
        },
        "legal_choices": [
            {"choice_id": "101", "title": "Reward 101", "value": {"reward_id": 101}},
            {"choice_id": "102", "title": "Reward 102", "value": {"reward_id": 102}},
        ],
        "transport": "http",
    }


def _trick_to_use_payload() -> dict[str, object]:
    return {
        "request_id": "req_worker_trick_1",
        "session_id": "sess_worker_trick_1",
        "seat": 1,
        "player_id": 1,
        "decision_name": "choose_trick_to_use",
        "request_type": "trick_to_use",
        "fallback_policy": "local_ai",
        "public_context": {},
        "legal_choices": [
            {"choice_id": "deck_11", "title": "Hidden trick", "secondary": True, "value": {"is_usable": False}},
            {"choice_id": "deck_12", "title": "Usable trick", "value": {"is_usable": True}},
            {"choice_id": "none", "title": "Skip"},
        ],
        "transport": "http",
    }


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class ExternalAiWorkerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        service = ExternalAiWorkerService(worker_id="worker-api-test", policy_mode="heuristic_v3_gpt")
        self.client = TestClient(create_app(service))

    def test_health_exposes_worker_metadata(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["worker_id"], "worker-api-test")
        self.assertEqual(payload["policy_mode"], "heuristic_v3_gpt")
        self.assertEqual(payload["decision_style"], "contract_heuristic")
        self.assertEqual(payload["supported_transports"], ["http"])
        self.assertEqual(payload["worker_contract_version"], "v1")
        self.assertIn("choice_id_response", payload["capabilities"])
        self.assertIn("worker_identity", payload["capabilities"])
        self.assertIn("purchase_tile", payload["supported_request_types"])

    def test_decide_returns_choice_id_and_choice_payload(self) -> None:
        response = self.client.post("/decide", json=_purchase_tile_payload(cash=8, cost=4))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["choice_id"], "yes")
        self.assertEqual(payload["choice_payload"]["choice_id"], "yes")
        self.assertEqual(payload["worker_id"], "worker-api-test")
        self.assertEqual(payload["worker_contract_version"], "v1")
        self.assertIn("healthcheck", payload["capabilities"])

    def test_decide_handles_mark_target_contract(self) -> None:
        response = self.client.post("/decide", json=_mark_target_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["choice_id"], "2")
        self.assertEqual(payload["choice_payload"]["value"]["target_player_id"], 2)

    def test_decide_prefers_contextual_specific_trick_reward(self) -> None:
        response = self.client.post("/decide", json=_specific_trick_reward_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["choice_id"], "102")
        self.assertEqual(payload["choice_payload"]["value"]["reward_id"], 102)

    def test_decide_prefers_usable_non_secondary_trick(self) -> None:
        response = self.client.post("/decide", json=_trick_to_use_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["choice_id"], "deck_12")

    def test_decide_rejects_requests_without_legal_choices(self) -> None:
        payload = _purchase_tile_payload()
        payload["legal_choices"] = []

        response = self.client.post("/decide", json=payload)

        self.assertEqual(response.status_code, 400)
        error = response.json()["detail"]["error"]
        self.assertEqual(error["code"], "EXTERNAL_AI_INVALID_REQUEST")
        self.assertEqual(error["message"], "no_legal_choices")

    def test_decide_rejects_unsupported_contract_version(self) -> None:
        payload = _purchase_tile_payload()
        payload["worker_contract_version"] = "v2"

        response = self.client.post("/decide", json=payload)

        self.assertEqual(response.status_code, 400)
        error = response.json()["detail"]["error"]
        self.assertEqual(error["message"], "unsupported_contract_version")

    def test_auth_required_rejects_missing_or_wrong_header(self) -> None:
        service = ExternalAiWorkerService(worker_id="worker-api-auth", policy_mode="heuristic_v3_gpt")
        with patch.dict(
            "os.environ",
            {
                "MRN_EXTERNAL_AI_AUTH_TOKEN": "worker-secret",
                "MRN_EXTERNAL_AI_AUTH_HEADER_NAME": "X-Worker-Auth",
                "MRN_EXTERNAL_AI_AUTH_SCHEME": "Token",
            },
            clear=False,
        ):
            client = TestClient(create_app(service))

        unauthorized = client.get("/health")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.json()["detail"]["error"]["code"], "EXTERNAL_AI_UNAUTHORIZED")

        response = client.get("/health", headers={"X-Worker-Auth": "Token worker-secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["worker_id"], "worker-api-auth")


if __name__ == "__main__":
    unittest.main()
