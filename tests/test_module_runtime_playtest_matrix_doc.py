from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "GPT"))

MATRIX_DOC = ROOT / "docs/current/engineering/[MATRIX]_MODULE_RUNTIME_PLAYTEST_SCENARIOS.md"
ROUND_ACTION_CONTROL_MATRIX = ROOT / "docs/current/runtime/round-action-control-matrix.md"
TILE_TRAIT_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md"
REDIS_STATE_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md"
SERVER_README = ROOT / "apps/server/README.md"
DEPLOYMENT_CONTRACT_DOC = ROOT / "docs/current/engineering/[CONTRACT]_REDIS_RUNTIME_DEPLOYMENT.md"
DEPLOYMENT_PROCESS_CONTRACT = ROOT / "deploy/redis-runtime/process-contract.json"

REQUIRED_SCENARIOS = {
    "MRN-MOD-001": "첫 턴 실행",
    "MRN-MOD-002": "드래프트 최종 결정",
    "MRN-MOD-003": "산적 지목 후 잔꾀",
    "MRN-MOD-004": "잔꾀 후속 선택",
    "MRN-MOD-005": "운수 추가 이동/도착",
    "MRN-MOD-006": "건설업자 무료 구매",
    "MRN-MOD-007": "파발꾼 주사위 modifier",
    "MRN-MOD-008": "어사 무뢰 억제 modifier",
    "MRN-MOD-009": "재보급 동시 응답",
    "MRN-MOD-010": "라운드 종료 카드 플립",
    "MRN-MOD-011": "프론트 중복 결정 전송",
    "MRN-MOD-012": "prompt continuation mismatch",
    "MRN-MOD-013": "남의 토지 도착 임대료",
    "MRN-MOD-014": "재보급 eligible 스냅샷 재개",
    "MRN-MOD-015": "잔꾀 후속 재시도 idempotency",
}

REQUIRED_COVERAGE_TOKENS = {
    "GPT/test_runtime_sequence_modules.py",
    "GPT/test_runtime_sequence_handlers.py",
    "GPT/test_runtime_turn_handlers.py",
    "GPT/test_tile_effects.py",
    "GPT/test_runtime_effect_inventory.py",
    "apps/server/tests/test_runtime_semantic_guard.py",
    "apps/server/tests/test_prompt_module_continuation.py",
    "apps/web/src/hooks/useGameStream.spec.ts",
    "npm run e2e:module-runtime",
}


def test_module_runtime_playtest_matrix_documents_required_scenarios() -> None:
    text = MATRIX_DOC.read_text(encoding="utf-8")

    for scenario_id, title in REQUIRED_SCENARIOS.items():
        assert scenario_id in text
        assert title in text


def test_module_runtime_playtest_matrix_links_automated_coverage() -> None:
    text = MATRIX_DOC.read_text(encoding="utf-8")

    for token in REQUIRED_COVERAGE_TOKENS:
        assert token in text


def test_runtime_docs_do_not_keep_stale_rent_atomicity_language() -> None:
    combined = "\n".join(
        [
            TILE_TRAIT_PLAN_DOC.read_text(encoding="utf-8"),
            REDIS_STATE_PLAN_DOC.read_text(encoding="utf-8"),
        ]
    )

    forbidden = {
        "split rent payment itself into a queued action if animation/recovery needs a payment boundary",
        "split rent payment itself into an explicit action only if a later prompt/animation boundary needs it",
        "rent payment, force sale/takeover, and global all-player payments stay atomic",
        "rent payment still mutates inside `rent.payment.resolve`",
    }
    for phrase in forbidden:
        assert phrase not in combined

    required = {
        "RentPaymentModule",
        "`resolve_rent_payment`",
        "rent payment is now actionized",
    }
    for phrase in required:
        assert phrase in combined


def test_server_readme_documents_redis_cluster_hash_tag_contract() -> None:
    text = SERVER_README.read_text(encoding="utf-8")

    required = {
        "Redis Cluster",
        "hash tag",
        "MRN_REDIS_KEY_PREFIX=mrn:{project-mrn-prod}",
        "same Redis hash slot",
    }
    for phrase in required:
        assert phrase in text


def test_redis_runtime_deployment_contract_documents_required_process_roles() -> None:
    doc = DEPLOYMENT_CONTRACT_DOC.read_text(encoding="utf-8")
    manifest = json.loads(DEPLOYMENT_PROCESS_CONTRACT.read_text(encoding="utf-8"))

    roles = {role["name"]: role for role in manifest["required_roles"]}
    assert set(roles) == {"server", "prompt-timeout-worker", "command-wakeup-worker"}
    assert roles["prompt-timeout-worker"]["readiness_command"].endswith("prompt_timeout_worker_app --health")
    assert roles["command-wakeup-worker"]["readiness_command"].endswith("command_wakeup_worker_app --health")
    assert "MRN_REDIS_KEY_PREFIX" in manifest["shared_environment"]
    assert any(
        flag.startswith("--expected-redis-hash-tag")
        for flag in manifest["rollout_smoke"]["required_flags"]
    )

    for phrase in {
        "GET /health",
        "MRN_RESTART_RECOVERY_POLICY=keep",
        "worker_health_checks",
        "deploy/redis-runtime/process-contract.json",
    }:
        assert phrase in doc


def test_round_action_control_matrix_covers_runtime_module_catalog_and_effects() -> None:
    from runtime_modules.catalog import MODULE_RULES
    from runtime_modules.effect_inventory import EFFECT_INVENTORY, VIRTUAL_EFFECT_MODULE_FRAME_KINDS
    from runtime_modules.sequence_modules import (
        ACTION_TYPE_TO_MODULE_TYPE,
        FORTUNE_ACTION_TYPE_TO_MODULE_TYPE,
        SIMULTANEOUS_ACTION_TYPES,
    )

    text = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")

    for module_type in MODULE_RULES:
        assert f"`{module_type}`" in text

    for virtual_module_type in VIRTUAL_EFFECT_MODULE_FRAME_KINDS:
        assert f"`{virtual_module_type}`" in text

    for action_type, module_type in ACTION_TYPE_TO_MODULE_TYPE.items():
        assert f"`{action_type}`" in text
        assert f"`{module_type}`" in text

    for action_type, module_type in FORTUNE_ACTION_TYPE_TO_MODULE_TYPE.items():
        assert f"`{action_type}`" in text
        assert f"`{module_type}`" in text
    assert "unknown `resolve_fortune_*` action" in text
    assert "`LegacyActionAdapterModule`" in text
    assert "Legacy Adapter Removal Classification" in text
    assert "migration escape hatch" in text

    for action_type in SIMULTANEOUS_ACTION_TYPES:
        assert f"`{action_type}`" in text
    assert "`SimultaneousResolutionFrame`" in text
    assert "`ResupplyModule`" in text

    for entry in EFFECT_INVENTORY:
        assert f"`{entry.effect_id}`" in text
        assert f"`{entry.producer_module}`" in text
        for module_type in entry.consumer_modules + entry.runtime_boundary_modules:
            assert f"`{module_type}`" in text


def test_round_action_control_matrix_documents_latest_log_revalidation() -> None:
    text = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")

    for phrase in {
        "Latest Play Log Revalidation",
        ".log/20260502-150332-272298-p1/",
        ".log/20260502-150334-677119-p1/",
        "173 times",
        "1 `accepted`, 215 `stale/already_resolved`",
        "0 `RoundEndCardFlipModule` runtime modules",
        "0 `LegacyActionAdapterModule` runtime modules",
    }:
        assert phrase in text
