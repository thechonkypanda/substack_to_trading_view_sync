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
        client = GoogleSheetsClient(sheet_id="dummy")
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

    def test_google_sheets_csv_parser_missing_headers(self):
        """Verifies that missing columns raise a GoogleSheetsClientError."""
        client = GoogleSheetsClient(sheet_id="dummy")
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


if __name__ == "__main__":
    unittest.main()
