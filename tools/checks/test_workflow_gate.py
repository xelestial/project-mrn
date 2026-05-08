from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def test_all_workflow_expands_without_browser_by_default() -> None:
    from tools.checks.workflow_gate import expand_workflows

    assert expand_workflows("all", include_browser=False) == [
        "runtime",
        "prompt",
        "redis",
        "protocol",
        "rl",
    ]


def test_all_workflow_can_include_browser() -> None:
    from tools.checks.workflow_gate import expand_workflows

    assert expand_workflows("all", include_browser=True)[-1] == "browser"


def test_runner_writes_report_and_stage_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.checks.workflow_gate import RunContext, run_workflows

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = run_workflows(
        RunContext(
            workflows=["runtime", "prompt"],
            profile="smoke",
            seed=123,
            output_dir=tmp_path,
        )
    )

    assert report["ok"] is True
    assert [workflow["name"] for workflow in report["workflows"]] == ["runtime", "prompt"]
    assert all(workflow["ok"] for workflow in report["workflows"])
    assert calls
    assert (tmp_path / "workflow_report.json").exists()
    assert (tmp_path / "runtime" / "runtime-pytest.stdout.log").exists()


def test_runner_marks_failed_stage_and_preserves_command_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.checks.workflow_gate import RunContext, run_workflows

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 7, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = run_workflows(
        RunContext(
            workflows=["redis"],
            profile="smoke",
            seed=123,
            output_dir=tmp_path,
        )
    )

    assert report["ok"] is False
    stage = report["workflows"][0]["stages"][0]
    assert stage["ok"] is False
    assert stage["returncode"] == 7
    assert Path(stage["stdout_path"]).read_text(encoding="utf-8") == "out"
    assert Path(stage["stderr_path"]).read_text(encoding="utf-8") == "err"


def test_cli_prints_compact_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from tools.checks import workflow_gate

    def fake_run_workflows(context: workflow_gate.RunContext) -> dict[str, object]:
        assert context.workflows == ["rl"]
        return {
            "ok": True,
            "profile": context.profile,
            "seed": context.seed,
            "output_dir": str(context.output_dir),
            "workflows": [{"name": "rl", "ok": True, "stages": []}],
            "report_path": str(context.output_dir / "workflow_report.json"),
        }

    monkeypatch.setattr(workflow_gate, "run_workflows", fake_run_workflows)

    assert workflow_gate.main(["--workflow", "rl", "--output-dir", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert printed["workflows"] == [{"name": "rl", "ok": True}]
