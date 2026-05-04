from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

MATRIX_DOC = ROOT / "docs/current/engineering/[MATRIX]_MODULE_RUNTIME_PLAYTEST_SCENARIOS.md"
ROUND_ACTION_CONTROL_MATRIX = ROOT / "docs/current/runtime/round-action-control-matrix.md"
END_TO_END_CONTRACT_DOC = ROOT / "docs/current/runtime/end-to-end-contract.md"
TILE_TRAIT_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md"
REDIS_STATE_PLAN_DOC = ROOT / "docs/current/engineering/[PLAN]_REDIS_AUTHORITATIVE_GAME_STATE.md"
SERVER_README = ROOT / "apps/server/README.md"
WEB_PACKAGE_JSON = ROOT / "apps/web/package.json"
WEB_PROMPT_SELECTOR_SPEC = ROOT / "apps/web/src/domain/selectors/promptSelectors.spec.ts"
WEB_E2E_README = ROOT / "apps/web/e2e/README.md"
WEB_E2E_PARITY_SPEC = ROOT / "apps/web/e2e/parity.spec.ts"
WEB_E2E_FIXTURES_DIR = ROOT / "apps/web/e2e/fixtures"
ONLINE_GAME_API_SPEC = ROOT / "docs/current/api/online-game-api-spec.md"
DEPLOYMENT_CONTRACT_DOC = ROOT / "docs/current/engineering/[CONTRACT]_REDIS_RUNTIME_DEPLOYMENT.md"
DEPLOYMENT_PROCESS_CONTRACT = ROOT / "deploy/redis-runtime/process-contract.json"
ROUND_COMBINATION_REGRESSION_PACK = (
    ROOT / "packages/runtime-contracts/ws/examples/round-combination.regression-pack.json"
)

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
    "engine/test_runtime_sequence_modules.py",
    "engine/test_runtime_sequence_handlers.py",
    "engine/test_runtime_turn_handlers.py",
    "engine/test_tile_effects.py",
    "engine/test_runtime_effect_inventory.py",
    "apps/server/tests/test_runtime_semantic_guard.py",
    "apps/server/tests/test_prompt_module_continuation.py",
    "apps/server/tests/test_command_wakeup_worker.py",
    "apps/web/src/hooks/useGameStream.spec.ts",
    "apps/web/src/features/prompt/promptEffectContextDisplay.spec.ts",
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


def test_module_runtime_playtest_matrix_documents_round_combination_regression_pack() -> None:
    text = MATRIX_DOC.read_text(encoding="utf-8")

    for phrase in {
        "## 6. 1-5 회귀 묶음",
        "`MRN-MOD-003`/`MRN-MOD-004`/`MRN-MOD-015`",
        "CharacterStartModule",
        "TargetJudicatorModule",
        "`FortuneResolveModule -> MapMoveModule -> ArrivalTileModule`",
        "`RoundEndCardFlipModule`은 모든 `PlayerTurnModule`과 child frame이 종료된 뒤에만 실행",
        "`SimultaneousResolutionFrame`만 소유",
        "프론트 생성 request id나 stale continuation이 엔진을 진행시키지 않는지 확인한다",
    }:
        assert phrase in text


def test_round_combination_regression_pack_fixture_matches_matrix_doc() -> None:
    text = MATRIX_DOC.read_text(encoding="utf-8")
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))

    assert pack["pack_id"] == "MRN-MOD-ROUND-COMBINATION-1-5"
    assert "packages/runtime-contracts/ws/examples/round-combination.regression-pack.json" in text
    assert "npm run e2e:module-runtime" in pack["automation_commands"]
    assert set(pack["required_wire_fields"]) == {
        "request_id",
        "request_type",
        "player_id",
        "frame_id",
        "module_id",
        "module_type",
        "module_cursor",
    }
    assert set(pack["simultaneous_wire_fields"]) == {
        "batch_id",
        "missing_player_ids",
        "resume_tokens_by_player_id",
    }
    assert set(pack["forbidden_replay_sources"]) == {
        "round_setup_replay_base",
        "pending_prompt_instance_id - 1",
        "frontend-created request id",
    }

    scenario_ids = {scenario["scenario_id"] for scenario in pack["scenarios"]}
    assert scenario_ids == {"MRN-MOD-003", "MRN-MOD-004", "MRN-MOD-005", "MRN-MOD-010", "MRN-MOD-014", "MRN-MOD-015"}

    for scenario in pack["scenarios"]:
        assert scenario["scenario_id"] in text
        assert scenario["title"] in text
        for module_name in scenario["required_modules"]:
            assert module_name in text
        for token in scenario["automation"]:
            assert token in text

    for invariant in pack["invariants"]:
        assert invariant in text
    for field in pack["required_wire_fields"]:
        assert field in text
    for field in pack["simultaneous_wire_fields"]:
        assert field in text
    for source in pack["forbidden_replay_sources"]:
        assert source in text


