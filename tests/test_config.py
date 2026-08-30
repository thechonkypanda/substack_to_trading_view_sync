"""Unit tests for configuration loading and validation."""

import os
import tempfile
import unittest

from src.config import Settings, load_env_file


class TestConfig(unittest.TestCase):

    def test_load_env_file_parsing(self):
        """Verifies custom .env parser handles quotes, comments, whitespace, and values."""
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("# Comment line\n")
            f.write("SUBSTACK_SUBDOMAIN=my_pub\n")
            f.write("SUBSTACK_SESSION_COOKIE=\"s%3Asecrettoken123\"\n")
            f.write("GOOGLE_SHEET_WEBAPP_URL='https://script.google.com/test?key=123'\n")
            f.write("TRADINGVIEW_SESSIONID=tv_session_xyz\n")
            f.write("TRADINGVIEW_SCRIPT_ID=PUB_custom123\n")
            temp_path = f.name

        try:
            # Clear any preexisting env
            for k in ["SUBSTACK_SUBDOMAIN", "SUBSTACK_SESSION_COOKIE", "GOOGLE_SHEET_WEBAPP_URL", "TRADINGVIEW_SESSIONID", "TRADINGVIEW_SCRIPT_ID"]:
                os.environ.pop(k, None)

            settings = Settings.load_from_env(env_path=temp_path)
            self.assertEqual(settings.substack_subdomain, "my_pub")
            self.assertEqual(settings.substack_session_cookie, "s%3Asecrettoken123")
            self.assertEqual(settings.google_sheet_webapp_url, "https://script.google.com/test?key=123")
            self.assertEqual(settings.tradingview_sessionid, "tv_session_xyz")
            self.assertEqual(settings.tradingview_script_id, "PUB_custom123")
            
            # Validation should succeed
            settings.validate_for_sync()
        finally:
            os.remove(temp_path)

    def test_validate_for_sync_missing_variables(self):
        """Verifies that missing configuration raises ValueError with detailed field list."""
        incomplete_settings = Settings(
            substack_subdomain="",
            substack_session_cookie="",
            google_sheet_webapp_url="",
            tradingview_sessionid="",
            tradingview_script_id=""
        )

        with self.assertRaises(ValueError) as ctx:
            incomplete_settings.validate_for_sync()

        err_msg = str(ctx.exception)
        self.assertIn("SUBSTACK_SUBDOMAIN", err_msg)
        self.assertIn("SUBSTACK_SESSION_COOKIE", err_msg)
        self.assertIn("GOOGLE_SHEET_WEBAPP_URL", err_msg)
        self.assertIn("TRADINGVIEW_SESSIONID", err_msg)
        self.assertIn("TRADINGVIEW_SCRIPT_ID", err_msg)


if __name__ == "__main__":
    unittest.main()
