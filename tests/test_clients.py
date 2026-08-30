"""Unit tests for API clients and adapters."""

import unittest
from datetime import datetime

from src.clients.google_sheets_client import GoogleSheetsClient, GoogleSheetsClientError
from src.clients.substack_client import SubstackClient, SubstackAuthError
from src.clients.tradingview_client import DryRunTradingViewBridge, TradingViewUser
from src.models import FormResponse, Subscriber


class TestClients(unittest.TestCase):

    def test_google_sheets_csv_parser_normal(self):
        """Verifies that GoogleSheetsClient correctly parses CSV content."""
        client = GoogleSheetsClient(webapp_url="https://script.google.com/dummy")
        csv_sample = (
            "Timestamp,Substack Email Address,TradingView Username\n"
            "2026-08-01 10:00:00, user1@example.com , @TraderOne \n"
            "2026-08-02 12:30:00,USER2@EXAMPLE.COM,trader_two\n"
        )

        responses = client.parse_csv_content(csv_sample)
        self.assertEqual(len(responses), 2)

        self.assertEqual(responses[0].email, "user1@example.com")
        self.assertEqual(responses[0].tradingview_username, "TraderOne")

        self.assertEqual(responses[1].email, "user2@example.com")
        self.assertEqual(responses[1].tradingview_username, "trader_two")

    def test_google_sheets_apps_script_2d_array_parser(self):
        """Verifies that GoogleSheetsClient parses JSON 2D array from Apps Script."""
        client = GoogleSheetsClient(webapp_url="https://script.google.com/dummy")
        json_payload = [
            ["Timestamp", "Substack Email Address", "TradingView Username"],
            ["2026-08-01 10:00:00", "user1@example.com", "TraderOne"],
            ["2026-08-02 12:30:00", "user2@example.com", "@trader_two"]
        ]

        responses = client.parse_json_rows(json_payload)
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].email, "user1@example.com")
        self.assertEqual(responses[0].tradingview_username, "TraderOne")
        self.assertEqual(responses[1].email, "user2@example.com")
        self.assertEqual(responses[1].tradingview_username, "trader_two")

    def test_google_sheets_apps_script_dict_list_parser(self):
        """Verifies that GoogleSheetsClient parses a list of dictionary objects."""
        client = GoogleSheetsClient(webapp_url="https://script.google.com/dummy")
        json_payload = [
            {
                "Timestamp": "2026-08-01 10:00:00",
                "Substack Email Address": "userA@domain.com",
                "TradingView Username": "TraderA"
            },
            {
                "timestamp": "2026-08-02 11:00:00",
                "email": "userB@domain.com",
                "tradingview_username": "@TraderB"
            }
        ]

        responses = client.parse_json_rows(json_payload)
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].email, "usera@domain.com")
        self.assertEqual(responses[0].tradingview_username, "TraderA")
        self.assertEqual(responses[1].email, "userb@domain.com")
        self.assertEqual(responses[1].tradingview_username, "TraderB")

    def test_google_sheets_csv_parser_missing_headers(self):
        """Verifies that missing columns raise a GoogleSheetsClientError."""
        client = GoogleSheetsClient(webapp_url="https://script.google.com/dummy")
        invalid_csv = "RandomCol1,RandomCol2\nval1,val2\n"

        with self.assertRaises(GoogleSheetsClientError):
            client.parse_csv_content(invalid_csv)

    def test_substack_client_parse_items(self):
        """Verifies parsing Substack raw dictionary records."""
        client = SubstackClient(subdomain="testpub", session_cookie="fake_token")
        raw_item = {
            "email": "SUBSCRIBER@DOMAIN.COM",
            "subscription_type": "paid",
            "membership_state": "active",
            "expiry": None,
        }

        parsed = client._parse_subscriber_item(raw_item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.email, "subscriber@domain.com")
        self.assertTrue(parsed.is_paid_active)

    def test_dry_run_tradingview_bridge(self):
        """Verifies DryRunTradingViewBridge state mutations without network calls."""
        initial = [TradingViewUser(username="existing_user")]
        bridge = DryRunTradingViewBridge(initial_users=initial)

        users = bridge.get_authorized_users("PUB_test")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].username, "existing_user")

        # Grant new user
        bridge.grant_access("PUB_test", "new_user")
        updated = bridge.get_authorized_users("PUB_test")
        self.assertEqual(len(updated), 2)

        # Revoke user
        bridge.revoke_access("PUB_test", "existing_user")
        final_users = bridge.get_authorized_users("PUB_test")
        self.assertEqual(len(final_users), 1)
        self.assertEqual(final_users[0].username, "new_user")

    def test_tradingview_client_pacing_configuration(self):
        """Verifies that TradingViewClient properly configures and executes pacing delay."""
        from unittest.mock import patch, MagicMock
        from src.clients.tradingview_client import TradingViewClient

        client = TradingViewClient(sessionid="test_session", request_delay=0.5)
        self.assertEqual(client.request_delay, 0.5)

        # Mock _request_with_retry to simulate successful grant
        with patch.object(client, "_request_with_retry", return_value={"status": "ok"}):
            with patch("time.sleep") as mock_sleep:
                success = client.grant_access("PUB_123", "testuser")
                self.assertTrue(success)
                mock_sleep.assert_called_once_with(0.5)

        # Mock _request_with_retry to simulate successful revoke
        with patch.object(client, "_request_with_retry", return_value={"status": "ok"}):
            with patch("time.sleep") as mock_sleep:
                success = client.revoke_access("PUB_123", "testuser")
                self.assertTrue(success)
                mock_sleep.assert_called_once_with(0.5)

    def test_tradingview_client_fail_fast_on_401(self):
        """Verifies that TradingViewClient raises TradingViewAuthError immediately without retrying on 401."""
        from unittest.mock import patch
        import urllib.error
        from src.clients.tradingview_client import TradingViewClient, TradingViewAuthError

        client = TradingViewClient(sessionid="expired_session")

        # Simulate 401 HTTP error
        http_401 = urllib.error.HTTPError(
            url="https://www.tradingview.com/pine_perm/add_user/",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )

        with patch("urllib.request.urlopen", side_effect=http_401) as mock_urlopen:
            with self.assertRaises(TradingViewAuthError):
                client.grant_access("PUB_123", "testuser")
            
            # Verify it failed fast on the first call (urlopen called exactly once, 0 retries)
            self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
