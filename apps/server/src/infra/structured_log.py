from __future__ import annotations

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


LOGGER_NAME = "mrn.server"
_CONFIGURED = False


def _logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        configure_structured_logging()
    return logger


def build_log_payload(event: str, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "ts_ms": int(time.time() * 1000),
    }
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    return payload


def configure_structured_logging(
    *,
    level: str = "INFO",
    file_path: str = "",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    logger.handlers.clear()
    formatter = logging.Formatter("%(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    if file_path:
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(target),
            maxBytes=max(1024, int(max_bytes)),
            backupCount=max(1, int(backup_count)),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    _CONFIGURED = True


def log_event(event: str, **fields: Any) -> None:
    payload = build_log_payload(event, **fields)
    _logger().info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
