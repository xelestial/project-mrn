from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/redis-runtime/docker-compose.runtime.yml"
ENV_EXAMPLE = ROOT / "deploy/redis-runtime/.env.example"
PROCESS_CONTRACT = ROOT / "deploy/redis-runtime/process-contract.json"


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
