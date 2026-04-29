from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed >= minimum else default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    return raw or default


@dataclass(frozen=True)
class RuntimeSettings:
    stream_heartbeat_interval_ms: int = 5000
    stream_sender_poll_timeout_ms: int = 1000
    runtime_watchdog_timeout_ms: int = 45000
    log_level: str = "INFO"
    log_file_path: str = ""
    log_file_max_bytes: int = 5 * 1024 * 1024
    log_file_backup_count: int = 5
    session_store_path: str = ""
    stream_store_path: str = ""
    session_store_max_sessions: int = 200
    stream_store_max_sessions: int = 200
    restart_recovery_policy: str = "abort_in_progress"
    redis_url: str = ""
    redis_key_prefix: str = "mrn"
    redis_socket_timeout_ms: int = 1000
    game_log_archive_path: str = "data/game_logs"
    archive_hot_retention_seconds: int = 300
    prompt_timeout_worker_poll_interval_ms: int = 250


def load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        stream_heartbeat_interval_ms=_env_int("MRN_STREAM_HEARTBEAT_INTERVAL_MS", 5000, 250),
        stream_sender_poll_timeout_ms=_env_int("MRN_STREAM_SENDER_POLL_TIMEOUT_MS", 1000, 50),
        runtime_watchdog_timeout_ms=_env_int("MRN_RUNTIME_WATCHDOG_TIMEOUT_MS", 45000, 5000),
        log_level=_env_str("MRN_LOG_LEVEL", "INFO").upper(),
        log_file_path=_env_str("MRN_LOG_FILE_PATH", ""),
        log_file_max_bytes=_env_int("MRN_LOG_FILE_MAX_BYTES", 5 * 1024 * 1024, 1024),
        log_file_backup_count=_env_int("MRN_LOG_FILE_BACKUP_COUNT", 5, 1),
        session_store_path=_env_str("MRN_SESSION_STORE_PATH", ""),
        stream_store_path=_env_str("MRN_STREAM_STORE_PATH", ""),
        session_store_max_sessions=_env_int("MRN_SESSION_STORE_MAX_SESSIONS", 200, 1),
        stream_store_max_sessions=_env_int("MRN_STREAM_STORE_MAX_SESSIONS", 200, 1),
        restart_recovery_policy=_env_str("MRN_RESTART_RECOVERY_POLICY", "abort_in_progress"),
        redis_url=_env_str("MRN_REDIS_URL", ""),
        redis_key_prefix=_env_str("MRN_REDIS_KEY_PREFIX", "mrn"),
        redis_socket_timeout_ms=_env_int("MRN_REDIS_SOCKET_TIMEOUT_MS", 1000, 50),
        game_log_archive_path=_env_str("MRN_GAME_LOG_ARCHIVE_PATH", "data/game_logs"),
        archive_hot_retention_seconds=_env_int("MRN_ARCHIVE_HOT_RETENTION_SECONDS", 300, 0),
        prompt_timeout_worker_poll_interval_ms=_env_int("MRN_PROMPT_TIMEOUT_WORKER_POLL_INTERVAL_MS", 250, 50),
    )
