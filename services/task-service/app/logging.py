import logging
import structlog


def setup_logging():

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.processors.JSONRenderer()
        ]
    )