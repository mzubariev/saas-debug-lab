import structlog
from fastapi import FastAPI
from saas_shared.health import router as health_router

from .api.routes.routes import router as api_router
from .core.config import settings

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

app = FastAPI(title=settings.service_name)
app.include_router(health_router)
app.include_router(api_router)
