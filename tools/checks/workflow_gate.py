from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "apps" / "web"
DEFAULT_SEED = 20260509
WORKFLOW_ORDER = ["runtime", "prompt", "redis", "protocol", "rl", "browser"]
DEFAULT_ALL_WORKFLOWS = ["runtime", "prompt", "redis", "protocol", "rl"]


@dataclass(frozen=True)
class RunContext:
    workflows: list[str]
    profile: str = "smoke"
    seed: int = DEFAULT_SEED
    output_dir: Path = ROOT / "tmp" / "workflow-gate"
    base_url: str = "http://127.0.0.1:9091"
    api_base_url: str = "http://127.0.0.1:9090"
    web_base_url: str = "http://127.0.0.1:9000"
    live_protocol: bool = False


@dataclass(frozen=True)
class StageSpec:
    name: str
    cmd: list[str]
    cwd: Path = ROOT
    env: dict[str, str] | None = None
    timeout_seconds: int | None = None


def project_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    return str(venv_python if venv_python.exists() else Path(sys.executable))


def expand_workflows(workflow: str, *, include_browser: bool = False) -> list[str]:
    if workflow == "all":
        workflows = list(DEFAULT_ALL_WORKFLOWS)
        if include_browser:
            workflows.append("browser")
        return workflows
    if workflow not in WORKFLOW_ORDER:
        raise ValueError(f"unknown workflow: {workflow}")
    return [workflow]


def build_workflow_stages(workflow: str, context: RunContext) -> list[StageSpec]:
    python = project_python()
    pytest_base = [python, "-m", "pytest"]
    pythonpath_env = {"PYTHONPATH": _prepend_pythonpath("engine")}

    if workflow == "runtime":
        return [
            StageSpec(
                name="runtime-pytest",
                cmd=pytest_base
                + [
                    "apps/server/tests/test_runtime_semantic_guard.py",
                    "apps/server/tests/test_runtime_service.py",
                    "apps/server/tests/test_runtime_end_to_end_contract.py",
                    "apps/server/tests/test_view_commit_decision_contract.py",
                ],
                env=pythonpath_env,
            )
        ]
    if workflow == "prompt":
        return [
            StageSpec(
                name="prompt-pytest",
                cmd=pytest_base
                + [
                    "apps/server/tests/test_prompt_service.py",
                    "apps/server/tests/test_prompt_module_continuation.py",
                    "apps/server/tests/test_prompt_timeout_worker.py",
                    "apps/server/tests/test_view_state_prompt_selector.py",
                ],
                env=pythonpath_env,
            )
        ]
    if workflow == "redis":
        return [
            StageSpec(
                name="redis-pytest",
                cmd=pytest_base
                + [
                    "apps/server/tests/test_redis_state_inspector.py",
                    "apps/server/tests/test_redis_realtime_services.py",
                    "apps/server/tests/test_redis_persistence.py",
                ],
            )
        ]
    if workflow == "protocol":
        stages = [
            StageSpec(
                name="protocol-headless-vitest",
                cmd=[
                    "npm",
                    "test",
                    "--",
                    "src/headless/HeadlessGameClient.spec.ts",
                    "src/headless/fullStackProtocolHarness.spec.ts",
                    "src/headless/protocolReplay.spec.ts",
                ],
                cwd=WEB_DIR,
            )
        ]
        if context.live_protocol:
            stages.append(
                StageSpec(
                    name="protocol-live-gate",
                    cmd=[
                        "npm",
                        "run",
                        "rl:protocol-gate",
                        "--",
                        "--profile",
                        context.profile,
                        "--base-url",
                        context.base_url,
                        "--seed",
                        str(context.seed),
                        "--output-dir",
                        str(context.output_dir / "protocol" / "live"),
                    ],
                    cwd=WEB_DIR,
                    env=pythonpath_env,
                    timeout_seconds=1_900,
                )
            )
        return stages
    if workflow == "rl":
        return [
            StageSpec(
                name="rl-gate",
                cmd=[
                    python,
                    "tools/checks/rl_gate.py",
                    "--profile",
                    context.profile,
                    "--seed",
                    str(context.seed),
                    "--output-dir",
                    str(context.output_dir / "rl"),
                ],
                env=pythonpath_env,
                timeout_seconds=1_900,
            )
        ]
    if workflow == "browser":
        return [
            StageSpec(
                name="browser-live-full-game",
                cmd=["npm", "run", "e2e:live-full-game"],
                cwd=WEB_DIR,
                env={
                    "MRN_API_BASE_URL": context.api_base_url,
                    "MRN_WEB_BASE_URL": context.web_base_url,
                    "MRN_FULL_GAME_SEED": str(context.seed),
                    "MRN_FULL_GAME_BOUNDED": "1",
                    "MRN_SCREEN_STALL_MS": "60000",
                },
                timeout_seconds=900,
            )
        ]
    raise ValueError(f"unknown workflow: {workflow}")


