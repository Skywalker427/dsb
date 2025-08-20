import logging
import sys
from typing import Any, Dict

import structlog
from structlog import configure, get_logger
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

from app.core.config import get_settings

settings = get_settings()


def setup_logging() -> None:
    """Configure structured logging with structlog."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Choose renderer based on environment
    if settings.environment == "development":
        renderer = ConsoleRenderer()
    else:
        renderer = JSONRenderer()

    # Configure structlog
    configure(
        processors=[
            add_log_level,
            TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_structured_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return get_logger(name)