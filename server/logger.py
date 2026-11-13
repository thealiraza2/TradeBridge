"""Centralized logging module for TradeBridge.

Configures console and rotating file logging to logs/tradebridge.log (5 MB, 3 files).
Enforces security rules: NEVER logs webhook secrets or account passwords.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "tradebridge.log"

# Logger instance
logger = logging.getLogger("tradebridge")
logger.setLevel(logging.INFO)

# Formatter: timestamp - level - message
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
formatter = logging.Formatter(LOG_FORMAT)

# Avoid duplicate handlers if re-imported
if not logger.handlers:
    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler (5 MB, 3 backup files)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def sanitize_payload(payload: dict) -> dict:
    """Return a sanitized copy of a dictionary with sensitive keys redacted."""
    sanitized = {}
    for k, v in payload.items():
        if k.lower() in ("secret", "password", "mt5_password", "webhook_secret"):
            sanitized[k] = "***REDACTED***"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        else:
            sanitized[k] = v
    return sanitized
