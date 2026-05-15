from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/scripts/redis_restart_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("redis_restart_smoke", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_restart_smoke_parser_supports_production_like_topology_commands() -> None:
    script = _load_script()

    args = script.build_parser().parse_args(
        [
            "--skip-up",
            "--topology-name",
            "staging-blue",
            "--compose-file",
            "deploy/redis-runtime/docker-compose.runtime.yml",
            "--restart-command",
            "platform restart server",
            "--restart-command",
            "platform restart workers",
            "--worker-health-command",
            "platform health prompt-timeout-worker",
            "--expected-redis-hash-tag",
            "project-mrn-prod",
            "--decision-smoke",
        ]
    )

    assert args.skip_up is True
    assert args.topology_name == "staging-blue"
    assert args.compose_file == ["deploy/redis-runtime/docker-compose.runtime.yml"]
    assert args.restart_command == ["platform restart server", "platform restart workers"]
    assert args.worker_health_command == ["platform health prompt-timeout-worker"]
    assert args.expected_redis_hash_tag == "project-mrn-prod"
    assert args.decision_smoke is True


def test_restart_smoke_builds_compose_worker_health_commands() -> None:
    script = _load_script()

    commands = script._compose_worker_health_commands(["docker", "compose", "-p", "project mrn"], enabled=True)

    assert len(commands) == 2
    assert "'project mrn'" in commands[0]
    assert "prompt_timeout_worker_app --health" in commands[0]
    assert "command_wakeup_worker_app --health" in commands[1]


def test_restart_smoke_builds_compose_command_with_custom_files() -> None:
    script = _load_script()

    command = script._compose_command(
        "runtime smoke",
        ["docker-compose.yml", "deploy/redis-runtime/docker-compose.runtime.yml"],
    )

    assert command[:4] == ["docker", "compose", "-p", "runtime smoke"]
    assert command.count("-f") == 2
    assert str(ROOT / "docker-compose.yml") in command
    assert str(ROOT / "deploy/redis-runtime/docker-compose.runtime.yml") in command


def test_restart_smoke_allows_disabling_compose_worker_health_commands() -> None:
    script = _load_script()

    assert script._compose_worker_health_commands(["docker"], enabled=False) == []


def test_worker_health_checks_retry_transient_startup_failure(monkeypatch) -> None:
    script = _load_script()
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise script.subprocess.CalledProcessError(returncode=1, cmd=args[0])
        return script.subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(script.time, "sleep", lambda _delay: None)

    assert (
        script._run_worker_health_checks(
            ["worker health"],
            env={},
            phase="before_restart",
            attempts=2,
        )
        == 1
    )
    assert calls == 2


def test_decision_smoke_payload_preserves_prompt_continuation_contract() -> None:
    script = _load_script()

    decision = script._decision_from_prompt(
        {
            "request_id": "sess:r1:t1:p1:draft_card:1",
            "player_id": 1,
            "resume_token": "resume-1",
            "frame_id": "frame-1",
            "module_id": "module-1",
            "module_type": "DraftModule",
            "module_cursor": 3,
            "batch_id": "batch-1",
            "prompt_fingerprint": "fp-1",
            "prompt_fingerprint_version": 1,
        },
        choice_id="8",
    )

    assert decision == {
        "type": "decision",
        "request_id": "sess:r1:t1:p1:draft_card:1",
        "player_id": 1,
        "player_id_alias_role": "legacy_compatibility_alias",
        "primary_player_id": 1,
        "primary_player_id_source": "legacy",
        "choice_id": "8",
        "choice_payload": {},
        "resume_token": "resume-1",
        "frame_id": "frame-1",
        "module_id": "module-1",
        "module_type": "DraftModule",
        "module_cursor": 3,
        "batch_id": "batch-1",
        "prompt_fingerprint": "fp-1",
        "prompt_fingerprint_version": 1,
    }


def test_latest_prompt_for_player_accepts_public_protocol_player_id_with_legacy_alias() -> None:
    script = _load_script()
    prompt = {
        "type": "prompt",
        "payload": {
            "request_id": "req_public_1",
            "player_id": "player_public_1",
            "legacy_player_id": 1,
            "public_player_id": "player_public_1",
            "seat_id": "seat_public_1",
            "viewer_id": "viewer_public_1",
            "legal_choices": [{"choice_id": "roll"}],
        },
    }

    assert script._latest_prompt_for_player({"events": [prompt]}, player_id=1) == prompt["payload"]


def test_decision_smoke_payload_preserves_protocol_identity_companions() -> None:
    script = _load_script()

    decision = script._decision_from_prompt(
        {
            "request_id": "req_public_1",
            "legacy_request_id": "ai_req_1",
            "public_request_id": "req_public_1",
            "public_prompt_instance_id": "ppi_public_1",
            "player_id": "player_public_1",
            "legacy_player_id": 1,
            "public_player_id": "player_public_1",
            "seat_id": "seat_public_1",
            "viewer_id": "viewer_public_1",
        },
        choice_id="roll",
    )

    assert decision == {
        "type": "decision",
        "request_id": "req_public_1",
        "primary_player_id": "player_public_1",
        "primary_player_id_source": "public",
        "choice_id": "roll",
        "choice_payload": {},
        "legacy_request_id": "ai_req_1",
        "public_request_id": "req_public_1",
        "public_prompt_instance_id": "ppi_public_1",
        "legacy_player_id": 1,
        "public_player_id": "player_public_1",
        "seat_id": "seat_public_1",
        "viewer_id": "viewer_public_1",
    }
    assert "player_id" not in decision
    assert "player_id_alias_role" not in decision


def test_decision_smoke_payload_prefers_explicit_primary_identity_over_top_level_alias() -> None:
    script = _load_script()

    decision = script._decision_from_prompt(
        {
            "request_id": "req_public_2",
            "player_id": 2,
            "player_id_alias_role": "legacy_compatibility_alias",
            "primary_player_id": "player_public_2",
            "primary_player_id_source": "public",
            "legacy_player_id": 2,
            "public_player_id": "player_public_2",
            "seat_id": "seat_public_2",
            "viewer_id": "viewer_public_2",
        },
        choice_id="roll",
    )

    assert "player_id" not in decision
    assert "player_id_alias_role" not in decision
    assert decision["primary_player_id"] == "player_public_2"
    assert decision["primary_player_id_source"] == "public"


def test_decision_smoke_payload_ignores_numeric_public_primary_when_public_companion_exists() -> None:
    script = _load_script()

    decision = script._decision_from_prompt(
        {
            "request_id": "req_public_bad_primary",
            "player_id": 2,
            "player_id_alias_role": "legacy_compatibility_alias",
            "primary_player_id": 2,
            "primary_player_id_source": "public",
            "legacy_player_id": 2,
            "public_player_id": "player_public_2",
            "seat_id": "seat_public_2",
            "viewer_id": "viewer_public_2",
        },
        choice_id="roll",
    )

    assert "player_id" not in decision
    assert "player_id_alias_role" not in decision
    assert decision["primary_player_id"] == "player_public_2"
    assert decision["primary_player_id_source"] == "public"
    assert decision["legacy_player_id"] == 2
