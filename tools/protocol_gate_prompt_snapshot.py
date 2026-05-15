from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.server.src.infra.redis_client import RedisConnection, RedisConnectionSettings


PROMPT_HASHES = {
    "prompts_pending": ("prompts", "pending"),
    "prompts_resolved": ("prompts", "resolved"),
    "prompt_decisions": ("prompts", "decisions"),
    "prompt_lifecycle": ("prompts", "lifecycle"),
}


def _safe_hlen(client: Any, key: str) -> int | None:
    try:
        return int(client.hlen(key))
    except Exception:
        return None


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    if parts.username:
        host = f"{parts.username}:***@{host}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def _scan_keys(client: Any, pattern: str, limit: int) -> list[str]:
    try:
        iterator = client.scan_iter(match=pattern, count=max(10, limit))
    except Exception:
        return []
    keys: list[str] = []
    try:
        for key in iterator:
            keys.append(str(key))
            if len(keys) >= limit:
                break
    except Exception:
        return keys
    return keys


def build_snapshot(redis_url: str, key_prefix: str, sample_limit: int) -> dict[str, Any]:
    connection = RedisConnection(RedisConnectionSettings(url=redis_url, key_prefix=key_prefix))
    client = connection.client()
    hash_lengths = {
        name: _safe_hlen(client, connection.key(*parts))
        for name, parts in PROMPT_HASHES.items()
    }
    marker_pattern = connection.key("prompts", "*", "debug", "marker")
    bucket_pattern = connection.key("prompts", "*", "debug", "*")
    marker_keys = _scan_keys(client, marker_pattern, sample_limit)
    bucket_keys = [key for key in _scan_keys(client, bucket_pattern, sample_limit) if not key.endswith(":marker")]
    bucket_samples = [
        {
            "key": key,
            "hlen": _safe_hlen(client, key),
        }
        for key in bucket_keys
    ]
    snapshot = {
        "event": "redis_prompt_keyspace_snapshot_start",
        "ts_ms": int(time.time() * 1000),
        "redis_url": _redact_url(redis_url),
        "key_prefix": key_prefix,
        "hash_lengths": hash_lengths,
        "debug_marker_count_sample": len(marker_keys),
        "debug_marker_sample": marker_keys,
        "debug_bucket_sample": bucket_samples,
        "debug_marker_any_sampled": bool(marker_keys),
    }
    connection.close()
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Redis prompt keyspace state before a protocol-gate run.")
    parser.add_argument("--redis-url", default=os.environ.get("MRN_REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--key-prefix", default=os.environ.get("MRN_REDIS_KEY_PREFIX", "mrn"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args()

    snapshot = build_snapshot(args.redis_url, args.key_prefix, max(1, int(args.sample_limit)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
