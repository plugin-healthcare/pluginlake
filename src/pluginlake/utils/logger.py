"""Structured logging setup for pluginlake."""

import logging
import sys

_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_TEXT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root ``pluginlake`` logger.

    Call once at application startup. All child loggers
    (e.g., ``pluginlake.storage``) inherit this configuration.

    Args:
        level: The log level to set.
    """
    root_logger = logging.getLogger("pluginlake")
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_TEXT_FORMAT, datefmt=_TEXT_DATE_FORMAT))

    root_logger.addHandler(handler)
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger for a pluginlake module.

    Usage::

        from pluginlake.utils.logger import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started")

    Args:
        name: The module name, typically ``__name__``.

    Returns:
        A logger under the ``pluginlake`` namespace.
    """
    if not name.startswith("pluginlake"):
        name = f"pluginlake.{name}"
    return logging.getLogger(name)
