"""Configuration loader and validator for Substack to TradingView Sync."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def load_env_file(dotenv_path: Optional[str] = None) -> None:
    """Lightweight built-in .env parser (avoids mandatory third-party dependency)."""
    target = Path(dotenv_path) if dotenv_path else Path(".env")
    if not target.exists() or not target.is_file():
        return

    with open(target, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val


@dataclass(frozen=True)
class Settings:
    """Application configuration settings loaded from environment."""
    # Substack
    substack_subdomain: str
    substack_session_cookie: str

    # Google Sheets (Apps Script Web App or Sheet ID)
    google_sheet_webapp_url: str
    google_sheet_id: str
    google_sheet_name: str

    # TradingView
    tradingview_sessionid: str
    tradingview_sessionid_sign: Optional[str]
    tradingview_script_id: str

    @classmethod
    def load_from_env(cls, env_path: Optional[str] = None) -> "Settings":
        """Loads settings from .env file or environment variables."""
        load_env_file(env_path)

        return cls(
            substack_subdomain=os.getenv("SUBSTACK_SUBDOMAIN", "").strip(),
            substack_session_cookie=os.getenv("SUBSTACK_SESSION_COOKIE", "").strip(),
            google_sheet_webapp_url=os.getenv("GOOGLE_SHEET_WEBAPP_URL", "").strip(),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
            google_sheet_name=os.getenv("GOOGLE_SHEET_NAME", "Form Responses 1").strip(),
            tradingview_sessionid=os.getenv("TRADINGVIEW_SESSIONID", "").strip(),
            tradingview_sessionid_sign=os.getenv("TRADINGVIEW_SESSIONID_SIGN", "").strip() or None,
            tradingview_script_id=os.getenv("TRADINGVIEW_SCRIPT_ID", "").strip(),
        )

    def validate_for_sync(self) -> None:
        """Validates that all required credentials are present."""
        missing = []
        if not self.substack_subdomain:
            missing.append("SUBSTACK_SUBDOMAIN")
        if not self.substack_session_cookie:
            missing.append("SUBSTACK_SESSION_COOKIE")
        if not self.google_sheet_webapp_url and not self.google_sheet_id:
            missing.append("GOOGLE_SHEET_WEBAPP_URL (or GOOGLE_SHEET_ID)")
        if not self.tradingview_sessionid:
            missing.append("TRADINGVIEW_SESSIONID")
        if not self.tradingview_script_id:
            missing.append("TRADINGVIEW_SCRIPT_ID")

        if missing:
            raise ValueError(
                f"Missing required configuration in .env: {', '.join(missing)}.\n"
                f"Please see .env.example for guidance."
            )
