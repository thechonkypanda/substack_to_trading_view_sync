"""Unit tests for reconciliation logic conforming to Spec 02 and acceptance criteria."""

import unittest
from datetime import datetime, timedelta

from src.models import (
    FormResponse,
    Subscriber,
    SyncActionType,
    TradingViewUser,
)
from src.reconciliation import ReconciliationEngine


class TestReconciliation(unittest.TestCase):
    def setUp(self):
        self.engine = ReconciliationEngine()

    def test_form_deduplication_first_submission_locks_handle(self):
        """Verifies that the earliest submission locks the handle and subsequent submissions are ignored."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 11, 0, 0)
        t3 = datetime(2026, 8, 1, 12, 0, 0)

        responses = [
            FormResponse.create_normalized(t2, "alice@example.com", "alice_second"),
            FormResponse.create_normalized(t1, "alice@example.com", "alice_first"),
            FormResponse.create_normalized(t3, "alice@example.com", "alice_third"),
        ]

        deduped = self.engine.deduplicate_form_responses(responses)
        self.assertEqual(len(deduped), 1)
        self.assertIn("alice@example.com", deduped)
        self.assertEqual(deduped["alice@example.com"].tradingview_username, "alice_first")

    def test_reconciliation_new_paid_subscriber_grant(self):
        """Active paid subscriber who submitted form and is not on TV gets GRANT action."""
        subscribers = [
            Subscriber(email="alice@example.com", subscription_type="paid", status="active")
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "alice@example.com", "alice_tv")
        ]
        tv_users = []

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.grants), 1)
        self.assertEqual(diff.grants[0].action_type, SyncActionType.GRANT)
        self.assertEqual(diff.grants[0].tradingview_username, "alice_tv")
        self.assertEqual(diff.grants[0].email, "alice@example.com")
        self.assertEqual(len(diff.revokes), 0)
        self.assertEqual(len(diff.unmatched_form_submissions), 0)

    def test_reconciliation_already_authorized_no_op(self):
        """Active paid subscriber already on TradingView results in NO_OP."""
        subscribers = [
            Subscriber(email="alice@example.com", subscription_type="paid", status="active")
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "alice@example.com", "alice_tv")
        ]
        tv_users = [
            TradingViewUser(username="alice_tv", has_access=True)
        ]

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.grants), 0)
        self.assertEqual(len(diff.revokes), 0)
        self.assertEqual(len(diff.no_ops), 1)
        self.assertEqual(diff.no_ops[0].action_type, SyncActionType.NO_OP)

    def test_reconciliation_canceled_subscriber_revoke(self):
        """A user currently on TradingView who canceled their Substack subscription is REVOKED."""
        subscribers = [
            Subscriber(email="bob@example.com", subscription_type="paid", status="canceled")
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "bob@example.com", "bob_tv")
        ]
        tv_users = [
            TradingViewUser(username="bob_tv", has_access=True)
        ]

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.grants), 0)
        self.assertEqual(len(diff.revokes), 1)
        self.assertEqual(diff.revokes[0].action_type, SyncActionType.REVOKE)
        self.assertEqual(diff.revokes[0].tradingview_username, "bob_tv")

    def test_reconciliation_canceled_subscriber_no_tv_access_is_no_op(self):
        """A user who canceled and NEVER had TV access produces no spurious revoke."""
        subscribers = [
            Subscriber(email="canceler@example.com", subscription_type="paid", status="canceled")
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "canceler@example.com", "canceler_tv")
        ]
        tv_users = []

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)
        self.assertEqual(len(diff.grants), 0)
        self.assertEqual(len(diff.revokes), 0)

    def test_reconciliation_unmatched_form_submission_rejected(self):
        """Free user or non-subscriber filling out form is classified as unmatched and gets no access."""
        subscribers = [
            Subscriber(email="free_user@example.com", subscription_type="free", status="active")
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "free_user@example.com", "free_tv"),
            FormResponse.create_normalized(datetime.now(), "stranger@example.com", "stranger_tv"),
        ]
        tv_users = []

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.grants), 0)
        self.assertEqual(len(diff.revokes), 0)
        self.assertEqual(len(diff.unmatched_form_submissions), 2)

    def test_reconciliation_unregistered_paid_subscribers(self):
        """Paid subscribers who haven't submitted the form are flagged under unregistered."""
        subscribers = [
            Subscriber(email="paid1@example.com", subscription_type="paid", status="active"),
            Subscriber(email="paid2@example.com", subscription_type="paid", status="active"),
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "paid1@example.com", "paid1_tv")
        ]
        tv_users = []

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.unregistered_paid_subscribers), 1)
        self.assertEqual(diff.unregistered_paid_subscribers[0], "paid2@example.com")

    def test_comp_and_gift_subscribers_are_active(self):
        """Complimentary and gift subscriptions are recognized as active paid."""
        subscribers = [
            Subscriber(email="vip@example.com", subscription_type="comp", status="active"),
            Subscriber(email="gifted@example.com", subscription_type="gift", status="active"),
        ]
        form_responses = [
            FormResponse.create_normalized(datetime.now(), "vip@example.com", "vip_tv"),
            FormResponse.create_normalized(datetime.now(), "gifted@example.com", "gifted_tv"),
        ]
        tv_users = []

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        self.assertEqual(len(diff.grants), 2)
        granted_handles = {g.tradingview_username for g in diff.grants}
        self.assertIn("vip_tv", granted_handles)
        self.assertIn("gifted_tv", granted_handles)

    def test_complex_multi_user_batch_reconciliation(self):
        """Tests a realistic batch containing active new members, active existing, canceled, and spam submissions."""
        now = datetime.now()
        subscribers = [
            Subscriber(email="new_paid@domain.com", subscription_type="paid", status="active"),
            Subscriber(email="existing_paid@domain.com", subscription_type="paid", status="active"),
            Subscriber(email="canceled_user@domain.com", subscription_type="paid", status="canceled"),
            Subscriber(email="unreg_paid@domain.com", subscription_type="founding", status="active"),
            Subscriber(email="free_reader@domain.com", subscription_type="free", status="active"),
        ]

        form_responses = [
            FormResponse.create_normalized(now - timedelta(hours=2), "new_paid@domain.com", "@NewTrader1"),
            FormResponse.create_normalized(now - timedelta(hours=5), "existing_paid@domain.com", "ExistingTrader"),
            FormResponse.create_normalized(now - timedelta(hours=1), "canceled_user@domain.com", "OldTrader"),
            FormResponse.create_normalized(now - timedelta(minutes=10), "free_reader@domain.com", "FreebieGuy"),
            FormResponse.create_normalized(now - timedelta(minutes=5), "spammer@random.com", "TrollAccount"),
            # Duplicate submission attempt for new_paid@domain.com (should be ignored)
            FormResponse.create_normalized(now, "new_paid@domain.com", "HijackerHandle"),
        ]

        tv_users = [
            TradingViewUser(username="existingtrader", has_access=True),
            TradingViewUser(username="oldtrader", has_access=True),
        ]

        diff = self.engine.calculate_diff(subscribers, form_responses, tv_users)

        # 1. New paid should be granted access to NewTrader1 (not HijackerHandle)
        self.assertEqual(len(diff.grants), 1)
        self.assertEqual(diff.grants[0].tradingview_username, "NewTrader1")
        self.assertEqual(diff.grants[0].email, "new_paid@domain.com")

        # 2. Old trader should be revoked
        self.assertEqual(len(diff.revokes), 1)
        self.assertEqual(diff.revokes[0].tradingview_username, "oldtrader")

        # 3. Existing trader should be a no-op
        self.assertEqual(len(diff.no_ops), 1)
        self.assertEqual(diff.no_ops[0].tradingview_username, "ExistingTrader")

        # 4. Freebie, Canceled, and Spammer should be unmatched (not currently active paid)
        self.assertEqual(len(diff.unmatched_form_submissions), 3)
        unmatched_emails = {u.email for u in diff.unmatched_form_submissions}
        self.assertIn("canceled_user@domain.com", unmatched_emails)
        self.assertIn("free_reader@domain.com", unmatched_emails)
        self.assertIn("spammer@random.com", unmatched_emails)

        # 5. Unregistered paid subscriber should be tracked
        self.assertEqual(len(diff.unregistered_paid_subscribers), 1)
        self.assertEqual(diff.unregistered_paid_subscribers[0], "unreg_paid@domain.com")


if __name__ == "__main__":
    unittest.main()
