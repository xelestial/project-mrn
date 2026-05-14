#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import socket
import ssl
import struct
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


def _runtime_waiting_request_id(runtime: dict[str, Any]) -> str:
    recovery = runtime.get("recovery_checkpoint")
    if not isinstance(recovery, dict):
        return ""
    checkpoint = recovery.get("checkpoint")
    if not isinstance(checkpoint, dict):
        return ""
    return str(checkpoint.get("waiting_prompt_request_id") or "").strip()


_IDENTITY_COMPANION_FIELDS = (
    "legacy_request_id",
    "public_request_id",
    "public_prompt_instance_id",
    "legacy_player_id",
    "public_player_id",
    "seat_id",
    "viewer_id",
)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prompt_legacy_player_id(prompt: dict[str, Any]) -> int | None:
    for field in ("legacy_player_id", "player_id", "seat"):
        legacy_player_id = _optional_int(prompt.get(field))
        if legacy_player_id is not None:
            return legacy_player_id
    return None


def _copy_identity_companions(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field in _IDENTITY_COMPANION_FIELDS:
        value = source.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if field == "legacy_player_id":
            legacy_player_id = _optional_int(value)
            if legacy_player_id is not None:
                target[field] = legacy_player_id
            continue
        target[field] = str(value).strip() if isinstance(value, str) else value


def _prompt_primary_player_identity(prompt: dict[str, Any]) -> tuple[Any, str] | None:
    primary_player_id = prompt.get("primary_player_id")
    primary_player_id_source = str(prompt.get("primary_player_id_source") or "").strip()
    if primary_player_id_source in {"public", "protocol", "legacy"}:
        if isinstance(primary_player_id, int) and not isinstance(primary_player_id, bool):
            return primary_player_id, primary_player_id_source
        if isinstance(primary_player_id, str) and primary_player_id.strip():
            return primary_player_id.strip(), primary_player_id_source

    public_player_id = prompt.get("public_player_id")
    if isinstance(public_player_id, str) and public_player_id.strip():
        return public_player_id.strip(), "public"

    player_id = prompt.get("player_id")
    if isinstance(player_id, str) and player_id.strip() and _optional_int(player_id) is None:
        return player_id.strip(), "protocol"

    legacy_player_id = _prompt_legacy_player_id(prompt)
    if legacy_player_id is not None:
        return legacy_player_id, "legacy"
    return None


def _add_player_identity_metadata(target: dict[str, Any], prompt: dict[str, Any]) -> None:
    if isinstance(target.get("player_id"), int) and not isinstance(target.get("player_id"), bool):
        alias_role = str(prompt.get("player_id_alias_role") or "").strip()
        target["player_id_alias_role"] = (
            alias_role if alias_role == "legacy_compatibility_alias" else "legacy_compatibility_alias"
        )
    primary_identity = _prompt_primary_player_identity(prompt)
    if primary_identity is None:
        return
    primary_player_id, primary_player_id_source = primary_identity
    target["primary_player_id"] = primary_player_id
    target["primary_player_id_source"] = primary_player_id_source


def _prompt_protocol_player_id(prompt: dict[str, Any]) -> Any:
    primary_identity = _prompt_primary_player_identity(prompt)
    if primary_identity is not None:
        primary_player_id, primary_player_id_source = primary_identity
        if primary_player_id_source in {"public", "protocol"}:
            return primary_player_id

    public_player_id = prompt.get("public_player_id")
    if isinstance(public_player_id, str) and public_player_id.strip():
        return public_player_id.strip()

    player_id = prompt.get("player_id")
    if isinstance(player_id, str) and player_id.strip() and _optional_int(player_id) is None:
        return player_id.strip()

    return _prompt_legacy_player_id(prompt) or 0


def _poll_runtime_advanced_from_request(
    base_url: str,
    session_id: str,
    *,
    token: str,
    previous_request_id: str,
    attempts: int = 60,
) -> dict[str, Any]:
    last_status: dict[str, Any] | None = None
    for _ in range(attempts):
        data = _require_ok(
            _http_json("GET", _session_api_url(base_url, session_id, "runtime-status", token=token)),
            "runtime-status-after-decision",
        )
        runtime = data.get("runtime")
        if not isinstance(runtime, dict):
            raise RuntimeError(f"runtime-status returned invalid runtime payload: {data}")
        last_status = runtime
        status = str(runtime.get("status") or "")
        waiting_request_id = _runtime_waiting_request_id(runtime)
        if status in {"completed", "unavailable", "aborted"}:
            return runtime
        if status == "waiting_input" and waiting_request_id and waiting_request_id != previous_request_id:
            return runtime
        time.sleep(1)
    raise RuntimeError(
        "Runtime did not advance from submitted decision request "
        f"{previous_request_id!r}; last={last_status}"
    )


def _latest_prompt_for_player(replay_payload: dict[str, Any], *, player_id: int) -> dict[str, Any]:
    for event in reversed(replay_payload.get("events") or []):
        if not isinstance(event, dict) or event.get("type") != "prompt":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if _prompt_legacy_player_id(payload) != int(player_id):
            continue
        request_id = str(payload.get("request_id") or "").strip()
        legal_choices = payload.get("legal_choices")
        if request_id and isinstance(legal_choices, list) and legal_choices:
            return payload
    raise RuntimeError(f"Could not find an actionable prompt for player {player_id} in replay")


def _first_legal_choice_id(prompt: dict[str, Any]) -> str:
    for choice in prompt.get("legal_choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("choice_id") or "").strip()
        if choice_id:
            return choice_id
    raise RuntimeError(f"Prompt has no legal choice ids: {json.dumps(prompt, ensure_ascii=False)}")


def _decision_from_prompt(prompt: dict[str, Any], *, choice_id: str) -> dict[str, Any]:
    player_id = _prompt_protocol_player_id(prompt)
    decision: dict[str, Any] = {
        "type": "decision",
        "request_id": str(prompt.get("request_id") or ""),
        "player_id": str(player_id).strip() if isinstance(player_id, str) else int(player_id or 0),
        "choice_id": choice_id,
        "choice_payload": {},
    }
    for field in (
        "resume_token",
        "frame_id",
        "module_id",
        "module_type",
        "module_cursor",
        "batch_id",
        "prompt_fingerprint",
        "prompt_fingerprint_version",
    ):
        value = prompt.get(field)
        if value is not None:
            decision[field] = value
    _add_player_identity_metadata(decision, prompt)
    _copy_identity_companions(decision, prompt)
    return decision


class _WebSocketJsonClient:
    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        self._url = url
        self._timeout = timeout
        self._sock: socket.socket | ssl.SSLSocket | None = None

    def __enter__(self) -> "_WebSocketJsonClient":
        parsed = urllib.parse.urlparse(self._url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError(f"Unsupported websocket URL scheme: {parsed.scheme}")
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        raw_sock = socket.create_connection((host, port), timeout=self._timeout)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            self._sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            self._sock = raw_sock
        self._sock.settimeout(self._timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._sock.sendall(request.encode("ascii"))
        response = self._recv_http_response()
        if " 101 " not in response.split("\r\n", 1)[0]:
            raise RuntimeError(f"WebSocket upgrade failed: {response.splitlines()[0] if response else response!r}")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept not in response:
            raise RuntimeError("WebSocket upgrade did not return the expected Sec-WebSocket-Accept")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._sock is not None:
            try:
                self._send_frame(b"", opcode=0x8)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def send_json(self, payload: dict[str, Any]) -> None:
        self._send_frame(json.dumps(payload, ensure_ascii=False).encode("utf-8"), opcode=0x1)

    def recv_json(self) -> dict[str, Any]:
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 0x1:
                data = json.loads(payload.decode("utf-8"))
                if isinstance(data, dict):
                    return data
                raise RuntimeError(f"WebSocket JSON message was not an object: {data!r}")
            if opcode == 0x8:
                raise RuntimeError("WebSocket closed before expected message")
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)

    def _recv_http_response(self) -> str:
        assert self._sock is not None
        chunks: list[bytes] = []
        while b"\r\n\r\n" not in b"".join(chunks):
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("iso-8859-1")

    def _send_frame(self, payload: bytes, *, opcode: int) -> None:
        assert self._sock is not None
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.extend([0x80 | 126])
            header.extend(struct.pack("!H", length))
        else:
            header.extend([0x80 | 127])
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _recv_exact(self, size: int) -> bytes:
        assert self._sock is not None
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                raise RuntimeError("WebSocket connection closed while reading frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_frame(self) -> tuple[int, bytes]:
        first_two = self._recv_exact(2)
        first, second = first_two[0], first_two[1]
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload


def _stream_url(base_url: str, session_id: str, *, token: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    query = urllib.parse.urlencode({"token": token})
    return f"{scheme}://{netloc}/api/v1/sessions/{session_id}/stream?{query}"


def _wait_for_decision_ack(
    client: _WebSocketJsonClient,
    *,
    request_id: str,
    allowed_statuses: set[str],
    attempts: int = 30,
) -> dict[str, Any]:
    for _ in range(attempts):
        message = client.recv_json()
        if message.get("type") != "decision_ack":
            continue
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("request_id") or "") != request_id:
            continue
        status = str(payload.get("status") or "")
        if status not in allowed_statuses:
            raise RuntimeError(f"Unexpected decision ack for {request_id}: {payload}")
        return payload
    raise RuntimeError(f"Did not receive decision_ack for {request_id}")


def _run_decision_smoke(
    base_url: str,
    session_id: str,
    *,
    token: str,
    player_id: int,
    before_replay_count: int,
) -> dict[str, Any]:
    replay = _require_ok(
        _http_json("GET", _session_api_url(base_url, session_id, "replay", token=token)),
        "replay-before-decision",
    )
    prompt = _latest_prompt_for_player(replay, player_id=player_id)
    request_id = str(prompt.get("request_id") or "").strip()
    choice_id = _first_legal_choice_id(prompt)
    decision = _decision_from_prompt(prompt, choice_id=choice_id)
    stream_url = _stream_url(base_url, session_id, token=token)
    with _WebSocketJsonClient(stream_url) as client:
        client.send_json(decision)
        accepted_ack = _wait_for_decision_ack(client, request_id=request_id, allowed_statuses={"accepted"})
        client.send_json(decision)
        duplicate_ack = _wait_for_decision_ack(
            client,
            request_id=request_id,
            allowed_statuses={"stale", "rejected"},
        )

    advanced = _poll_runtime_advanced_from_request(
        base_url,
        session_id,
        token=token,
        previous_request_id=request_id,
    )
    replay_after = _require_ok(
        _http_json("GET", _session_api_url(base_url, session_id, "replay", token=token)),
        "replay-after-decision",
    )
    after_replay_count = len(replay_after.get("events") or [])
    if after_replay_count <= before_replay_count:
        raise RuntimeError(
            f"Replay did not grow after decision smoke: before={before_replay_count}, after={after_replay_count}"
        )
    return {
        "request_id": request_id,
        "choice_id": choice_id,
        "accepted_status": accepted_ack.get("status"),
        "duplicate_status": duplicate_ack.get("status"),
        "duplicate_reason": duplicate_ack.get("reason"),
        "after_status": advanced.get("status"),
        "after_waiting_request_id": _runtime_waiting_request_id(advanced),
        "after_replay_events": after_replay_count,
    }


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
    parser.add_argument(
        "--decision-smoke",
        action="store_true",
        help="After restart, submit one legal websocket decision, submit it again, and verify resume/dedupe.",
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

        _before_health = _verify_backend_health(
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
        after_health = _verify_backend_health(
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
        decision_summary = None
        if args.decision_smoke:
            decision_summary = _run_decision_smoke(
                args.base_url,
                session_id,
                token=session_token,
                player_id=1,
                before_replay_count=after_count,
            )

        summary = {
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
        }
        redis_health = after_health.get("redis") if isinstance(after_health.get("redis"), dict) else {}
        if redis_health:
            summary["redis"] = {
                "cluster_hash_tag": redis_health.get("cluster_hash_tag"),
                "cluster_hash_tag_valid": redis_health.get("cluster_hash_tag_valid"),
            }
        if decision_summary is not None:
            summary["decision_smoke"] = decision_summary
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        if not args.keep_running and not args.skip_up:
            _run([*compose, "down"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
