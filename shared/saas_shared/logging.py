import logging
from typing import Any

import structlog
from structlog.typing import EventDict


def _add_service_name(service_name: str):
    def processor(logger: Any, method: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service_name
        return event_dict
    return processor


def setup_logging(log_level: str = "INFO", service_name: str = "") -> None:

    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service_name(service_name),
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
    )
