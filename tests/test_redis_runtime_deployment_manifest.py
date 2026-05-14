from __future__ import annotations

import json
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/redis-runtime/docker-compose.runtime.yml"
ENV_EXAMPLE = ROOT / "deploy/redis-runtime/.env.example"
PROCESS_CONTRACT = ROOT / "deploy/redis-runtime/process-contract.json"
PLATFORM_MANIFEST = ROOT / "deploy/redis-runtime/platform-managed.manifest.template.json"
LOCAL_PLATFORM_SMOKE = ROOT / "deploy/redis-runtime/local-platform-managed.smoke.json"
PLATFORM_SMOKE_SCRIPT = ROOT / "tools/scripts/redis_platform_smoke_from_manifest.py"


def _load_platform_smoke_script():
    spec = importlib.util.spec_from_file_location("redis_platform_smoke_from_manifest", PLATFORM_SMOKE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_platform_smoke_script_builds_restart_smoke_command_from_manifest() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)

    command = module.build_smoke_command(manifest)

    assert command[:3] == ["python3", "tools/scripts/redis_restart_smoke.py", "--skip-up"]
    assert "--topology-name" in command
    assert command[command.index("--topology-name") + 1] == "local-runtime-platform-managed-decision"
    assert "--expected-redis-hash-tag" in command
    assert command[command.index("--expected-redis-hash-tag") + 1] == "runtime-platform-decision-smoke"
    assert command.count("--restart-command") == 1
    assert "restart server prompt-timeout-worker command-wakeup-worker" in command[command.index("--restart-command") + 1]
    assert command.count("--worker-health-command") == 2
    assert command[-1] == "--decision-smoke"


def test_platform_smoke_script_validates_contract_mapping_and_preflight() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)

    validation = module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT)

    assert validation["ok"] is True
    assert validation["target_topology_kind"] == "local_smoke"
    assert validation["external_topology_ready"] is False
    assert validation["rollout_scope"] == "local_contract_proof"
    assert validation["roles"] == ["server", "prompt-timeout-worker", "command-wakeup-worker"]
    assert validation["topology_name"] == "local-runtime-platform-managed-decision"
    assert validation["expected_redis_hash_tag"] == "runtime-platform-decision-smoke"
    assert validation["preflight_up_command"].endswith(
        "up -d --build redis server prompt-timeout-worker command-wakeup-worker"
    )
    assert validation["preflight_down_command"].endswith(" down")


def test_platform_smoke_script_can_require_external_topology_manifest() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)

    try:
        module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT, require_external_topology=True)
    except ValueError as exc:
        assert "external platform manifest" in str(exc)
    else:
        raise AssertionError("local smoke manifest must not satisfy external topology validation")


def test_platform_smoke_script_classifies_filled_external_manifest() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)
    manifest["name"] = "project-mrn-render-staging"
    manifest["target_topology"] = "render-staging"
    manifest.pop("preflight", None)
    manifest["shared_environment"]["MRN_REDIS_KEY_PREFIX"] = "mrn:{project-mrn-staging}"
    manifest["shared_environment"]["expected_redis_hash_tag"] = "project-mrn-staging"
    manifest["rollout_smoke"]["topology_name"] = "render-staging"
    manifest["rollout_smoke"]["expected_redis_hash_tag"] = "project-mrn-staging"
    manifest["rollout_smoke"]["restart_commands"] = ["platformctl restart server workers"]
    manifest["rollout_smoke"]["worker_health_commands"] = [
        "platformctl exec prompt-timeout-worker -- python -m apps.server.src.workers.prompt_timeout_worker_app --health",
        "platformctl exec command-wakeup-worker -- python -m apps.server.src.workers.command_wakeup_worker_app --health",
    ]
    for role in manifest["roles"]:
        role["restart_command"] = f"platformctl restart {role['name']}"
        if role["name"] != "server":
            role["smoke_health_command"] = (
                f"platformctl exec {role['name']} -- {role['readiness']['command']}"
            )

    validation = module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT, require_external_topology=True)

    assert validation["ok"] is True
    assert validation["target_topology_kind"] == "external_platform"
    assert validation["external_topology_ready"] is True
    assert validation["rollout_scope"] == "external_platform_evidence"
    assert validation["preflight_up_command"] == ""
    assert validation["preflight_down_command"] == ""


def test_platform_smoke_script_rejects_local_runtime_commands_as_external_evidence() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)
    manifest["name"] = "project-mrn-render-staging"
    manifest["target_topology"] = "render-staging"

    try:
        module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT, require_external_topology=True)
    except ValueError as exc:
        assert "external platform manifest must not include local runtime preflight" in str(exc)
        assert "external platform commands must not use local Docker compose runtime commands" in str(exc)
    else:
        raise AssertionError("local Docker runtime commands must not satisfy external topology validation")