def test_round_combination_regression_pack_documents_redis_resume_evidence() -> None:
    text = MATRIX_DOC.read_text(encoding="utf-8")
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))

    evidence = pack["redis_resume_evidence"]
    assert {item["scenario_id"] for item in evidence} == {
        "MRN-MOD-003",
        "MRN-MOD-004",
        "MRN-MOD-005",
        "MRN-MOD-014",
        "MRN-MOD-015",
    }
    for item in evidence:
        assert item["scenario_id"] in text
        assert item["checkpoint_contract"] in text
        for test_name in item["required_tests"]:
            assert test_name in text

    required_contracts = {
        "PromptContinuation + TrickSequenceFrame",
        "PromptContinuation + ActionSequenceFrame",
        "SimultaneousPromptBatchContinuation + SimultaneousResolutionFrame",
    }
    assert required_contracts.issubset({item["checkpoint_contract"] for item in evidence})


def test_round_combination_regression_pack_documents_prompt_decision_contract_matrix() -> None:
    matrix_doc = MATRIX_DOC.read_text(encoding="utf-8")
    control_doc = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))

    rows = pack["prompt_decision_contract_matrix"]
    request_types = {row["request_type"] for row in rows}
    assert request_types == {
        "mark_target",
        "trick_to_use",
        "hidden_trick_card",
        "specific_trick_reward",
        "movement",
        "lap_reward",
        "purchase_tile",
        "coin_placement",
        "burden_exchange",
    }

    required_fields = set(pack["required_wire_fields"])
    simultaneous_fields = set(pack["simultaneous_wire_fields"])
    for row in rows:
        assert required_fields.issubset(set(row["required_wire_fields"]))
        if row["request_type"] == "burden_exchange":
            assert simultaneous_fields.issubset(set(row["required_wire_fields"]))
            assert row["frame_contract"] == "SimultaneousResolutionFrame"
        else:
            assert row["resume_contract"] == "PromptContinuation"
        assert row["request_type"] in matrix_doc
        assert row["request_type"] in control_doc
        assert row["frame_contract"] in control_doc
        for module_type in row["owner_modules"]:
            assert module_type in control_doc
        for forbidden in row["replay_must_not"]:
            assert forbidden in matrix_doc


def test_runtime_end_to_end_contract_covers_prompt_decision_request_types() -> None:
    text = END_TO_END_CONTRACT_DOC.read_text(encoding="utf-8")
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))

    for row in pack["prompt_decision_contract_matrix"]:
        assert row["request_type"] in text

    assert "`coin_placement`" in text
    assert "`score_token_placement`" not in text


def test_prompt_decision_contract_matrix_is_covered_by_frontend_prompt_selector_spec() -> None:
    text = WEB_PROMPT_SELECTOR_SPEC.read_text(encoding="utf-8")
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))

    for row in pack["prompt_decision_contract_matrix"]:
        request_type = row["request_type"]
        assert f'requestType: "{request_type}"' in text or f'request_type: "{request_type}"' in text


def test_browser_e2e_readme_lists_every_parameter_manifest_fixture() -> None:
    readme = WEB_E2E_README.read_text(encoding="utf-8")
    parity_spec = WEB_E2E_PARITY_SPEC.read_text(encoding="utf-8")
    fixture_names = sorted(path.name for path in WEB_E2E_FIXTURES_DIR.glob("*.json"))

    assert fixture_names
    for fixture_name in fixture_names:
        assert f"`fixtures/{fixture_name}`" in readme

    assert "parameter matrix fixture rehydrates seat/economy/dice assumptions" in readme
    assert "parameter matrix fixture rehydrates seat/economy/dice assumptions" in parity_spec


def test_online_game_api_spec_records_parameter_manifest_hardening_coverage() -> None:
    text = ONLINE_GAME_API_SPEC.read_text(encoding="utf-8")

    assert "Parameter manifest hardening coverage" in text
    assert "seat/topology/economy/resources/dice" in text
    assert "parameter_matrix_economy_dice_2seat.json" in text
    assert "broaden manifest contract coverage beyond current reconnect" not in text
    assert "expand manifest variation matrix (seat/topology/economy/dice) in browser E2E" not in text


def test_round_action_control_matrix_documents_trick_mark_loop_gates_and_simultaneous_response_term() -> None:
    text = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")

    for phrase in {
        "Prompt/Decision Contract Matrix",
        "Trick/Mark Loop Structural Gates",
        "Simultaneous response",
        "SimultaneousPromptBatchContinuation",
        "TrickWindowModule may suspend only into a child `TrickSequenceFrame`",
        "completed pre-trick modules must not replay after `TrickSequenceFrame` completion",
        "후속 잔꾀 선택은 `followup_choice_module_id`로 한 번만 삽입",
    }:
        assert phrase in text


