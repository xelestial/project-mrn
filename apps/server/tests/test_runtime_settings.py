from __future__ import annotations

import os
import unittest

from apps.server.src.config.runtime_settings import load_runtime_settings


class RuntimeSettingsTests(unittest.TestCase):
    def test_defaults_when_env_missing(self) -> None:
        with _temporary_env({}):
            settings = load_runtime_settings()
        self.assertEqual(settings.stream_heartbeat_interval_ms, 5000)
        self.assertEqual(settings.stream_sender_poll_timeout_ms, 1000)
        self.assertEqual(settings.runtime_watchdog_timeout_ms, 45000)
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.log_file_path, "")
        self.assertEqual(settings.log_file_max_bytes, 5 * 1024 * 1024)
        self.assertEqual(settings.log_file_backup_count, 5)
        self.assertEqual(settings.session_store_path, "")
        self.assertEqual(settings.stream_store_path, "")
        self.assertEqual(settings.session_store_max_sessions, 200)
        self.assertEqual(settings.stream_store_max_sessions, 200)
        self.assertEqual(settings.restart_recovery_policy, "abort_in_progress")
        self.assertEqual(settings.redis_url, "")
        self.assertEqual(settings.redis_key_prefix, "mrn")
        self.assertEqual(settings.redis_socket_timeout_ms, 1000)
        self.assertEqual(settings.game_log_archive_path, "data/game_logs")
        self.assertEqual(settings.archive_hot_retention_seconds, 300)
        self.assertEqual(settings.prompt_timeout_worker_poll_interval_ms, 250)
        self.assertEqual(settings.command_wakeup_worker_poll_interval_ms, 250)

    def test_env_overrides_with_minimum_clamp(self) -> None:
        with _temporary_env(
            {
                "MRN_STREAM_HEARTBEAT_INTERVAL_MS": "7000",
                "MRN_STREAM_SENDER_POLL_TIMEOUT_MS": "500",
                "MRN_RUNTIME_WATCHDOG_TIMEOUT_MS": "60000",
                "MRN_LOG_LEVEL": "debug",
                "MRN_LOG_FILE_PATH": "result/server/server.log",
                "MRN_LOG_FILE_MAX_BYTES": "1048576",
                "MRN_LOG_FILE_BACKUP_COUNT": "8",
                "MRN_SESSION_STORE_PATH": "result/server/session-store.json",
                "MRN_STREAM_STORE_PATH": "result/server/stream-store.json",
                "MRN_SESSION_STORE_MAX_SESSIONS": "321",
                "MRN_STREAM_STORE_MAX_SESSIONS": "654",
                "MRN_RESTART_RECOVERY_POLICY": "keep",
                "MRN_REDIS_URL": "redis://127.0.0.1:6379/4",
                "MRN_REDIS_KEY_PREFIX": "mrn-test",
                "MRN_REDIS_SOCKET_TIMEOUT_MS": "1500",
                "MRN_GAME_LOG_ARCHIVE_PATH": "data/test_logs",
                "MRN_ARCHIVE_HOT_RETENTION_SECONDS": "45",
                "MRN_PROMPT_TIMEOUT_WORKER_POLL_INTERVAL_MS": "750",
                "MRN_COMMAND_WAKEUP_WORKER_POLL_INTERVAL_MS": "900",
            }
        ):
            settings = load_runtime_settings()
        self.assertEqual(settings.stream_heartbeat_interval_ms, 7000)
        self.assertEqual(settings.stream_sender_poll_timeout_ms, 500)
        self.assertEqual(settings.runtime_watchdog_timeout_ms, 60000)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.log_file_path, "result/server/server.log")
        self.assertEqual(settings.log_file_max_bytes, 1048576)
        self.assertEqual(settings.log_file_backup_count, 8)
        self.assertEqual(settings.session_store_path, "result/server/session-store.json")
        self.assertEqual(settings.stream_store_path, "result/server/stream-store.json")
        self.assertEqual(settings.session_store_max_sessions, 321)
        self.assertEqual(settings.stream_store_max_sessions, 654)
        self.assertEqual(settings.restart_recovery_policy, "keep")
        self.assertEqual(settings.redis_url, "redis://127.0.0.1:6379/4")
        self.assertEqual(settings.redis_key_prefix, "mrn-test")
        self.assertEqual(settings.redis_socket_timeout_ms, 1500)
        self.assertEqual(settings.game_log_archive_path, "data/test_logs")
        self.assertEqual(settings.archive_hot_retention_seconds, 45)
        self.assertEqual(settings.prompt_timeout_worker_poll_interval_ms, 750)
        self.assertEqual(settings.command_wakeup_worker_poll_interval_ms, 900)

    def test_invalid_env_values_fallback_to_defaults(self) -> None:
        with _temporary_env(
            {
                "MRN_STREAM_HEARTBEAT_INTERVAL_MS": "x",
                "MRN_STREAM_SENDER_POLL_TIMEOUT_MS": "0",
                "MRN_RUNTIME_WATCHDOG_TIMEOUT_MS": "4999",
                "MRN_LOG_LEVEL": "",
                "MRN_LOG_FILE_PATH": "",
                "MRN_LOG_FILE_MAX_BYTES": "1",
                "MRN_LOG_FILE_BACKUP_COUNT": "0",
                "MRN_SESSION_STORE_PATH": "",
                "MRN_STREAM_STORE_PATH": "",
                "MRN_SESSION_STORE_MAX_SESSIONS": "0",
                "MRN_STREAM_STORE_MAX_SESSIONS": "-1",
                "MRN_RESTART_RECOVERY_POLICY": "",
                "MRN_REDIS_URL": "",
                "MRN_REDIS_KEY_PREFIX": "",
                "MRN_REDIS_SOCKET_TIMEOUT_MS": "10",
                "MRN_GAME_LOG_ARCHIVE_PATH": "",
                "MRN_ARCHIVE_HOT_RETENTION_SECONDS": "-1",
                "MRN_PROMPT_TIMEOUT_WORKER_POLL_INTERVAL_MS": "10",
                "MRN_COMMAND_WAKEUP_WORKER_POLL_INTERVAL_MS": "10",
            }
        ):
            settings = load_runtime_settings()
        self.assertEqual(settings.stream_heartbeat_interval_ms, 5000)
        self.assertEqual(settings.stream_sender_poll_timeout_ms, 1000)
        self.assertEqual(settings.runtime_watchdog_timeout_ms, 45000)
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.log_file_path, "")
        self.assertEqual(settings.log_file_max_bytes, 5 * 1024 * 1024)
        self.assertEqual(settings.log_file_backup_count, 5)
        self.assertEqual(settings.session_store_path, "")
        self.assertEqual(settings.stream_store_path, "")
        self.assertEqual(settings.session_store_max_sessions, 200)
        self.assertEqual(settings.stream_store_max_sessions, 200)
        self.assertEqual(settings.restart_recovery_policy, "abort_in_progress")
        self.assertEqual(settings.redis_url, "")
        self.assertEqual(settings.redis_key_prefix, "mrn")
        self.assertEqual(settings.redis_socket_timeout_ms, 1000)
        self.assertEqual(settings.game_log_archive_path, "data/game_logs")
        self.assertEqual(settings.archive_hot_retention_seconds, 300)
        self.assertEqual(settings.prompt_timeout_worker_poll_interval_ms, 250)
        self.assertEqual(settings.command_wakeup_worker_poll_interval_ms, 250)


