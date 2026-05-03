from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_DOC = ROOT / "docs/current/engineering/[MATRIX]_MODULE_RUNTIME_PLAYTEST_SCENARIOS.md"
TILE_TRAIT_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md"
REDIS_STATE_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md"
SERVER_README = ROOT / "apps/server/README.md"

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
