from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

from autobench.logging_utils import ProgressLogger


class ProgressLoggerTest(unittest.TestCase):
    def test_quiet_logger_suppresses_output(self) -> None:
        stream = io.StringIO()
        logger = ProgressLogger(enabled=False)
        with redirect_stderr(stream):
            logger.info("hidden")
        self.assertEqual(stream.getvalue(), "")

    def test_enabled_logger_writes_message_to_stderr(self) -> None:
        stream = io.StringIO()
        logger = ProgressLogger(enabled=True)
        with redirect_stderr(stream):
            logger.info("visible")
        self.assertIn("visible", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
