"""TradingView Bridge Client for managing invite-only indicator permissions."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models import TradingViewUser
from src.logger import log_schema_drift


class TradingViewAuthError(Exception):
    """Raised when TradingView sessionid is invalid or expired."""
    pass


class TradingViewAPIError(Exception):
    """Raised on general TradingView communication errors."""
    pass


class TradingViewBridge(ABC):
    """Abstract interface for TradingView permission interactions."""

    @abstractmethod
    def get_authorized_users(self, script_id: str) -> List[TradingViewUser]:
        """Fetches the list of users currently authorized for the script."""
        pass

    @abstractmethod
    def grant_access(self, script_id: str, username: str, expiration: Optional[str] = None) -> bool:
        """Grants invite-only access to a username."""
        pass

    @abstractmethod
    def revoke_access(self, script_id: str, username: str) -> bool:
        """Revokes invite-only access from a username."""
        pass

    @abstractmethod
    def verify_auth(self) -> bool:
        """Verifies session credentials."""
        pass


class DryRunTradingViewBridge(TradingViewBridge):
    """Simulation bridge that performs no network writes."""

    def __init__(self, initial_users: Optional[List[TradingViewUser]] = None, logger: Optional[logging.Logger] = None) -> None:
        self.users = {u.username.lower(): u for u in (initial_users or [])}
        self.logger = logger or logging.getLogger("substack_tv_sync")

    def get_authorized_users(self, script_id: str) -> List[TradingViewUser]:
        return list(self.users.values())

    def grant_access(self, script_id: str, username: str, expiration: Optional[str] = None) -> bool:
        self.logger.info(f"[DRY-RUN] Simulated GRANT access for '{username}' on {script_id}")
        self.users[username.lower()] = TradingViewUser(username=username, expiration=expiration, has_access=True)
        return True

    def revoke_access(self, script_id: str, username: str) -> bool:
        self.logger.info(f"[DRY-RUN] Simulated REVOKE access for '{username}' on {script_id}")
        self.users.pop(username.lower(), None)
        return True

    def verify_auth(self) -> bool:
        return True


class TradingViewClient(TradingViewBridge):
    """Live HTTP bridge client communicating with TradingView endpoints."""

    def __init__(
        self,
        sessionid: str,
        sessionid_sign: Optional[str] = None,
        request_delay: float = 0.5,
        logger: Optional[logging.Logger] = None
    ) -> None:
        self.sessionid = sessionid.strip()
        self.sessionid_sign = (sessionid_sign or "").strip()
        self.request_delay = request_delay
        self.logger = logger or logging.getLogger("substack_tv_sync")
        self.base_url = "https://www.tradingview.com"
        
        cookie_str = f"sessionid={self.sessionid}"
        if self.sessionid_sign:
            cookie_str += f"; sessionid_sign={self.sessionid_sign}"

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Cookie": cookie_str,
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def verify_auth(self) -> bool:
        """Verifies session credentials against TradingView user profile endpoint."""
        url = f"{self.base_url}/user/"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise TradingViewAuthError(
                    "TradingView sessionid cookie is expired or invalid.\n"
                    "👉 Remediation: Log into TradingView in your browser, copy your 'sessionid' cookie, "
                    "and update TRADINGVIEW_SESSIONID in .env."
                )
            raise TradingViewAPIError(f"TradingView HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            raise TradingViewAPIError(f"TradingView connection error: {e}")

        return True

    def _request_with_retry(self, url: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Performs an HTTP request with exponential backoff for rate limits."""
        max_retries = 3
        backoff = 1.0

        encoded_data = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        method = "POST" if data is not None else "GET"

        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(url, data=encoded_data, headers=self.headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw_body = resp.read().decode("utf-8")
                    return json.loads(raw_body)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self.logger.warning(
                        f"TradingView rate limit (429) hit. Backing off for {backoff:.1f}s (Attempt {attempt}/{max_retries})..."
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                if e.code in (401, 403):
                    raise TradingViewAuthError(
                        "TradingView authentication failed (HTTP 401/403). Session cookie expired."
                    )
                raise TradingViewAPIError(f"TradingView HTTP Error {e.code}: {e.reason}")
            except Exception as e:
                if attempt == max_retries:
                    raise TradingViewAPIError(f"TradingView request failed after {max_retries} attempts: {e}")
                self.logger.warning(f"Network error on attempt {attempt}/{max_retries}: {e}. Retrying...")
                time.sleep(backoff)
                backoff *= 2.0

        raise TradingViewAPIError(f"TradingView request to {url} failed after {max_retries} retries.")

    def get_authorized_users(self, script_id: str) -> List[TradingViewUser]:
        """Fetches the list of authorized users for a specific invite-only indicator."""
        url = f"{self.base_url}/pine_perm/list_users/"
        data = {"pine_id": script_id}

        try:
            payload = self._request_with_retry(url, data=data)
        except Exception as e:
            self.logger.error(f"Failed to fetch authorized users for {script_id}: {e}")
            raise

        users_list: List[TradingViewUser] = []
        raw_users = payload.get("users", [])
        if not isinstance(raw_users, list):
            log_schema_drift(
                self.logger,
                endpoint="/pine_perm/list_users/",
                error_details="Expected 'users' key containing list in response",
                raw_payload=payload
            )
            return users_list

        for u in raw_users:
            if isinstance(u, dict):
                username = u.get("username", "")
                user_id = u.get("user_id")
                expiration = u.get("expiration")
                if username:
                    users_list.append(TradingViewUser(
                        username=username.strip().lower(),
                        user_id=user_id,
                        expiration=expiration,
                        has_access=True
                    ))
            elif isinstance(u, str):
                users_list.append(TradingViewUser(username=u.strip().lower(), has_access=True))

        return users_list

    def grant_access(self, script_id: str, username: str, expiration: Optional[str] = None) -> bool:
        """Grants invite-only access to a username on TradingView with pacing delay."""
        url = f"{self.base_url}/pine_perm/add_user/"
        data = {
            "pine_id": script_id,
            "username": username,
        }
        if expiration:
            data["expiration"] = expiration

        try:
            payload = self._request_with_retry(url, data=data)
            if payload.get("status") == "ok":
                self.logger.info(f"Successfully GRANTED TradingView access to '{username}' for script {script_id}")
                if self.request_delay > 0:
                    time.sleep(self.request_delay)
                return True
            else:
                self.logger.error(f"Failed to grant access to '{username}': {payload}")
                return False
        except Exception as e:
            self.logger.error(f"Error granting access to '{username}': {e}")
            raise

    def revoke_access(self, script_id: str, username: str) -> bool:
        """Revokes invite-only access from a username on TradingView with pacing delay."""
        url = f"{self.base_url}/pine_perm/remove_user/"
        data = {
            "pine_id": script_id,
            "username": username,
        }

        try:
            payload = self._request_with_retry(url, data=data)
            if payload.get("status") == "ok":
                self.logger.info(f"Successfully REVOKED TradingView access from '{username}' for script {script_id}")
                if self.request_delay > 0:
                    time.sleep(self.request_delay)
                return True
            else:
                self.logger.error(f"Failed to revoke access from '{username}': {payload}")
                return False
        except Exception as e:
            self.logger.error(f"Error revoking access from '{username}': {e}")
            raise
