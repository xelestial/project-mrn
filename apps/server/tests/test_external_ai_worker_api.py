from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