def test_round_combination_regression_pack_e2e_titles_are_wired_to_module_runtime_script() -> None:
    pack = json.loads(ROUND_COMBINATION_REGRESSION_PACK.read_text(encoding="utf-8"))
    package = json.loads(WEB_PACKAGE_JSON.read_text(encoding="utf-8"))
    script = package["scripts"]["e2e:module-runtime"]
    spec = (ROOT / "apps/web/e2e/human_play_runtime.spec.ts").read_text(encoding="utf-8")

    assert pack["e2e_grep_titles"]
    for title in pack["e2e_grep_titles"]:
        assert title in script
        assert f'test("{title}"' in spec


def test_redis_state_plan_documents_authoritative_continuation_boundary() -> None:
    text = REDIS_STATE_PLAN_DOC.read_text(encoding="utf-8")

    for phrase in {
        "Authoritative Continuation Boundary",
        "Worker 재실행은 Redis checkpoint rehydration",
        "not a parent turn replay",
        "`PromptContinuation`",
        "`SimultaneousPromptBatchContinuation`",
        "frontend-created request id",
        "mismatched continuation",
        "must not mutate canonical game state",
        "ignores prompt replay aids",
        "raw resume tokens",
    }:
        assert phrase in text


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


def test_redis_state_plan_keeps_module_fortune_as_owned_sequence() -> None:
    text = REDIS_STATE_PLAN_DOC.read_text(encoding="utf-8")

    forbidden = {
        "Direct fortune/forced-move callers still execute inline for compatibility",
        "until their call sites are migrated to enqueue actions",
    }
    for phrase in forbidden:
        assert phrase not in text

    for phrase in {
        "test/plugin-only surfaces guarded by contract tests",
        "`FortuneResolveModule`",
        "`MapMoveModule`",
        "`ArrivalTileModule`",
    }:
        assert phrase in text


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
    assert "rejected with `UnknownActionTypeError` until catalogued" in text
    assert "Action Classification" in text
    assert "UnknownActionTypeError" in text
    assert "uncatalogued action" in text

    for action_type in SIMULTANEOUS_ACTION_TYPES:
        assert f"`{action_type}`" in text
    assert "`SimultaneousResolutionFrame`" in text
    assert "`ResupplyModule`" in text

    for entry in EFFECT_INVENTORY:
        assert f"`{entry.effect_id}`" in text
        assert f"`{entry.producer_module}`" in text
        for module_type in entry.consumer_modules + entry.runtime_boundary_modules:
            assert f"`{module_type}`" in text


def _inventory_line_modules(text: str, label: str) -> set[str]:
    match = re.search(rf"^- {re.escape(label)}: (?P<body>.+)$", text, flags=re.MULTILINE)
    assert match is not None, f"missing inventory line: {label}"
    body = match.group("body").split(". ", 1)[0]
    return set(re.findall(r"`([A-Za-z0-9_]+Module)`", body))


def test_round_action_control_matrix_frame_inventory_matches_catalog_exactly() -> None:
    from runtime_modules.catalog import MODULE_RULES
    from runtime_modules.effect_inventory import VIRTUAL_EFFECT_MODULE_FRAME_KINDS

    text = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")
    documented_round = _inventory_line_modules(text, "RoundFrame modules")
    documented_turn = _inventory_line_modules(text, "TurnFrame modules")
    documented_sequence = (
        _inventory_line_modules(text, "SequenceFrame trick modules")
        | _inventory_line_modules(text, "SequenceFrame action modules")
    )
    documented_simultaneous = _inventory_line_modules(text, "SimultaneousResolutionFrame modules")
    documented_virtual = _inventory_line_modules(text, "Virtual effect modules")

    assert documented_round == {
        module_type for module_type, rule in MODULE_RULES.items() if rule.frame_types == frozenset({"round"})
    }
    assert documented_turn == {
        module_type for module_type, rule in MODULE_RULES.items() if "turn" in rule.frame_types
    }
    assert documented_sequence == {
        module_type for module_type, rule in MODULE_RULES.items() if "sequence" in rule.frame_types
    }
    assert documented_simultaneous == {
        module_type for module_type, rule in MODULE_RULES.items() if rule.frame_types == frozenset({"simultaneous"})
    }
    assert documented_virtual == set(VIRTUAL_EFFECT_MODULE_FRAME_KINDS)


def test_round_action_control_matrix_documents_latest_log_revalidation() -> None:
    text = ROUND_ACTION_CONTROL_MATRIX.read_text(encoding="utf-8")

    for phrase in {
        "Latest Play Log Revalidation",
        ".log/20260502-150332-272298-p1/",
        ".log/20260502-150334-677119-p1/",
        "173 times",
        "1 `accepted`, 215 `stale/already_resolved`",
        "0 `RoundEndCardFlipModule` runtime modules",
    }:
        assert phrase in text
