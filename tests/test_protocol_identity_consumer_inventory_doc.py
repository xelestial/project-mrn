from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_DOC = ROOT / "docs/current/engineering/PROTOCOL_IDENTITY_CONSUMER_INVENTORY.md"

REQUIRED_CLASSIFICATIONS = {
    "display",
    "engine bridge",
    "compat alias",
    "protocol violation",
}

REQUIRED_CONSUMER_ENTRIES = {
    "apps/web/src/domain/stream/decisionProtocol.ts": "compat alias",
    "apps/web/src/hooks/useGameStream.ts": "compat alias",
    "apps/web/src/headless/HeadlessGameClient.ts": "compat alias",
    "apps/web/src/headless/httpDecisionPolicy.ts": "compat alias",
    "apps/web/src/headless/protocolReplay.ts": "display",
    "apps/web/src/headless/fullStackProtocolHarness.ts": "display",
    "apps/web/src/domain/selectors/streamSelectors.ts": "display",
    "apps/web/src/domain/selectors/promptSelectors.ts": "engine bridge",
    "packages/runtime-contracts/ws/schemas/outbound.decision.schema.json": "compat alias",
    "packages/runtime-contracts/ws/schemas/inbound.prompt.schema.json": "compat alias",
    "packages/runtime-contracts/ws/schemas/inbound.decision_ack.schema.json": "compat alias",
    "packages/runtime-contracts/external-ai/schemas/request.schema.json": "compat alias",
    "apps/server/src/domain/view_state/prompt_selector.py": "compat alias",
    "tools/scripts/external_ai_full_stack_smoke.py": "compat alias",
    "tools/scripts/redis_restart_smoke.py": "compat alias",
    "tools/scripts/game_debug_log_audit.py": "display",
}


def test_protocol_identity_consumer_inventory_documents_required_classifications() -> None:
    text = INVENTORY_DOC.read_text(encoding="utf-8")

    for classification in REQUIRED_CLASSIFICATIONS:
        assert f"`{classification}`" in text


def test_protocol_identity_consumer_inventory_documents_known_consumers() -> None:
    text = INVENTORY_DOC.read_text(encoding="utf-8")

    for path, classification in REQUIRED_CONSUMER_ENTRIES.items():
        assert path in text
        assert f"| `{path}` | `{classification}` |" in text


def test_protocol_identity_consumer_inventory_states_no_current_protocol_violations() -> None:
    text = INVENTORY_DOC.read_text(encoding="utf-8")

    assert "Current `protocol violation` entries: none found" in text
    assert "Do not remove numeric aliases until this inventory has no `compat alias` entries" in text
