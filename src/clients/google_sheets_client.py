"""Google Sheets Ingestion Client for fetching form response rows securely."""

import csv
import io
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, List, Optional, Union

from src.models import FormResponse
from src.logger import log_schema_drift


class GoogleSheetsClientError(Exception):
    """Raised when fetching or parsing Google Sheets responses fails."""
    pass


class GoogleSheetsClient:
    """Client for querying Google Sheets containing form responses via secure Apps Script Web App or CSV endpoint."""

    def __init__(
        self,
        webapp_url: Optional[str] = None,
        sheet_id: Optional[str] = None,
        sheet_name: str = "Form Responses 1",
        logger: Optional[logging.Logger] = None
    ) -> None:
        self.webapp_url = (webapp_url or "").strip()
        self.sheet_id = (sheet_id or "").strip()
        self.sheet_name = sheet_name.strip()
        self.logger = logger or logging.getLogger("substack_tv_sync")

    def _get_target_url(self) -> str:
        """Returns the configured Web App URL or direct export URL."""
        if self.webapp_url:
            return self.webapp_url
        if self.sheet_id:
            return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/gviz/tq?tqx=out:csv&sheet={self.sheet_name}"
        raise GoogleSheetsClientError("Neither GOOGLE_SHEET_WEBAPP_URL nor GOOGLE_SHEET_ID is configured in .env.")

    def verify_connection(self) -> bool:
        """Verifies that the Google Sheets endpoint is reachable and authorized."""
        url = self._get_target_url()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise GoogleSheetsClientError(
                    f"Google Sheets access denied (HTTP {e.code}). Check your Apps Script key or permissions."
                )
            if e.code == 404:
                raise GoogleSheetsClientError(f"Google Sheet endpoint not found (HTTP 404).")
            raise GoogleSheetsClientError(f"Google Sheet HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            raise GoogleSheetsClientError(f"Failed to connect to Google Sheet endpoint: {e}")

        return True

    def fetch_form_responses(self) -> List[FormResponse]:
        """Fetches and parses form responses from the configured Google Sheet endpoint."""
        url = self._get_target_url()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            self.logger.error(f"Google Sheets fetch failed with HTTP {e.code}: {e.reason}")
            raise GoogleSheetsClientError(f"Google Sheet download failed (HTTP {e.code}): {e.reason}")
        except Exception as e:
            self.logger.error(f"Google Sheets fetch failed: {e}")
            raise GoogleSheetsClientError(f"Failed to download Google Sheet data: {e}")

        # Determine if response is JSON (from Apps Script) or CSV
        raw_text_stripped = raw_text.strip()
        if raw_text_stripped.startswith("[") or raw_text_stripped.startswith("{"):
            try:
                data = json.loads(raw_text_stripped)
                return self.parse_json_rows(data)
            except json.JSONDecodeError:
                pass

        return self.parse_csv_content(raw_text)

    def parse_json_rows(self, data: Union[List[Any], dict]) -> List[FormResponse]:
        """Parses a 2D array or list of objects returned by Google Apps Script."""
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                rows = data["data"]
            elif "rows" in data and isinstance(data["rows"], list):
                rows = data["rows"]
            else:
                rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            raise GoogleSheetsClientError("Unrecognized JSON format from Google Apps Script.")

        if not rows:
            return []

        # If it's a 2D array where row 0 is header
        if isinstance(rows[0], list):
            header = [str(col).strip().lower() for col in rows[0]]
            time_idx = self._find_column_index(header, ["timestamp", "submitted at", "date"])
            email_idx = self._find_column_index(header, ["substack email address", "email address", "email", "substack email"])
            tv_idx = self._find_column_index(header, ["tradingview username", "tradingview handle", "tv username", "username"])

            if time_idx is None or email_idx is None or tv_idx is None:
                missing = []
                if time_idx is None: missing.append("Timestamp")
                if email_idx is None: missing.append("Email")
                if tv_idx is None: missing.append("TradingView Username")
                raise GoogleSheetsClientError(f"Missing columns in Apps Script response: {missing}")

            responses: List[FormResponse] = []
            for row in rows[1:]:
                if not row or len(row) <= max(time_idx, email_idx, tv_idx):
                    continue
                raw_time = str(row[time_idx]).strip()
                raw_email = str(row[email_idx]).strip()
                raw_tv = str(row[tv_idx]).strip()
                if raw_email and raw_tv:
                    responses.append(FormResponse.create_normalized(
                        submitted_at=self._parse_datetime(raw_time),
                        email=raw_email,
                        username=raw_tv
                    ))
            return responses

        # If it's a list of dict objects
        responses = []
        for obj in rows:
            if not isinstance(obj, dict):
                continue
            email = obj.get("email") or obj.get("substack_email") or obj.get("Substack Email Address")
            username = obj.get("tradingview_username") or obj.get("username") or obj.get("TradingView Username")
            raw_time = str(obj.get("timestamp") or obj.get("Timestamp") or "")
            if email and username:
                responses.append(FormResponse.create_normalized(
                    submitted_at=self._parse_datetime(raw_time),
                    email=str(email),
                    username=str(username)
                ))
        return responses

    def parse_csv_content(self, csv_text: str) -> List[FormResponse]:
        """Parses CSV text into a list of normalized FormResponse objects."""
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        if not rows:
            return []

        header = [col.strip().lower() for col in rows[0]]
        time_idx = self._find_column_index(header, ["timestamp", "timestamp (utc)", "submitted at", "date"])
        email_idx = self._find_column_index(header, ["substack email address", "email address", "email", "substack email"])
        tv_idx = self._find_column_index(header, ["tradingview username", "tradingview handle", "tv username", "username"])

        if time_idx is None or email_idx is None or tv_idx is None:
            missing = []
            if time_idx is None: missing.append("Timestamp")
            if email_idx is None: missing.append("Email")
            if tv_idx is None: missing.append("TradingView Username")
            log_schema_drift(
                self.logger,
                endpoint="GoogleSheet/CSV",
                error_details=f"Missing expected columns in Google Sheet header: {missing}",
                raw_payload={"header_columns": header}
            )
            raise GoogleSheetsClientError(f"Google Sheet is missing required columns: {missing}")

        responses: List[FormResponse] = []
        for row in rows[1:]:
            if not row or len(row) <= max(time_idx, email_idx, tv_idx):
                continue

            raw_time = row[time_idx].strip()
            raw_email = row[email_idx].strip()
            raw_tv = row[tv_idx].strip()

            if not raw_email or not raw_tv:
                continue

            responses.append(FormResponse.create_normalized(
                submitted_at=self._parse_datetime(raw_time),
                email=raw_email,
                username=raw_tv
            ))

        self.logger.info(f"Parsed {len(responses)} form submissions from Google Sheet.")
        return responses

    def _find_column_index(self, headers: List[str], candidate_aliases: List[str]) -> Optional[int]:
        """Finds column index matching any candidate alias."""
        for alias in candidate_aliases:
            for idx, h in enumerate(headers):
                if alias == h or alias in h:
                    return idx
        return None

    def _parse_datetime(self, time_str: str) -> datetime:
        """Parses various datetime formats from Google Forms."""
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%m/%d/%Y %I:%M:%S %p",
            "%Y/%m/%d %I:%M:%S %p",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return datetime.utcnow()
