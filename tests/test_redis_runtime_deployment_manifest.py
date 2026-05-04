from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/redis-runtime/docker-compose.runtime.yml"
ENV_EXAMPLE = ROOT / "deploy/redis-runtime/.env.example"
PROCESS_CONTRACT = ROOT / "deploy/redis-runtime/process-contract.json"
PLATFORM_MANIFEST = ROOT / "deploy/redis-runtime/platform-managed.manifest.template.json"
LOCAL_PLATFORM_SMOKE = ROOT / "deploy/redis-runtime/local-platform-managed.smoke.json"


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(_walk_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for item in value.values():
            strings.extend(_walk_strings(item))
        return strings
    return []


def test_runtime_compose_manifest_covers_process_contract_roles() -> None:
    manifest = MANIFEST.read_text()
    contract = json.loads(PROCESS_CONTRACT.read_text())

    for role in contract["required_roles"]:
        assert f"  {role['name']}:" in manifest
        for part in role["command"].split():
            if part in {"python", "-m", "--host", "0.0.0.0", "--port", "9090"}:
                continue
            assert part in manifest
        readiness = role.get("readiness_command")
        if readiness:
            assert readiness.split("python -m ", 1)[1].split()[0] in manifest
            assert "--health" in manifest


def test_runtime_compose_manifest_requires_shared_redis_hash_tag() -> None:
    manifest = MANIFEST.read_text()
    env_example = ENV_EXAMPLE.read_text()

    assert "${MRN_REDIS_KEY_PREFIX:?" in manifest
    assert "mrn:{project-mrn-prod}" in manifest
    assert "MRN_REDIS_KEY_PREFIX=mrn:{project-mrn-prod}" in env_example


def test_runtime_compose_manifest_avoids_fixed_container_names() -> None:
    manifest = MANIFEST.read_text()

    assert "container_name:" not in manifest
    assert manifest.count("restart: unless-stopped") >= 4


def test_platform_managed_manifest_maps_process_contract_roles() -> None:
    contract = json.loads(PROCESS_CONTRACT.read_text())
    manifest = json.loads(PLATFORM_MANIFEST.read_text())

    roles_by_name = {role["name"]: role for role in manifest["roles"]}
    assert set(roles_by_name) == {role["name"] for role in contract["required_roles"]}

    for contract_role in contract["required_roles"]:
        role = roles_by_name[contract_role["name"]]
        assert role["command"] == contract_role["command"]
        assert role["restart_policy"] == contract_role["restart_policy"]
        assert role["restart_recovery_policy"] == contract_role["restart_recovery_policy"]
        if "readiness_command" in contract_role:
            assert role["readiness"] == {"type": "command", "command": contract_role["readiness_command"]}
            assert role["smoke_health_command"].endswith(contract_role["readiness_command"] + ">")
        else:
            assert role["readiness"] == {"type": "http", "path": "/health"}


def test_platform_managed_manifest_carries_rollout_smoke_contract() -> None:
    contract = json.loads(PROCESS_CONTRACT.read_text())
    manifest = json.loads(PLATFORM_MANIFEST.read_text())
    smoke = manifest["rollout_smoke"]

    assert smoke["script"] == contract["rollout_smoke"]["script"]
    assert smoke["required_mode"] == "--skip-up"
    assert smoke["expected_redis_hash_tag"] == manifest["shared_environment"]["redis_hash_tag_value"]
    assert len(smoke["restart_commands"]) == 3
    assert len(smoke["worker_health_commands"]) == 2
    assert smoke["decision_smoke"] == "--decision-smoke"

    required_flags = set(contract["rollout_smoke"]["required_flags"])
    assert "--skip-up" in required_flags
    assert "--topology-name <deployment-name>" in required_flags
    assert "--expected-redis-hash-tag <hash-tag>" in required_flags
    assert "--restart-command <platform restart command>" in required_flags
    assert "--worker-health-command <prompt timeout worker health command>" in required_flags
    assert "--worker-health-command <command wakeup worker health command>" in required_flags
    assert "--decision-smoke" in required_flags

    evidence = set(contract["rollout_smoke"]["passing_evidence"])
    assert "decision_smoke.accepted_status=accepted" in evidence
    assert "decision_smoke.duplicate_status is stale or rejected" in evidence


def test_platform_managed_manifest_requires_shared_redis_environment() -> None:
    contract = json.loads(PROCESS_CONTRACT.read_text())
    manifest = json.loads(PLATFORM_MANIFEST.read_text())

    shared_required = set(manifest["shared_environment"]["required"])
    assert {"MRN_REDIS_URL", "MRN_REDIS_KEY_PREFIX"} <= shared_required
    assert manifest["shared_environment"]["redis_hash_tag_example"] == "mrn:{project-mrn-prod}"

    for env_name in shared_required:
        assert env_name in contract["shared_environment"]


def test_local_platform_smoke_manifest_is_executable_mapping() -> None:
    contract = json.loads(PROCESS_CONTRACT.read_text())
    template = json.loads(PLATFORM_MANIFEST.read_text())
    smoke_manifest = json.loads(LOCAL_PLATFORM_SMOKE.read_text())

    assert smoke_manifest["source_contract"] == "deploy/redis-runtime/process-contract.json"
    assert smoke_manifest["source_template"] == "deploy/redis-runtime/platform-managed.manifest.template.json"
    assert smoke_manifest["target_topology"] == "local-platform-managed-smoke"
    assert smoke_manifest["shared_environment"]["MRN_REDIS_KEY_PREFIX"] == "mrn:{runtime-platform-decision-smoke}"
    assert smoke_manifest["shared_environment"]["expected_redis_hash_tag"] == "runtime-platform-decision-smoke"

    role_names = {role["name"] for role in smoke_manifest["roles"]}
    assert role_names == {role["name"] for role in contract["required_roles"]}
    assert role_names == {role["name"] for role in template["roles"]}

    strings = _walk_strings(smoke_manifest)
    assert not any("<platform" in value or "<deployment" in value or "<hash" in value for value in strings)
    assert any("up -d --build redis server prompt-timeout-worker command-wakeup-worker" in value for value in strings)
    assert any(value.endswith(" down") for value in strings)

    smoke = smoke_manifest["rollout_smoke"]
    assert smoke["script"] == contract["rollout_smoke"]["script"]
    assert smoke["required_mode"] == "--skip-up"
    assert smoke["topology_name"] == "local-runtime-platform-managed-decision"
    assert smoke["expected_redis_hash_tag"] == smoke_manifest["shared_environment"]["expected_redis_hash_tag"]
    assert smoke["decision_smoke"] == "--decision-smoke"
    assert len(smoke["restart_commands"]) == 1
    assert len(smoke["worker_health_commands"]) == 2

    restart_command = smoke["restart_commands"][0]
    assert "restart server prompt-timeout-worker command-wakeup-worker" in restart_command
    assert "project-mrn-runtime-platform-decision-smoke" in restart_command

    worker_commands = "\n".join(smoke["worker_health_commands"])
    assert "prompt_timeout_worker_app --health" in worker_commands
    assert "command_wakeup_worker_app --health" in worker_commands

    evidence = set(smoke["passing_evidence"])
    assert set(contract["rollout_smoke"]["passing_evidence"]) <= evidence
