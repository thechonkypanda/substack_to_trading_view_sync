"""Unit tests for logger and credential redaction conforming to Spec 05."""

import logging
import os
import shutil
import tempfile
import unittest

from src.logger import mask_sensitive_data, setup_logger, log_schema_drift


class TestLogger(unittest.TestCase):

    def test_mask_sensitive_data(self):
        """Verifies that sensitive session cookies and tokens are masked."""
        sample = "Cookie: substack.sid=s%3Aabcdef1234567890; sessionid=xyz9876543210;"
        masked = mask_sensitive_data(sample)

        self.assertNotIn("s%3Aabcdef1234567890", masked)
        self.assertNotIn("xyz9876543210", masked)
        self.assertIn("substack.sid=s%3A***", masked)
        self.assertIn("sessionid=***", masked)

    def test_logger_file_creation(self):
        """Verifies that logger correctly writes masked logs to files."""
        temp_dir = tempfile.mkdtemp()
        try:
            logger = setup_logger(log_dir=temp_dir)
            test_msg = "Attempting auth with substack.sid=s%3Asecrettoken123456789"
            logger.info(test_msg)

            # Flush handlers
            for handler in logger.handlers:
                handler.flush()

            sync_log = os.path.join(temp_dir, "sync.log")
            self.assertTrue(os.path.exists(sync_log))

            with open(sync_log, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("secrettoken123456789", content)
            self.assertIn("substack.sid=s%3A***", content)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
