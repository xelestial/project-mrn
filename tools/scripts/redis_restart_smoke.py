#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Redis-backed backend restart smoke around a live waiting game.")
    parser.add_argument("--base-url", default=os.environ.get("MRN_SMOKE_BASE_URL", "http://127.0.0.1:9090"))
    parser.add_argument("--compose-project", default=os.environ.get("MRN_SMOKE_COMPOSE_PROJECT", "project-mrn"))
    parser.add_argument("--skip-up", action="store_true", help="Reuse an already running compose stack.")
    parser.add_argument("--keep-running", action="store_true", help="Leave compose services running after the smoke.")
    args = parser.parse_args()

    env = dict(os.environ)
    env.setdefault("MRN_COMPOSE_PROJECT", args.compose_project)
    env.setdefault("MRN_REDIS_KEY_PREFIX", f"mrn:{{restart-smoke-{int(time.time())}}}")
    env.setdefault("MRN_RESTART_RECOVERY_POLICY", "keep")

    compose = ["docker", "compose", "-p", args.compose_project, "-f", str(ROOT_DIR / "docker-compose.yml")]
    services = ["redis", "server", "prompt-timeout-worker", "command-wakeup-worker"]

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

        health = _require_ok(_wait_json("GET", f"{args.base_url}/health"), "health")
        redis = health.get("redis") if isinstance(health.get("redis"), dict) else {}
        if env["MRN_REDIS_KEY_PREFIX"].find("{") >= 0 and redis.get("cluster_hash_tag_valid") is not True:
            raise RuntimeError(f"Redis prefix is not cluster-hash-tag valid: {redis}")

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

        _run([*compose, "restart", "server", "prompt-timeout-worker", "command-wakeup-worker"], env=env)
        _require_ok(_wait_json("GET", f"{args.base_url}/health"), "health-after-restart")
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
                    "session_id": session_id,
                    "prefix": env["MRN_REDIS_KEY_PREFIX"],
                    "before_status": before.get("status"),
                    "after_status": after.get("status"),
                    "before_replay_events": before_count,
                    "after_replay_events": after_count,
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
