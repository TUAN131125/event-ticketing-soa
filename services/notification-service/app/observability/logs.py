"""Logging helpers without importing application settings."""

import logging

_configured = False


def configure_logging(level: str) -> None:
    global _configured
    if not _configured:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
