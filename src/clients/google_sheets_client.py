"""Google Sheets Ingestion Client for fetching form response rows."""

import csv
import io
import logging
import urllib.error
import urllib.request
from datetime import datetime
from typing import List, Optional

from src.models import FormResponse
from src.logger import log_schema_drift


class GoogleSheetsClientError(Exception):
    """Raised when fetching or parsing Google Sheets responses fails."""
    pass


class GoogleSheetsClient:
    """Client for querying Google Sheets containing form responses."""

    def __init__(
        self,
        sheet_id: str,
        sheet_name: str = "Form Responses 1",
        logger: Optional[logging.Logger] = None
    ) -> None:
        self.sheet_id = sheet_id.strip()
        self.sheet_name = sheet_name.strip()
        self.logger = logger or logging.getLogger("substack_tv_sync")

    def _get_export_url(self) -> str:
        """Constructs the Google Sheets CSV export endpoint."""
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/gviz/tq?tqx=out:csv&sheet={self.sheet_name}"

    def verify_connection(self) -> bool:
        """Verifies that the Google Sheet is reachable and accessible."""
        url = self._get_export_url()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise GoogleSheetsClientError(
                    f"Google Sheet not found (HTTP 404). Check GOOGLE_SHEET_ID in .env."
                )
            if e.code in (401, 403):
                raise GoogleSheetsClientError(
                    f"Google Sheet access denied (HTTP {e.code}). "
                    f"Ensure the sheet permissions allow access or link sharing is set up."
                )
            raise GoogleSheetsClientError(f"Google Sheet HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            raise GoogleSheetsClientError(f"Failed to connect to Google Sheet: {e}")

        return True

    def fetch_form_responses(self) -> List[FormResponse]:
        """Fetches and parses form responses from the Google Sheet."""
        url = self._get_export_url()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                csv_text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            self.logger.error(f"Google Sheets fetch failed with HTTP {e.code}: {e.reason}")
            raise GoogleSheetsClientError(f"Google Sheet download failed (HTTP {e.code}): {e.reason}")
        except Exception as e:
            self.logger.error(f"Google Sheets fetch failed: {e}")
            raise GoogleSheetsClientError(f"Failed to download Google Sheet: {e}")

        return self.parse_csv_content(csv_text)

    def parse_csv_content(self, csv_text: str) -> List[FormResponse]:
        """Parses CSV text into a list of normalized FormResponse objects."""
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        if not rows:
            return []

        header = [col.strip().lower() for col in rows[0]]
        
        # Locate column indexes dynamically based on aliases
        time_idx = self._find_column_index(header, ["timestamp", "timestamp (utc)", "submitted at", "date"])
        email_idx = self._find_column_index(header, ["substack email address", "email address", "email", "substack email"])
        tv_idx = self._find_column_index(header, ["tradingview username", "tradingview handle", "tv username", "username"])

        if time_idx is None or email_idx is None or tv_idx is None:
            missing = []
            if time_idx is None:
                missing.append("Timestamp")
            if email_idx is None:
                missing.append("Email")
            if tv_idx is None:
                missing.append("TradingView Username")
            
            log_schema_drift(
                self.logger,
                endpoint="GoogleSheet/CSV",
                error_details=f"Missing expected columns in Google Sheet header: {missing}",
                raw_payload={"header_columns": header}
            )
            raise GoogleSheetsClientError(f"Google Sheet is missing required columns: {missing}")

        responses: List[FormResponse] = []
        for row_num, row in enumerate(rows[1:], start=2):
            if not row or len(row) <= max(time_idx, email_idx, tv_idx):
                continue

            raw_time = row[time_idx].strip()
            raw_email = row[email_idx].strip()
            raw_tv = row[tv_idx].strip()

            if not raw_email or not raw_tv:
                continue

            # Parse timestamp or fallback to current time
            dt = self._parse_datetime(raw_time)

            resp_obj = FormResponse.create_normalized(
                submitted_at=dt,
                email=raw_email,
                username=raw_tv
            )
            responses.append(resp_obj)

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
            "%m/%d/%Y %I:%M:%S %p",
            "%Y/%m/%d %I:%M:%S %p",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return datetime.utcnow()
