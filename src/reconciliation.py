"""Reconciliation and Diff Engine conforming to Spec 02."""

import logging
from typing import Dict, List, Optional, Set
from src.models import (
    DiffPlan,
    FormResponse,
    Subscriber,
    SyncAction,
    SyncActionType,
    TradingViewUser,
)


class ReconciliationEngine:
    """Calculates diff actions between Substack subscribers, Google Sheet responses, and TradingView permissions."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("substack_tv_sync")

    def deduplicate_form_responses(
        self, form_responses: List[FormResponse]
    ) -> Dict[str, FormResponse]:
        """
        Deduplicates form responses using 'First Valid Submission Locks Handle'.
        Sorts by submitted_at ascending; the first row encountered for each email is locked.
        Subsequent submissions for that email are silently dropped to eliminate spam/hijacking.
        """
        sorted_responses = sorted(form_responses, key=lambda r: r.submitted_at)
        unique_responses: Dict[str, FormResponse] = {}

        for resp in sorted_responses:
            email = resp.email.strip().lower()
            if not email:
                continue

            if email not in unique_responses:
                unique_responses[email] = resp
            else:
                self.logger.debug(
                    f"Silently ignored duplicate form submission for email '{email}': "
                    f"locked to '{unique_responses[email].tradingview_username}', ignored '{resp.tradingview_username}'."
                )

        return unique_responses

    def calculate_diff(
        self,
        subscribers: List[Subscriber],
        form_responses: List[FormResponse],
        authorized_tv_users: List[TradingViewUser],
    ) -> DiffPlan:
        """
        Calculates the execution plan (Grants, Revokes, No-ops, Unregistered, Unmatched).
        """
        diff = DiffPlan()

        # Index active paid Substack subscribers by normalized email
        active_paid_map: Dict[str, Subscriber] = {}
        for sub in subscribers:
            if sub.is_paid_active:
                active_paid_map[sub.email.strip().lower()] = sub

        # Index currently authorized TradingView users by normalized handle
        tv_access_map: Dict[str, TradingViewUser] = {
            u.username.strip().lower(): u for u in authorized_tv_users if u.has_access
        }

        # Deduplicate form responses (First submission locks handle)
        unique_form_map = self.deduplicate_form_responses(form_responses)

        # Track which TradingView handles should have access based on verified paid submissions
        should_have_access_handles: Set[str] = set()
        claimed_emails: Set[str] = set()

        # 1. Process Form Submissions
        for email, form_resp in unique_form_map.items():
            tv_handle = form_resp.tradingview_username.strip().lower()

            if email not in active_paid_map:
                # Submitted email does not match any active paid subscriber
                diff.unmatched_form_submissions.append(form_resp)
                self.logger.info(
                    f"Unmatched form submission: '{email}' with handle '{tv_handle}' is not an active paid subscriber."
                )
                continue

            # Verified paid subscriber
            claimed_emails.add(email)
            should_have_access_handles.add(tv_handle)

            if tv_handle in tv_access_map:
                # Already authorized on TradingView -> No action needed
                diff.no_ops.append(
                    SyncAction(
                        action_type=SyncActionType.NO_OP,
                        tradingview_username=form_resp.tradingview_username,
                        email=email,
                        reason="Already authorized on TradingView",
                    )
                )
            else:
                # Paid subscriber needs access granted
                diff.grants.append(
                    SyncAction(
                        action_type=SyncActionType.GRANT,
                        tradingview_username=form_resp.tradingview_username,
                        email=email,
                        reason="Active paid subscriber requested access",
                    )
                )

        # 2. Check for Unregistered Paid Subscribers
        for email, sub in active_paid_map.items():
            if email not in claimed_emails:
                diff.unregistered_paid_subscribers.append(email)

        # 3. Check for Revocations (Users currently on TradingView who should no longer have access)
        for tv_handle, tv_user in tv_access_map.items():
            if tv_handle not in should_have_access_handles:
                diff.revokes.append(
                    SyncAction(
                        action_type=SyncActionType.REVOKE,
                        tradingview_username=tv_user.username,
                        email=None,
                        reason="No active paid Substack subscription associated with this handle",
                    )
                )

        return diff
