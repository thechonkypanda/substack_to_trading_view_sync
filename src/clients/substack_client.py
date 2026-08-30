"""Substack Creator API Client for fetching subscriber records."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.models import Subscriber
from src.logger import log_schema_drift


class SubstackAuthError(Exception):
    """Raised when Substack authentication session cookie is invalid or expired."""
    pass


class SubstackAPIError(Exception):
    """Raised when Substack API returns an unexpected error."""
    pass


class SubstackClient:
    """Client for querying Substack's creator API."""

    def __init__(
        self,
        subdomain: str,
        session_cookie: str,
        logger: Optional[logging.Logger] = None
    ) -> None:
        self.subdomain = subdomain.strip().lower()
        self.session_cookie = session_cookie.strip()
        self.logger = logger or logging.getLogger("substack_tv_sync")
        self.base_url = f"https://{self.subdomain}.substack.com/api/v1"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Cookie": f"substack.sid={self.session_cookie}",
        }

    def verify_connection(self) -> bool:
        """Pings Substack API to verify authentication status."""
        url = f"{self.base_url}/subscribers?limit=1"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SubstackAuthError(
                    "Substack session cookie expired or invalid (HTTP 401/403).\n"
                    "👉 Remediation: Log into your Substack dashboard in your browser, "
                    "copy a fresh 'substack.sid' cookie, and update SUBSTACK_SESSION_COOKIE in .env."
                )
            raise SubstackAPIError(f"Substack HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise SubstackAPIError(f"Failed to connect to Substack API: {e.reason}")

        return True

    def fetch_all_subscribers(self, filter_type: str = "paid") -> List[Subscriber]:
        """Fetches all subscribers from Substack handling pagination."""
        subscribers: List[Subscriber] = []
        limit = 100
        offset = 0

        while True:
            query = urllib.parse.urlencode({
                "filter": filter_type,
                "limit": limit,
                "offset": offset,
                "order_by": "created_at",
                "sort_direction": "desc",
            })
            url = f"{self.base_url}/subscribers?{query}"
            req = urllib.request.Request(url, headers=self.headers, method="GET")

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw_body = resp.read().decode("utf-8")
                    data = json.loads(raw_body)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise SubstackAuthError(
                        "Substack session cookie expired during sync (HTTP 401/403).\n"
                        "👉 Remediation: Refresh your 'substack.sid' in .env."
                    )
                self.logger.error(f"Substack request failed at offset {offset}: HTTP {e.code}")
                raise SubstackAPIError(f"Substack HTTP Error {e.code}: {e.reason}")
            except Exception as e:
                self.logger.error(f"Substack request failed at offset {offset}: {e}")
                raise SubstackAPIError(f"Substack fetch error: {e}")

            # Substack can return a list or an object with {subscribers: [...]}
            items: List[Dict[str, Any]] = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and "subscribers" in data:
                items = data["subscribers"]
            elif isinstance(data, dict) and "items" in data:
                items = data["items"]
            else:
                log_schema_drift(
                    self.logger,
                    endpoint="/api/v1/subscribers",
                    error_details="Unrecognized subscribers response format",
                    raw_payload=data if isinstance(data, dict) else {"raw": str(data)}
                )
                break

            if not items:
                break

            for item in items:
                subscriber = self._parse_subscriber_item(item)
                if subscriber:
                    subscribers.append(subscriber)

            if len(items) < limit:
                break

            offset += len(items)

        self.logger.info(f"Fetched {len(subscribers)} total subscribers from Substack.")
        return subscribers

    def _parse_subscriber_item(self, item: Dict[str, Any]) -> Optional[Subscriber]:
        """Parses a single subscriber item dictionary into a Subscriber model."""
        email = item.get("email") or item.get("user_email")
        if not email or not isinstance(email, str):
            log_schema_drift(
                self.logger,
                endpoint="/api/v1/subscribers",
                error_details="Subscriber item missing 'email' field",
                raw_payload=item
            )
            return None

        sub_type = (
            item.get("subscription_type")
            or item.get("type")
            or item.get("membership_type")
            or "paid"
        )
        status = (
            item.get("membership_state")
            or item.get("status")
            or item.get("subscription_status")
            or "active"
        )

        expiry_dt: Optional[datetime] = None
        expiry_raw = item.get("expiry") or item.get("current_period_end")
        if expiry_raw:
            try:
                if isinstance(expiry_raw, (int, float)):
                    expiry_dt = datetime.fromtimestamp(expiry_raw)
                elif isinstance(expiry_raw, str):
                    expiry_dt = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
            except Exception:
                expiry_dt = None

        return Subscriber(
            email=email.strip().lower(),
            subscription_type=str(sub_type).strip().lower(),
            status=str(status).strip().lower(),
            expiry=expiry_dt
        )
