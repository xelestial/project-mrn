import json
from pathlib import Path

import pytest

from rl.replay import write_replay_row


def test_parse_protocol_gate_summary_ignores_non_json_lines():
    from tools.checks.full_stack_protocol_rl_gate import parse_protocol_gate_summary

    summary = parse_protocol_gate_summary(
        'noise\n{"ok": true, "runtime_status": "completed", "failures": [], "trace_count": 10}\n'
    )

    assert summary["ok"] is True
    assert summary["runtime_status"] == "completed"


def test_parse_protocol_gate_summary_uses_last_json_object():
    from tools.checks.full_stack_protocol_rl_gate import parse_protocol_gate_summary

    summary = parse_protocol_gate_summary(
        '{"event": "progress", "commit_seq": 1}\n{"ok": true, "runtime_status": "completed"}\n'
    )

    assert summary["ok"] is True
    assert summary["runtime_status"] == "completed"


def test_smoke_profile_uses_short_end_rule_by_default():
    from tools.checks.full_stack_protocol_rl_gate import resolve_profile_config

    config = resolve_profile_config("smoke", None)

    assert config == {
        "rules": {
            "end": {
                "alive_players_at_most": 1,
                "f_threshold": 4,
                "monopolies_to_trigger_end": 1,
                "tiles_to_trigger_end": 4,
            }
        }
    }


def test_explicit_profile_config_disables_smoke_defaults():
    from tools.checks.full_stack_protocol_rl_gate import resolve_profile_config

    config = resolve_profile_config("smoke", {"rules": {"end": {"f_threshold": 9}}})

    assert config == {"rules": {"end": {"f_threshold": 9}}}


def test_protocol_gate_command_forwards_reconnect_scenarios(tmp_path: Path):
    from tools.checks.full_stack_protocol_rl_gate import protocol_gate_command

    command = protocol_gate_command(
        base_url="http://127.0.0.1:9091",
        seed=1,
        policy="baseline",
        trace_path=tmp_path / "trace.jsonl",
        replay_path=tmp_path / "replay.jsonl",
        timeout_ms=10_000,
        idle_timeout_ms=1_000,
        policy_http_timeout_ms=500,
        progress_interval_ms=1_000,
        cpu_diagnostic_idle_ms=30_000,
        cpu_low_load_percent=10.0,
        reconnect_scenarios=["after_start", "after_first_prompt", "turn_boundary"],
        require_backend_timing=True,
        backend_docker_compose_project="project-mrn-protocol",
        backend_docker_compose_file="../../docker-compose.protocol.yml",
        backend_docker_compose_service="server",
    )

    reconnect_index = command.index("--reconnect")
    assert command[reconnect_index + 1] == "after_start,after_first_prompt,turn_boundary"
    raw_fallback_index = command.index("--raw-prompt-fallback-delay-ms")
    assert command[raw_fallback_index + 1] == "off"
    cpu_idle_index = command.index("--cpu-diagnostic-idle-ms")
    assert command[cpu_idle_index + 1] == "30000"
    cpu_low_load_index = command.index("--cpu-low-load-percent")
    assert command[cpu_low_load_index + 1] == "10.0"
    command_gate_index = command.index("--max-backend-command-ms")
    assert command[command_gate_index + 1] == "5000"
    transition_gate_index = command.index("--max-backend-transition-ms")
    assert command[transition_gate_index + 1] == "5000"
    assert "--require-backend-timing" in command
    assert command[command.index("--backend-docker-compose-project") + 1] == "project-mrn-protocol"


def test_parse_reconnect_arg_accepts_off_and_rejects_unknown():
    from tools.checks.full_stack_protocol_rl_gate import parse_reconnect_arg

    assert parse_reconnect_arg("off") == []
    assert parse_reconnect_arg("after_start,after_first_prompt,round_boundary") == [
        "after_start",
        "after_first_prompt",
        "round_boundary",
    ]

    with pytest.raises(ValueError, match="invalid reconnect scenario"):
        parse_reconnect_arg("after_start,unknown")


