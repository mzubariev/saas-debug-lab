"""Service settings and the service catalogue."""

from saas_testkit.config.paths import repo_root
from saas_testkit.config.services import SERVICES, ServiceSpec, redis_db_index, service_environment
from saas_testkit.config.settings import POSTGRES_IMAGE, KitSettings

__all__ = [
    "POSTGRES_IMAGE",
    "SERVICES",
    "KitSettings",
    "ServiceSpec",
    "redis_db_index",
    "repo_root",
    "service_environment",
]