def test_platform_smoke_script_rejects_generic_placeholder_commands() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)
    manifest["rollout_smoke"]["restart_commands"] = ["<render restart server workers>"]

    try:
        module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT)
    except ValueError as exc:
        assert "rollout_smoke.restart_commands must be filled platform commands" in str(exc)
    else:
        raise AssertionError("generic placeholder command must be rejected")


def test_platform_smoke_script_builds_evidence_from_mixed_smoke_output() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)
    validation = module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT)
    command = module.build_smoke_command(manifest, contract_path=PROCESS_CONTRACT)
    smoke_output = """
+ worker-health[before-restart]#1: command
{"ok": true, "role": "prompt-timeout-worker"}
{
  "ok": true,
  "topology": "local-runtime-platform-managed-decision",
  "session_id": "sess_evidence",
  "prefix": "mrn:{runtime-platform-decision-smoke}",
  "before_status": "waiting_input",
  "after_status": "waiting_input",
  "before_replay_events": 11,
  "after_replay_events": 12,
  "worker_health_checks": 4,
  "redis": {
    "cluster_hash_tag": "runtime-platform-decision-smoke",
    "cluster_hash_tag_valid": true
  },
  "decision_smoke": {
    "request_id": "sess_evidence:r1:t1:p1:draft_card:1",
    "accepted_status": "accepted",
    "duplicate_status": "stale",
    "duplicate_reason": "already_resolved",
    "after_waiting_request_id": "sess_evidence:r1:t1:p1:final_character:1",
    "after_replay_events": 26
  }
}
Container cleanup line
"""

    evidence = module.build_evidence_document(
        manifest=manifest,
        validation=validation,
        command=command,
        smoke_stdout=smoke_output,
    )

    assert evidence["ok"] is True
    assert evidence["manifest"]["path"] == "deploy/redis-runtime/local-platform-managed.smoke.json"
    assert evidence["manifest"]["target_topology_kind"] == "local_smoke"
    assert evidence["manifest"]["external_topology_ready"] is False
    assert evidence["rollout_scope"] == "local_contract_proof"
    assert evidence["validation"]["roles"] == ["server", "prompt-timeout-worker", "command-wakeup-worker"]
    assert evidence["smoke_command"][0:3] == ["python3", "tools/scripts/redis_restart_smoke.py", "--skip-up"]
    assert evidence["smoke_summary"]["session_id"] == "sess_evidence"
    assert evidence["smoke_summary"]["decision_smoke"]["duplicate_status"] == "stale"
    assert evidence["evidence_checks"] == {
        "smoke_ok": True,
        "runtime_stays_waiting_input": True,
        "replay_does_not_shrink": True,
        "workers_checked": True,
        "redis_hash_tag_matches": True,
        "decision_accepts_once": True,
        "duplicate_decision_is_rejected_or_stale": True,
        "decision_advances_replay": True,
    }


def test_platform_smoke_script_marks_evidence_failed_when_dedupe_or_replay_contract_breaks() -> None:
    module = _load_platform_smoke_script()
    manifest = module.load_manifest(LOCAL_PLATFORM_SMOKE)
    validation = module.validate_manifest(manifest, contract_path=PROCESS_CONTRACT)
    command = module.build_smoke_command(manifest, contract_path=PROCESS_CONTRACT)
    smoke_output = """
 worker-health[before-restart]#1: command
 worker-health[after-restart]#1: command
 decision smoke
 output:
 {
   "ok": true,
   "topology": "local-runtime-platform-managed-decision",
   "session_id": "sess_bad_evidence",
   "prefix": "mrn:{runtime-platform-decision-smoke}",
   "before_status": "waiting_input",
   "after_status": "waiting_input",
   "before_replay_events": 11,
   "after_replay_events": 12,
   "worker_health_checks": 4,
   "redis": {
     "cluster_hash_tag": "runtime-platform-decision-smoke",
     "cluster_hash_tag_valid": true
   },
   "decision_smoke": {
     "request_id": "sess_bad_evidence:r1:t1:p1:draft_card:1",
     "accepted_status": "accepted",
     "duplicate_status": "accepted",
     "duplicate_reason": null,
     "after_waiting_request_id": "sess_bad_evidence:r1:t1:p1:final_character:1",
     "after_replay_events": 12
   }
 }
"""

    evidence = module.build_evidence_document(
        manifest=manifest,
        validation=validation,
        command=command,
        smoke_stdout=smoke_output,
    )

    assert evidence["ok"] is False
    assert evidence["evidence_checks"]["smoke_ok"] is True
    assert evidence["evidence_checks"]["duplicate_decision_is_rejected_or_stale"] is False
    assert evidence["evidence_checks"]["decision_advances_replay"] is False