def test_start_protocol_policy_server_cleans_up_when_health_wait_fails(monkeypatch, tmp_path: Path):
    from tools.checks import full_stack_protocol_rl_gate as gate

    class FakeProcess:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False
            self.waited = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True
            self.returncode = -15
            return self.returncode

    fake_process = FakeProcess()

    def fake_popen(*args, **kwargs):
        return fake_process

    def fake_wait_for_http_health(*args, **kwargs):
        raise RuntimeError("not healthy")

    monkeypatch.setattr(gate.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(gate, "wait_for_http_health", fake_wait_for_http_health)
    monkeypatch.setattr(gate, "find_free_port", lambda host: 12345)

    server = gate.start_protocol_policy_server(
        model_dir=tmp_path / "model",
        output_dir=tmp_path / "policy_server",
        startup_timeout=0.01,
    )

    with pytest.raises(RuntimeError, match="not healthy"):
        server.__enter__()

    assert fake_process.terminated is True
    assert fake_process.waited is True
    assert server.stdout_handle.closed is True
    assert server.stderr_handle.closed is True


def test_compute_replay_metrics_uses_authoritative_final_outcomes(tmp_path: Path):
    from tools.checks.full_stack_protocol_rl_gate import compute_replay_metrics

    replay = tmp_path / "replay.jsonl"
    write_replay_row(
        replay,
        {
            "game_id": "sess_1",
            "player_id": 1,
            "reward": {"total": 2.0},
            "outcome": {
                "final_rank": 1,
                "final_player_summary": {"player_id": 1, "cash": 25, "alive": True},
            },
        },
    )
    write_replay_row(
        replay,
        {
            "game_id": "sess_1",
            "player_id": 2,
            "reward": {"total": -1.0},
            "outcome": {
                "final_rank": 4,
                "final_player_summary": {"player_id": 2, "cash": 0, "alive": False},
            },
        },
    )

    metrics = compute_replay_metrics([replay])

    assert metrics["rows"] == 2
    assert metrics["average_reward"] == 0.5
    assert metrics["average_final_rank"] == 2.5
    assert metrics["bankruptcy_rate"] == 0.5


def test_evaluate_full_stack_acceptance_checks_stability_and_quality():
    from tools.checks.full_stack_protocol_rl_gate import evaluate_full_stack_acceptance

    result = evaluate_full_stack_acceptance(
        baseline_summaries=[{"ok": True, "failures": []}],
        candidate_summaries=[{"ok": True, "failures": []}],
        train_row_count=10,
        model_summary={"train_examples": 20},
        baseline_metrics={"average_final_rank": 2.5, "bankruptcy_rate": 0.25, "average_reward": 0.1},
        candidate_metrics={"average_final_rank": 2.7, "bankruptcy_rate": 0.3, "average_reward": -0.2},
        max_avg_rank_delta=0.5,
        max_bankruptcy_rate_delta=0.1,
        min_avg_reward_delta=-0.5,
    )

    assert result["stable"] is True
    assert result["accepted"] is True
    assert all(result["checks"].values())

    rejected = evaluate_full_stack_acceptance(
        baseline_summaries=[{"ok": True, "failures": []}],
        candidate_summaries=[{"ok": False, "failures": ["runtime status is failed"]}],
        train_row_count=10,
        model_summary={"train_examples": 20},
        baseline_metrics={"average_final_rank": 2.5, "bankruptcy_rate": 0.25, "average_reward": 0.1},
        candidate_metrics={"average_final_rank": 4.0, "bankruptcy_rate": 1.0, "average_reward": -2.0},
        max_avg_rank_delta=0.5,
        max_bankruptcy_rate_delta=0.1,
        min_avg_reward_delta=-0.5,
    )

    assert rejected["stable"] is False
    assert rejected["accepted"] is False
    assert json.dumps(rejected["checks"], sort_keys=True)


def test_attach_redis_diagnostics_marks_critical_report_as_gate_failure(monkeypatch, tmp_path: Path):
    from tools.checks import full_stack_protocol_rl_gate as gate

    class FakeInspector:
        def __init__(self, connection):
            self.connection = connection

        def inspect_session(self, session_id):
            assert session_id == "sess_critical"
            return {
                "summary": {"diagnostic_status": "critical"},
                "issues": [
                    {
                        "code": "runtime_failed",
                        "severity": "critical",
                        "message": "서버 런타임이 failed 상태입니다.",
                        "evidence": {},
                    }
                ],
            }

    class FakeConnection:
        def __init__(self, settings):
            self.settings = settings
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(gate, "RedisStateInspector", FakeInspector)
    monkeypatch.setattr(gate, "RedisConnection", FakeConnection)

    summary = gate.attach_redis_diagnostics(
        {"ok": True, "session_id": "sess_critical", "failures": []},
        run_dir=tmp_path,
        fail_on="critical",
        redis_url="redis://example/0",
        key_prefix="mrn-test",
        socket_timeout_ms=123,
    )

    assert summary["ok"] is False
    assert summary["redis_diagnostics"]["checked"] is True
    assert summary["redis_diagnostics"]["diagnostic_status"] == "critical"
    assert summary["redis_diagnostics"]["critical_issue_count"] == 1
    assert "Redis diagnostics reported critical issue(s): runtime_failed" in summary["failures"]
    report = json.loads((tmp_path / "redis_state_report.json").read_text(encoding="utf-8"))
    assert report["issues"][0]["code"] == "runtime_failed"


def test_attach_redis_diagnostics_skips_when_session_id_is_missing(tmp_path: Path):
    from tools.checks import full_stack_protocol_rl_gate as gate

    summary = gate.attach_redis_diagnostics(
        {"ok": False, "failures": ["protocol gate did not emit parseable JSON summary"]},
        run_dir=tmp_path,
        fail_on="critical",
        redis_url="redis://example/0",
        key_prefix="mrn-test",
        socket_timeout_ms=123,
    )

    assert summary["redis_diagnostics"] == {
        "checked": False,
        "reason": "missing_session_id",
    }
    assert not (tmp_path / "redis_state_report.json").exists()


def test_resolve_redis_diagnostics_url_uses_protocol_compose_port(monkeypatch):
    from tools.checks.full_stack_protocol_rl_gate import resolve_redis_diagnostics_url

    monkeypatch.delenv("MRN_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("MRN_PROTOCOL_REDIS_PORT", raising=False)

    assert resolve_redis_diagnostics_url(None, "mrn:protocol") == "redis://127.0.0.1:6380/0"

    monkeypatch.setenv("MRN_PROTOCOL_REDIS_PORT", "6399")
    assert resolve_redis_diagnostics_url(None, "mrn:protocol") == "redis://127.0.0.1:6399/0"
    assert resolve_redis_diagnostics_url("redis://example/0", "mrn:protocol") == "redis://example/0"
    assert resolve_redis_diagnostics_url(None, "mrn") == "redis://127.0.0.1:6379/0"
