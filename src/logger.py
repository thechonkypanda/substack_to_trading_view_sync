"""Logging and observability system conforming to Spec 05."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


def mask_sensitive_data(text: str) -> str:
    """Masks session tokens and secret cookies in logs."""
    # Mask substack.sid (e.g. s%3Aabcdef123 -> s%3A***)
    text = re.sub(r"(substack\.sid=s%3A)[a-zA-Z0-9_\-]+", r"\1***", text)
    text = re.sub(r"(s%3A)[a-zA-Z0-9_\-]{8,}", r"\1***", text)
    # Mask sessionid (e.g. sessionid=abc123xyz -> sessionid=abc***)
    text = re.sub(r"(sessionid=)[a-zA-Z0-9_\-]+", r"\1***", text)
    return text


class MaskingFormatter(logging.Formatter):
    """Custom log formatter that redacts credentials."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return mask_sensitive_data(original)


def setup_logger(log_dir: str = "logs") -> logging.Logger:
    """Sets up file and console loggers for the sync engine."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("substack_tv_sync")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    formatter = MaskingFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # General runtime file handler (INFO and higher)
    sync_file_handler = logging.FileHandler(os.path.join(log_dir, "sync.log"), encoding="utf-8")
    sync_file_handler.setLevel(logging.INFO)
    sync_file_handler.setFormatter(formatter)
    logger.addHandler(sync_file_handler)

    # Error file handler (WARNING and higher)
    error_file_handler = logging.FileHandler(os.path.join(log_dir, "sync_errors.log"), encoding="utf-8")
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(formatter)
    logger.addHandler(error_file_handler)

    return logger


def log_schema_drift(
    logger: logging.Logger,
    endpoint: str,
    error_details: str,
    raw_payload: Optional[Dict[str, Any]] = None
) -> None:
    """Logs API schema drift with raw payload dump for script maintenance."""
    payload_str = json.dumps(raw_payload, indent=2, default=str) if raw_payload else "None"
    masked_payload = mask_sensitive_data(payload_str)
    
    logger.warning(
        f"SCHEMA_DRIFT_DETECTED | Endpoint: {endpoint} | Error: {error_details}\n"
        f"Raw Payload Dump:\n{masked_payload}"
    )
