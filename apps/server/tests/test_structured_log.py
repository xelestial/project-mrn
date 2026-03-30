from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from apps.server.src.infra import structured_log


class StructuredLogTests(unittest.TestCase):
    def setUp(self) -> None:
        logger = logging.getLogger(structured_log.LOGGER_NAME)
        for handler in list(logger.handlers):
            handler.close()
        logger.handlers.clear()
        logger.propagate = True
        structured_log._CONFIGURED = False  # noqa: SLF001

    def tearDown(self) -> None:
        logger = logging.getLogger(structured_log.LOGGER_NAME)
        for handler in list(logger.handlers):
            handler.close()
        logger.handlers.clear()
        logger.propagate = True
        structured_log._CONFIGURED = False  # noqa: SLF001

    def test_build_payload_omits_none_fields(self) -> None:
        payload = structured_log.build_log_payload("test_event", session_id="sess_1", empty=None)
        self.assertEqual(payload["event"], "test_event")
        self.assertEqual(payload["session_id"], "sess_1")
        self.assertNotIn("empty", payload)
        self.assertIn("ts_ms", payload)

    def test_configure_logging_with_rotating_file_handler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "server.log"
            structured_log.configure_structured_logging(
                level="INFO",
                file_path=str(target),
                max_bytes=4096,
                backup_count=2,
            )
            structured_log.log_event("runtime_started", session_id="sess_2", seed=42)
            logger = logging.getLogger(structured_log.LOGGER_NAME)
            for handler in logger.handlers:
                handler.flush()
            content = target.read_text(encoding="utf-8").strip()
            self.assertTrue(content)
            parsed = json.loads(content.splitlines()[-1])
            self.assertEqual(parsed["event"], "runtime_started")
            self.assertEqual(parsed["session_id"], "sess_2")
            self.assertEqual(parsed["seed"], 42)
            for handler in list(logger.handlers):
                handler.close()
            logger.handlers.clear()


if __name__ == "__main__":
    unittest.main()
