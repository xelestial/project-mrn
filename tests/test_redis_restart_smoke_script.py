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
            "--restart-command",
            "platform restart server",
            "--restart-command",
            "platform restart workers",
            "--worker-health-command",
            "platform health prompt-timeout-worker",
            "--expected-redis-hash-tag",
            "project-mrn-prod",
        ]
    )

    assert args.skip_up is True
    assert args.topology_name == "staging-blue"
    assert args.restart_command == ["platform restart server", "platform restart workers"]
    assert args.worker_health_command == ["platform health prompt-timeout-worker"]
    assert args.expected_redis_hash_tag == "project-mrn-prod"


def test_restart_smoke_builds_compose_worker_health_commands() -> None:
    script = _load_script()

    commands = script._compose_worker_health_commands(["docker", "compose", "-p", "project mrn"], enabled=True)

    assert len(commands) == 2
    assert "'project mrn'" in commands[0]
    assert "prompt_timeout_worker_app --health" in commands[0]
    assert "command_wakeup_worker_app --health" in commands[1]


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
