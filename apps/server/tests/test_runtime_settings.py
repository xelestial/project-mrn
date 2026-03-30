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
