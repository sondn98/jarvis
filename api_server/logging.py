from logging_utils import LoggingConfig
from logging_utils import configure_logging as _configure_logging


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger for the API server."""
    log_config = LoggingConfig()
    _configure_logging(level=level, redact_sensitive=log_config.redact_sensitive_data)
