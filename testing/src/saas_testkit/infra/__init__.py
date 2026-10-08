"""Session infrastructure."""

from saas_testkit.infra.app_loader import (
    import_service_app,
    install_service_paths,
    open_app_lifespan,
)
from saas_testkit.infra.compose import (
    Stack,
    ensure_admin_token,
    read_session,
    release_stack,
    stack_down,
    stack_up,
)
from saas_testkit.infra.containers import (
    KAFKA_TOPICS,
    Infra,
    InfraHandle,
    redis_url_for,
    start_or_attach_infra,
)
from saas_testkit.infra.template_db import (
    DbUrls,
    building_database_name,
    create_worker_database,
    drop_database,
    ensure_template_database,
    quote_ident,
    read_alembic_head,
    template_database_name,
    worker_database_name,
)
from saas_testkit.infra.xdist import (
    _layer,  # pyright: ignore[reportPrivateUsage]
    infra_required,
    is_worker,
    needs_infra,
    worker_index,
)

__all__ = [
    "KAFKA_TOPICS",
    "DbUrls",
    "Infra",
    "InfraHandle",
    "Stack",
    "_layer",
    "building_database_name",
    "create_worker_database",
    "drop_database",
    "ensure_admin_token",
    "ensure_template_database",
    "import_service_app",
    "infra_required",
    "install_service_paths",
    "is_worker",
    "needs_infra",
    "open_app_lifespan",
    "quote_ident",
    "read_alembic_head",
    "read_session",
    "redis_url_for",
    "release_stack",
    "stack_down",
    "stack_up",
    "start_or_attach_infra",
    "template_database_name",
    "worker_database_name",
    "worker_index",
]
