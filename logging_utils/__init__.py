"""Shared logging utilities: TRACE level, redaction, and setup."""

import logging
import re
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# TRACE level (5, below DEBUG=10)
# ---------------------------------------------------------------------------

TRACE: int = 5
logging.addLevelName(TRACE, "TRACE")


def _trace_method(
    self: logging.Logger, message: object, *args: Any, **kwargs: Any
) -> None:
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)  # type: ignore[attr-defined]


logging.Logger.trace = _trace_method  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    redact_sensitive_data: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9])([A-Za-z0-9._%+\-]*)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_KEY_VALUE_RE = re.compile(
    r"(?i)((?:api[_\-]?key|password|passwd|secret|access_token|refresh_token"
    r"|oauth[_\-]?token|cookie)\s*[=:]\s*)\S+"
)

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "token",
        "authorization",
        "auth",
        "cookie",
        "oauth_token",
    }
)


def redact(value: Any) -> Any:
    """Redact emails, bearer tokens, and key=value secrets from a string or dict."""
    if isinstance(value, str):
        value = _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(3)}", value)
        value = _BEARER_RE.sub(lambda m: f"{m.group(1)}[REDACTED]", value)
        value = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in _SENSITIVE_KEYS else redact(v)
            for k, v in value.items()
        }
    return value


class RedactionFilter(logging.Filter):
    """Redacts sensitive data from log records in-place."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = None
        return True


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _level_to_numeric(level: str) -> int:
    upper = level.upper()
    if upper == "TRACE":
        return TRACE
    numeric = getattr(logging, upper, None)
    if isinstance(numeric, int):
        return numeric
    return logging.INFO


def configure_logging(level: str = "INFO", redact_sensitive: bool = True) -> None:
    """Configure root logger with optional TRACE support and redaction.

    Should be called once at application startup.
    """
    numeric = _level_to_numeric(level)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    root = logging.getLogger()
    root.setLevel(numeric)
    if redact_sensitive and not any(
        isinstance(f, RedactionFilter) for f in root.filters
    ):
        root.addFilter(RedactionFilter())
    for name in ("api_server", "jarvis"):
        logging.getLogger(name).setLevel(numeric)
