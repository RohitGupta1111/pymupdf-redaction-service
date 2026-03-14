"""Logging configuration."""

import logging
import sys
from app.config import settings


def debug_logs_enabled(settings_obj=None):
    """Return True if sensitive/verbose redaction logs (e.g. extracted text) should be emitted."""
    s = settings_obj if settings_obj is not None else settings
    return s.LOG_LEVEL.upper() == "DEBUG" or s.ENABLE_DEBUG_REDACTION_LOGS is True


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
