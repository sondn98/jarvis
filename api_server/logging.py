import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger for the API server."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("api_server").setLevel(numeric)
