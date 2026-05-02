from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def debug_game_logs_enabled() -> bool:
    raw = os.getenv("MRN_DEBUG_GAME_LOGS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def debug_game_log_dir() -> Path:
    return Path(os.getenv("MRN_DEBUG_GAME_LOG_DIR", ".log").strip() or ".log")


def build_debug_log_payload(component: str, event: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "component": component,
        "event": event,
        "ts_ms": int(time.time() * 1000),
        **(fields or {}),
    }


def write_game_debug_log(component: str, event: str, **fields: Any) -> None:
    if not debug_game_logs_enabled():
        return
    safe_component = _sanitize_component(component)
    payload = build_debug_log_payload(safe_component, event, {key: value for key, value in fields.items() if value is not None})
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    target = debug_game_log_dir() / f"{safe_component}.jsonl"
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")


def _sanitize_component(component: str) -> str:
    normalized = _COMPONENT_RE.sub("_", str(component).strip().lower())
    return normalized.strip("._-") or "debug"
