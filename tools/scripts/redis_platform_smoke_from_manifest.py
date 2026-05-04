#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT_DIR / "deploy/redis-runtime/local-platform-managed.smoke.json"
DEFAULT_CONTRACT = ROOT_DIR / "deploy/redis-runtime/process-contract.json"


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = _resolve_repo_path(path)
    return json.loads(manifest_path.read_text())


def validate_manifest(
    manifest: dict[str, Any],
    *,
    contract_path: str | Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(_resolve_repo_path(contract_path).read_text())
    errors: list[str] = []

    contract_roles = contract.get("required_roles", [])
    contract_role_names = [role.get("name") for role in contract_roles]
    manifest_roles = manifest.get("roles", [])
    manifest_role_names = [role.get("name") for role in manifest_roles]
    roles_by_name = {role.get("name"): role for role in manifest_roles}

    if manifest_role_names != contract_role_names:
        errors.append(f"roles must match process contract order: expected {contract_role_names}, got {manifest_role_names}")

    for contract_role in contract_roles:
        role_name = contract_role.get("name")
        role = roles_by_name.get(role_name)
        if role is None:
            continue
        if role.get("command") != contract_role.get("command"):
            errors.append(f"{role_name}: command does not match process contract")
        if role.get("restart_policy") != contract_role.get("restart_policy"):
            errors.append(f"{role_name}: restart_policy does not match process contract")
        if role.get("restart_recovery_policy") != contract_role.get("restart_recovery_policy"):
            errors.append(f"{role_name}: restart_recovery_policy does not match process contract")
        if not _is_filled_command(role.get("restart_command")):
            errors.append(f"{role_name}: restart_command must be a concrete platform command")
        readiness_command = contract_role.get("readiness_command")
        if readiness_command:
            if role.get("readiness") != {"type": "command", "command": readiness_command}:
                errors.append(f"{role_name}: readiness command does not match process contract")
            if not _is_filled_command(role.get("smoke_health_command")):
                errors.append(f"{role_name}: smoke_health_command must be a concrete platform command")
        elif role.get("readiness") != {"type": "http", "path": "/health"}:
            errors.append(f"{role_name}: api readiness must be GET /health")

    shared_environment = manifest.get("shared_environment", {})
    redis_prefix = shared_environment.get("MRN_REDIS_KEY_PREFIX")
    expected_hash_tag = shared_environment.get("expected_redis_hash_tag")
    if not isinstance(redis_prefix, str) or not redis_prefix:
        errors.append("shared_environment.MRN_REDIS_KEY_PREFIX is required")
    if not isinstance(expected_hash_tag, str) or not expected_hash_tag:
        errors.append("shared_environment.expected_redis_hash_tag is required")
    if isinstance(redis_prefix, str) and isinstance(expected_hash_tag, str):
        if "{" not in redis_prefix or "}" not in redis_prefix:
            errors.append("MRN_REDIS_KEY_PREFIX must include a Redis Cluster hash tag")
        elif f"{{{expected_hash_tag}}}" not in redis_prefix:
            errors.append("expected_redis_hash_tag must match the hash tag inside MRN_REDIS_KEY_PREFIX")

    smoke = manifest.get("rollout_smoke", {})
    contract_smoke = contract.get("rollout_smoke", {})
    if smoke.get("script") != contract_smoke.get("script"):
        errors.append("rollout_smoke.script must match process contract")
    if smoke.get("required_mode") != "--skip-up":
        errors.append("rollout_smoke.required_mode must be --skip-up")
    if not isinstance(smoke.get("topology_name"), str) or not smoke.get("topology_name"):
        errors.append("rollout_smoke.topology_name is required")
    if smoke.get("expected_redis_hash_tag") != expected_hash_tag:
        errors.append("rollout_smoke.expected_redis_hash_tag must match shared environment")
    if not _filled_command_list(smoke.get("restart_commands")):
        errors.append("rollout_smoke.restart_commands must contain concrete restart command(s)")
    if len(smoke.get("worker_health_commands") or []) != 2 or not _filled_command_list(smoke.get("worker_health_commands")):
        errors.append("rollout_smoke.worker_health_commands must contain two concrete worker health commands")
    if smoke.get("decision_smoke") != "--decision-smoke":
        errors.append("rollout_smoke.decision_smoke must be --decision-smoke")

    preflight = manifest.get("preflight") or {}
    preflight_up = preflight.get("up_command")
    preflight_down = preflight.get("down_command")
    if preflight and (not _is_filled_command(preflight_up) or not _is_filled_command(preflight_down)):
        errors.append("preflight up_command and down_command must be concrete commands when preflight is present")

    if errors:
        raise ValueError("; ".join(errors))

    return {
        "ok": True,
        "name": manifest.get("name"),
        "target_topology": manifest.get("target_topology"),
        "roles": manifest_role_names,
        "topology_name": smoke.get("topology_name"),
        "expected_redis_hash_tag": expected_hash_tag,
        "preflight_up_command": preflight_up,
        "preflight_down_command": preflight_down,
        "restart_command_count": len(smoke.get("restart_commands") or []),
        "worker_health_command_count": len(smoke.get("worker_health_commands") or []),
    }


def build_smoke_command(
    manifest: dict[str, Any],
    *,
    contract_path: str | Path = DEFAULT_CONTRACT,
) -> list[str]:
    validate_manifest(manifest, contract_path=contract_path)
    smoke = manifest["rollout_smoke"]
    command = [
        *shlex.split(smoke["script"]),
        smoke["required_mode"],
        "--topology-name",
        smoke["topology_name"],
        "--expected-redis-hash-tag",
        smoke["expected_redis_hash_tag"],
    ]
    for restart_command in smoke["restart_commands"]:
        command.extend(["--restart-command", restart_command])
    for worker_health_command in smoke["worker_health_commands"]:
        command.extend(["--worker-health-command", worker_health_command])
    command.append(smoke["decision_smoke"])
    return command


def build_manifest_env(manifest: dict[str, Any]) -> dict[str, str]:
    shared_environment = manifest.get("shared_environment", {})
    env = os.environ.copy()
    redis_prefix = shared_environment.get("MRN_REDIS_KEY_PREFIX")
    if redis_prefix:
        env["MRN_REDIS_KEY_PREFIX"] = redis_prefix
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Redis runtime platform manifest and run the contract smoke from it."
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Platform-managed smoke manifest path.")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT), help="Process contract path.")
    parser.add_argument("--validate-only", action="store_true", help="Validate the manifest and print JSON evidence.")
    parser.add_argument("--print-command", action="store_true", help="Print the redis_restart_smoke.py command and exit.")
    parser.add_argument("--run", action="store_true", help="Run redis_restart_smoke.py using manifest commands.")
    parser.add_argument("--preflight", action="store_true", help="Run manifest preflight up/down around --run.")
    parser.add_argument("--keep-running", action="store_true", help="Do not run preflight down after --run.")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    validation = validate_manifest(manifest, contract_path=args.contract)
    command = build_smoke_command(manifest, contract_path=args.contract)

    if args.validate_only or not (args.print_command or args.run):
        print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if args.print_command:
        print(" ".join(shlex.quote(part) for part in command))
    if not args.run:
        return 0

    env = build_manifest_env(manifest)
    preflight = manifest.get("preflight") or {}
    up_command = preflight.get("up_command")
    down_command = preflight.get("down_command")
    if args.preflight and up_command:
        _run_shell(up_command, env=env)
    try:
        subprocess.run(command, cwd=ROOT_DIR, env=env, check=True)
    finally:
        if args.preflight and down_command and not args.keep_running:
            _run_shell(down_command, env=env)
    return 0


def _resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate


def _is_filled_command(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return not any(token in value for token in ("<platform", "<deployment", "<hash"))


def _filled_command_list(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(_is_filled_command(item) for item in value)


def _run_shell(command: str, *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT_DIR, env=env, shell=True, check=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
