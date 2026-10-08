"""auth-service flow for the consumer-model check. The app fixture is the HTTP one."""

from tests.component.auth_service.conftest import auth, user_cache  # noqa: F401
from tests.component.conftest import db, rows, session_maker  # noqa: F401
