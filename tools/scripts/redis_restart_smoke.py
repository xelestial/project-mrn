#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
FIXED_COMPOSE_CONTAINERS = {
    "project-mrn",
    "project-mrn-server",
    "project-mrn-prompt-timeout-worker",
    "project-mrn-command-wakeup-worker",
}


def _run(cmd: list[str], *, env: dict[str, str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT_DIR, env=env, check=True)


def _run_shell(command: str, *, env: dict[str, str], label: str) -> None:
    print(f"+ {label}: {command}", flush=True)
    subprocess.run(command, cwd=ROOT_DIR, env=env, shell=True, check=True)


def _run_worker_health_checks(
    commands: list[str],
    *,
    env: dict[str, str],
    phase: str,
    attempts: int = 30,
    delay_seconds: float = 1.0,
) -> int:
    for command in commands:
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(1, attempts + 1):
            try:
                _run_shell(command, env=env, label=f"worker-health[{phase}]#{attempt}")
                break
            except subprocess.CalledProcessError as exc:
                last_error = exc
                if attempt == attempts:
                    raise
                time.sleep(delay_seconds)
        if last_error is not None:
            print(
                f"worker-health[{phase}] recovered after retry: {command}",
                flush=True,
            )
    return len(commands)


def _existing_fixed_containers() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--format",
                "{{.Names}}\t{{.State}}\t{{.Label \"com.docker.compose.project\"}}\t{{.Label \"com.docker.compose.service\"}}",
            ],
            cwd=ROOT_DIR,
            check=True,
            text=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    containers: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if not parts or parts[0] not in FIXED_COMPOSE_CONTAINERS:
            continue
        while len(parts) < 4:
            parts.append("")
        containers.append(
            {
                "name": parts[0],
                "state": parts[1],
                "project": parts[2],
                "service": parts[3],
            }
        )
    return sorted(containers, key=lambda item: item["name"])


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_json(method: str, url: str, *, attempts: int = 60, delay: float = 1.0) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return _http_json(method, url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _require_ok(response: dict[str, Any], label: str) -> dict[str, Any]:
    if response.get("ok") is not True:
        raise RuntimeError(f"{label} failed: {json.dumps(response, ensure_ascii=False)}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} returned non-object data: {json.dumps(response, ensure_ascii=False)}")
    return data


def _session_api_url(base_url: str, session_id: str, path: str, *, token: str | None = None) -> str:
    url = f"{base_url}/api/v1/sessions/{session_id}/{path.lstrip('/')}"
    if token is None:
        return url
    return f"{url}?{urllib.parse.urlencode({'token': token})}"


def _poll_runtime(base_url: str, session_id: str, *, token: str, wanted: set[str], attempts: int = 60) -> dict[str, Any]:
    last_status: dict[str, Any] | None = None
    for _ in range(attempts):
        data = _require_ok(_http_json("GET", _session_api_url(base_url, session_id, "runtime-status", token=token)), "runtime-status")
        runtime = data.get("runtime")
        if not isinstance(runtime, dict):
            raise RuntimeError(f"runtime-status returned invalid runtime payload: {data}")
        last_status = runtime
        if str(runtime.get("status")) in wanted:
            return runtime
        time.sleep(1)
    raise RuntimeError(f"Runtime never reached {sorted(wanted)}; last={last_status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Redis-backed backend restart smoke around a live waiting game.")
    parser.add_argument("--base-url", default=os.environ.get("MRN_SMOKE_BASE_URL", "http://127.0.0.1:9090"))
    parser.add_argument("--compose-project", default=os.environ.get("MRN_SMOKE_COMPOSE_PROJECT", "project-mrn"))
    parser.add_argument(
        "--compose-file",
        action="append",
        default=None,
        help=(
            "Docker Compose file used for local smoke startup/restart. "
            "May be passed multiple times; defaults to repository docker-compose.yml."
        ),
    )
    parser.add_argument("--topology-name", default=os.environ.get("MRN_SMOKE_TOPOLOGY_NAME", "local-compose"))
    parser.add_argument("--skip-up", action="store_true", help="Reuse an already running compose stack.")
    parser.add_argument("--keep-running", action="store_true", help="Leave compose services running after the smoke.")
    parser.add_argument(
        "--skip-restart",
        action="store_true",
        help="Verify a live topology without restarting roles.",
    )
    parser.add_argument(
        "--restart-command",
        action="append",
        default=[],
        help=(
            "Operator-supplied shell command used to restart production-like roles. "
            "May be passed multiple times; when omitted, local Compose restart is used."
        ),
    )
    parser.add_argument(
        "--worker-health-command",
        action="append",
        default=[],
        help=(
            "Operator-supplied shell command that must exit 0 when worker readiness is healthy. "
            "May be passed multiple times and runs before and after restart."
        ),
    )
    parser.add_argument(
        "--compose-worker-health",
        action="store_true",
        help="Run local Compose worker --health checks even when --skip-up is used.",
    )
    parser.add_argument(
        "--skip-worker-health",
        action="store_true",
        help="Do not run worker --health readiness checks.",
    )
    parser.add_argument(
        "--expected-redis-hash-tag",
        default=os.environ.get("MRN_SMOKE_EXPECTED_REDIS_HASH_TAG"),
        help="Fail unless /health reports this Redis Cluster hash tag.",
    )
    return parser


def _resolve_compose_file(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return str(candidate)


def _compose_command(project: str, compose_files: list[str] | None) -> list[str]:
    command = ["docker", "compose", "-p", project]
    for compose_file in compose_files or [str(ROOT_DIR / "docker-compose.yml")]:
        command.extend(["-f", _resolve_compose_file(compose_file)])
    return command


def _compose_worker_health_commands(compose: list[str], *, enabled: bool) -> list[str]:
    if not enabled:
        return []
    quoted = " ".join(shlex.quote(part) for part in compose)
    return [
        f"{quoted} exec -T prompt-timeout-worker python -m apps.server.src.workers.prompt_timeout_worker_app --health",
        f"{quoted} exec -T command-wakeup-worker python -m apps.server.src.workers.command_wakeup_worker_app --health",
    ]


def _verify_backend_health(
    base_url: str,
    *,
    key_prefix: str,
    expected_hash_tag: str | None,
    label: str,
) -> dict[str, Any]:
    health = _require_ok(_wait_json("GET", f"{base_url}/health"), label)
    redis = health.get("redis") if isinstance(health.get("redis"), dict) else {}
    if key_prefix.find("{") >= 0 and redis.get("cluster_hash_tag_valid") is not True:
        raise RuntimeError(f"Redis prefix is not cluster-hash-tag valid: {redis}")
    if expected_hash_tag is not None and redis.get("cluster_hash_tag") != expected_hash_tag:
        raise RuntimeError(
            f"Redis hash tag mismatch: expected={expected_hash_tag!r}, actual={redis.get('cluster_hash_tag')!r}"
        )
    return health


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env = dict(os.environ)
    env.setdefault("MRN_COMPOSE_PROJECT", args.compose_project)
    env.setdefault("MRN_REDIS_KEY_PREFIX", f"mrn:{{restart-smoke-{int(time.time())}}}")
    env.setdefault("MRN_RESTART_RECOVERY_POLICY", "keep")

    compose = _compose_command(args.compose_project, args.compose_file)
    services = ["redis", "server", "prompt-timeout-worker", "command-wakeup-worker"]
    worker_health_commands: list[str] = []
    if not args.skip_worker_health:
        compose_health_enabled = (not args.skip_up) or args.compose_worker_health
        worker_health_commands.extend(_compose_worker_health_commands(compose, enabled=compose_health_enabled))
        worker_health_commands.extend(args.worker_health_command)

    try:
        if not args.skip_up:
            existing = _existing_fixed_containers()
            foreign = [
                item for item in existing if item["project"] and item["project"] != args.compose_project
            ]
            if foreign:
                details = ", ".join(
                    f'{item["name"]}(project={item["project"]}, state={item["state"]})'
                    for item in foreign
                )
                raise RuntimeError(
                    "Existing fixed-name MRN Docker containers belong to another Compose project: "
                    + details
                    + f". Re-run with --compose-project {foreign[0]['project']!r} or clear that stack first."
                )
            running = [item for item in existing if item["state"] == "running"]
            if running and env.get("MRN_SMOKE_REPLACE_EXISTING") != "1":
                raise RuntimeError(
                    "Running MRN Docker containers would be affected by this smoke: "
                    + ", ".join(item["name"] for item in running)
                    + ". Stop them first, use --skip-up for that already running stack, "
                    + "or set MRN_SMOKE_REPLACE_EXISTING=1."
                )
            _run([*compose, "up", "-d", "--build", *services], env=env)

        _verify_backend_health(
            args.base_url,
            key_prefix=env["MRN_REDIS_KEY_PREFIX"],
            expected_hash_tag=args.expected_redis_hash_tag,
            label="health",
        )
        worker_health_check_count = _run_worker_health_checks(worker_health_commands, env=env, phase="before-restart")

        created = _require_ok(
            _http_json(
                "POST",
                f"{args.base_url}/api/v1/sessions",
                {
                    "seats": [
                        {"seat": 1, "seat_type": "human"},
                        {"seat": 2, "seat_type": "ai", "ai_profile": "balanced"},
                        {"seat": 3, "seat_type": "ai", "ai_profile": "balanced"},
                        {"seat": 4, "seat_type": "ai", "ai_profile": "balanced"},
                    ],
                    "config": {"seed": 42},
                },
            ),
            "create-session",
        )
        session_id = str(created["session_id"])
        join_token = str(dict(created["join_tokens"])["1"])
        joined = _require_ok(
            _http_json(
                "POST",
                f"{args.base_url}/api/v1/sessions/{session_id}/join",
                {"seat": 1, "join_token": join_token, "display_name": "Restart Smoke"},
            ),
            "join-seat",
        )
        session_token = str(joined["session_token"])
        _require_ok(
            _http_json(
                "POST",
                f"{args.base_url}/api/v1/sessions/{session_id}/start",
                {"host_token": str(created["host_token"])},
            ),
            "start-session",
        )

        before = _poll_runtime(args.base_url, session_id, token=session_token, wanted={"waiting_input"})
        before_replay = _require_ok(_http_json("GET", _session_api_url(args.base_url, session_id, "replay", token=session_token)), "replay-before")
        before_count = len(before_replay.get("events") or [])

        if not args.skip_restart:
            if args.restart_command:
                for command in args.restart_command:
                    _run_shell(command, env=env, label="restart")
                restart_mode = "custom-command"
            else:
                _run([*compose, "restart", "server", "prompt-timeout-worker", "command-wakeup-worker"], env=env)
                restart_mode = "compose"
        else:
            restart_mode = "skipped"
        _verify_backend_health(
            args.base_url,
            key_prefix=env["MRN_REDIS_KEY_PREFIX"],
            expected_hash_tag=args.expected_redis_hash_tag,
            label="health-after-restart",
        )
        worker_health_check_count += _run_worker_health_checks(worker_health_commands, env=env, phase="after-restart")
        after = _poll_runtime(args.base_url, session_id, token=session_token, wanted={"waiting_input"})
        if str(after.get("status")) in {"unavailable", "recovery_required", "aborted"}:
            raise RuntimeError(f"Runtime became unsafe after restart: {after}")

        after_replay = _require_ok(_http_json("GET", _session_api_url(args.base_url, session_id, "replay", token=session_token)), "replay-after")
        after_count = len(after_replay.get("events") or [])
        if after_count < before_count:
            raise RuntimeError(f"Replay shrank across restart: before={before_count}, after={after_count}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "topology": args.topology_name,
                    "restart_mode": restart_mode,
                    "session_id": session_id,
                    "prefix": env["MRN_REDIS_KEY_PREFIX"],
                    "before_status": before.get("status"),
                    "after_status": after.get("status"),
                    "before_replay_events": before_count,
                    "after_replay_events": after_count,
                    "worker_health_checks": worker_health_check_count,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if not args.keep_running and not args.skip_up:
            _run([*compose, "down"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
