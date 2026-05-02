from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_RUN_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_RUN_DIR_CACHE: dict[tuple[str, str], Path] = {}


def debug_game_logs_enabled() -> bool:
    raw = os.getenv("MRN_DEBUG_GAME_LOGS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def debug_game_log_dir() -> Path:
    return Path(os.getenv("MRN_DEBUG_GAME_LOG_DIR", ".log").strip() or ".log")


def debug_game_log_run_id() -> str:
    explicit = os.getenv("MRN_DEBUG_GAME_LOG_RUN_ID", "").strip()
    if explicit:
        return _sanitize_run_id(explicit)
    now = datetime.now().astimezone()
    return f"{now:%Y%m%d-%H%M%S}-{now.microsecond:06d}-p{os.getpid()}"


def debug_game_log_run_dir() -> Path:
    base_dir = debug_game_log_dir()
    explicit = os.getenv("MRN_DEBUG_GAME_LOG_RUN_ID", "").strip()
    cache_key = (str(base_dir), explicit or "__auto__")
    with _LOCK:
        cached = _RUN_DIR_CACHE.get(cache_key)
        if cached is not None:
            return cached
        run_dir = base_dir / debug_game_log_run_id()
        _RUN_DIR_CACHE[cache_key] = run_dir
        return run_dir


def build_debug_log_payload(component: str, event: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {
        "component": component,
        "event": event,
        "ts": now.isoformat(timespec="milliseconds"),
        "ts_ms": int(now.timestamp() * 1000),
        **(fields or {}),
    }


def write_game_debug_log(component: str, event: str, **fields: Any) -> None:
    if not debug_game_logs_enabled():
        return
    safe_component = _sanitize_component(component)
    payload = build_debug_log_payload(safe_component, event, {key: value for key, value in fields.items() if value is not None})
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    target = debug_game_log_run_dir() / f"{safe_component}.jsonl"
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")


def _sanitize_component(component: str) -> str:
    normalized = _COMPONENT_RE.sub("_", str(component).strip().lower())
    return normalized.strip("._-") or "debug"


def _sanitize_run_id(run_id: str) -> str:
    normalized = _RUN_ID_RE.sub("_", str(run_id).strip())
    return normalized.strip("._-") or "run"
