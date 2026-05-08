#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings
from apps.server.src.services.redis_state_inspector import RedisStateInspector


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a game session from Redis diagnostic state.")
    parser.add_argument("--session", required=True, help="Session id to inspect.")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("MRN_REDIS_URL") or os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0",
        help="Redis URL. Defaults to MRN_REDIS_URL, REDIS_URL, then redis://127.0.0.1:6379/0.",
    )
    parser.add_argument(
        "--key-prefix",
        default=os.environ.get("MRN_REDIS_KEY_PREFIX") or os.environ.get("REDIS_KEY_PREFIX") or "mrn",
        help="Redis key prefix. Defaults to MRN_REDIS_KEY_PREFIX, REDIS_KEY_PREFIX, then mrn.",
    )
    parser.add_argument("--socket-timeout-ms", type=int, default=1000, help="Redis socket timeout in milliseconds.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--fail-on",
        choices=("none", "warning", "critical"),
        default="none",
        help="Exit non-zero when the report has at least this diagnostic severity.",
    )
    args = parser.parse_args(argv)

    connection = RedisConnection(
        RedisConnectionSettings(
            url=str(args.redis_url),
            key_prefix=str(args.key_prefix),
            socket_timeout_ms=max(50, int(args.socket_timeout_ms)),
        )
    )
    try:
        report = RedisStateInspector(connection).inspect_session(str(args.session))
    finally:
        connection.close()

    json.dump(
        report,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=bool(args.pretty),
    )
    sys.stdout.write("\n")
    return _exit_code(report, fail_on=str(args.fail_on))


def _exit_code(report: dict[str, Any], *, fail_on: str) -> int:
    if fail_on == "none":
        return 0
    status = str(report.get("summary", {}).get("diagnostic_status") or "")
    if fail_on == "critical":
        return 2 if status == "critical" else 0
    if fail_on == "warning":
        return 2 if status in {"warning", "critical"} else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