def run_workflows(context: RunContext) -> dict[str, Any]:
    output_dir = context.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    workflow_reports = []

    for workflow in context.workflows:
        workflow_dir = output_dir / workflow
        workflow_dir.mkdir(parents=True, exist_ok=True)
        stages = [_run_stage(stage, workflow_dir) for stage in build_workflow_stages(workflow, context)]
        workflow_reports.append(
            {
                "name": workflow,
                "ok": all(stage["ok"] for stage in stages),
                "stages": stages,
            }
        )

    report = {
        "ok": all(workflow["ok"] for workflow in workflow_reports),
        "profile": context.profile,
        "seed": context.seed,
        "output_dir": str(output_dir),
        "duration_seconds": round(time.time() - started, 3),
        "workflows": workflow_reports,
    }
    report_path = output_dir / "workflow_report.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _run_stage(stage: StageSpec, workflow_dir: Path) -> dict[str, Any]:
    stdout_path = workflow_dir / f"{stage.name}.stdout.log"
    stderr_path = workflow_dir / f"{stage.name}.stderr.log"
    started = time.time()
    env = os.environ.copy()
    if stage.env:
        env.update(stage.env)
    try:
        completed = subprocess.run(
            stage.cmd,
            cwd=str(stage.cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=stage.timeout_seconds,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        stderr = (stderr + "\n" if stderr else "") + f"timeout after {stage.timeout_seconds}s"
        returncode = 124

    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "name": stage.name,
        "ok": returncode == 0,
        "returncode": returncode,
        "duration_seconds": round(time.time() - started, 3),
        "cmd": stage.cmd,
        "cwd": str(stage.cwd),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _prepend_pythonpath(value: str) -> str:
    existing = os.environ.get("PYTHONPATH")
    return value if not existing else f"{value}{os.pathsep}{existing}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MRN workflow-level test gates.")
    parser.add_argument("--workflow", choices=["all", *WORKFLOW_ORDER], default="all")
    parser.add_argument("--profile", choices=["smoke", "local"], default="smoke")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", default=str(ROOT / "tmp" / "workflow-gate"))
    parser.add_argument("--base-url", default="http://127.0.0.1:9091")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:9090")
    parser.add_argument("--web-base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--include-browser", action="store_true")
    parser.add_argument("--live-protocol", action="store_true")
    args = parser.parse_args(argv)

    workflows = expand_workflows(args.workflow, include_browser=args.include_browser)
    context = RunContext(
        workflows=workflows,
        profile=args.profile,
        seed=args.seed,
        output_dir=Path(args.output_dir),
        base_url=args.base_url,
        api_base_url=args.api_base_url,
        web_base_url=args.web_base_url,
        live_protocol=args.live_protocol,
    )
    report = run_workflows(context)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "profile": report["profile"],
                "seed": report["seed"],
                "output_dir": report["output_dir"],
                "report_path": report["report_path"],
                "workflows": [
                    {"name": workflow["name"], "ok": workflow["ok"]} for workflow in report["workflows"]
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