class _temporary_env:
    def __init__(self, updates: dict[str, str]) -> None:
        self._updates = updates
        self._before: dict[str, str | None] = {}
        self._keys = [
            "MRN_STREAM_HEARTBEAT_INTERVAL_MS",
            "MRN_STREAM_SENDER_POLL_TIMEOUT_MS",
            "MRN_RUNTIME_WATCHDOG_TIMEOUT_MS",
            "MRN_LOG_LEVEL",
            "MRN_LOG_FILE_PATH",
            "MRN_LOG_FILE_MAX_BYTES",
            "MRN_LOG_FILE_BACKUP_COUNT",
            "MRN_SESSION_STORE_PATH",
            "MRN_STREAM_STORE_PATH",
            "MRN_SESSION_STORE_MAX_SESSIONS",
            "MRN_STREAM_STORE_MAX_SESSIONS",
            "MRN_RESTART_RECOVERY_POLICY",
            "MRN_REDIS_URL",
            "MRN_REDIS_KEY_PREFIX",
            "MRN_REDIS_SOCKET_TIMEOUT_MS",
            "MRN_GAME_LOG_ARCHIVE_PATH",
            "MRN_ARCHIVE_HOT_RETENTION_SECONDS",
            "MRN_PROMPT_TIMEOUT_WORKER_POLL_INTERVAL_MS",
            "MRN_COMMAND_WAKEUP_WORKER_POLL_INTERVAL_MS",
        ]

    def __enter__(self) -> None:
        for key in self._keys:
            self._before[key] = os.environ.get(key)
            if key in self._updates:
                os.environ[key] = self._updates[key]
            else:
                os.environ.pop(key, None)

    def __exit__(self, exc_type, exc, tb) -> None:
        for key, value in self._before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
