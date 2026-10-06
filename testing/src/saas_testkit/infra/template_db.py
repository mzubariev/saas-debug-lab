"""Template database and one database per xdist worker (ADR-3).

Alembic runs with cwd set to ``migrations/`` because ``script_location`` is
relative. The template is built once under an advisory lock and reused.
Call ``ensure_template_database`` from synchronous controller code: Alembic's
``env.py`` uses ``asyncio.run``.
"""

import logging
import os
import re
import warnings
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool

from saas_testkit.config.paths import repo_root

logger = logging.getLogger("saas_testkit.template_db")

# Shared by every pytest session that builds or reuses the template.
TEMPLATE_LOCK_KEY = 815_001_815

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")

_LIST_PUBLIC_TABLES = text(
    """
    SELECT c.relname
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname NOT IN ('alembic_version', '_touched')
    ORDER BY c.relname
    """
)

_TOUCHED_TABLE = text(
    """
    CREATE TABLE IF NOT EXISTS public._touched (
        tbl text PRIMARY KEY
    )
    """
)

_TOUCHED_FUNCTION = text(
    """
    CREATE OR REPLACE FUNCTION public._mark() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        INSERT INTO public._touched (tbl) VALUES (TG_TABLE_NAME)
        ON CONFLICT DO NOTHING;
        RETURN NULL;
    END;
    $$
    """
)


def migrations_dir() -> Path:
    return repo_root() / "migrations"


def quote_ident(name: str) -> str:
    """Quote a database or table name. Rejects anything we did not generate."""
    if _IDENTIFIER.fullmatch(name) is None:
        raise ValueError(f"unsafe SQL identifier: {name}")
    return f'"{name}"'


def template_database_name(revision: str) -> str:
    name = f"app_template_{revision.replace('-', '_')}"
    quote_ident(name)
    return name


def building_database_name(revision: str) -> str:
    """Scratch name migrated, then renamed to :func:`template_database_name`."""
    name = f"{template_database_name(revision)}_building"
    quote_ident(name)
    return name


def worker_database_name(service: str, layer: str, worker_id: str) -> str:
    """``test_<service>_<layer>_<worker>`` with hyphens turned into underscores."""
    name = f"test_{service}_{layer}_{worker_id}".replace("-", "_")
    quote_ident(name)
    return name


def read_alembic_head(migrations: Path | None = None) -> str:
    """Return the single Alembic head. Raises when the graph has more than one."""
    root = migrations if migrations is not None else migrations_dir()
    with _quiet_alembic_warning():
        config = _alembic_config(root)
        heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected a single alembic head, found {list(heads)}")
    return heads[0]


@dataclass(frozen=True, slots=True, kw_only=True)
class DbUrls:
    """Sync and async URLs for one database, plus the env Alembic and the apps read."""

    name: str
    user: str
    password: str
    host: str
    port: int

    @classmethod
    def for_database(cls, admin_url: str, name: str) -> DbUrls:
        quote_ident(name)
        url = make_url(admin_url)
        if url.host is None or url.username is None or not url.password:
            raise ValueError("admin URL needs a user, a password, and a host")
        return cls(
            name=name,
            user=url.username,
            password=url.password,
            host=url.host,
            port=url.port or 5432,
        )

    @property
    def async_url(self) -> str:
        return self._render("postgresql+asyncpg")

    @property
    def sync_url(self) -> str:
        return self._render("postgresql+psycopg")

    def postgres_env(self) -> dict[str, str]:
        return {
            "POSTGRES_HOST": self.host,
            "POSTGRES_PORT": str(self.port),
            "POSTGRES_DB": self.name,
            "POSTGRES_USER": self.user,
            "POSTGRES_PASSWORD": self.password,
        }

    def _render(self, drivername: str) -> str:
        url = make_url(f"{drivername}://").set(
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        )
        return url.render_as_string(hide_password=False)


def admin_engine(admin_url: str) -> Engine:
    """Autocommit engine. ``CREATE DATABASE`` cannot run inside a transaction."""
    url = make_url(admin_url).set(drivername="postgresql+psycopg")
    return create_engine(
        url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )


def ensure_template_database(admin_url: str) -> str:
    """Reuse ``app_template_<head>``, or migrate a ``_building`` database and rename it.

    The rename happens only after every connection to the scratch database is gone.
    A leftover ``_building`` database from a crashed run is dropped first.
    """
    head = read_alembic_head()
    final = template_database_name(head)
    building = building_database_name(head)
    engine = admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": TEMPLATE_LOCK_KEY})
            try:
                terminate_connections(admin_url, building)
                _drop_database(conn, building)
                if _database_exists(conn, final):
                    logger.info("reusing template database %s; alembic upgrade skipped", final)
                    return final
                logger.info("building template database %s", building)
                _create_from_template(conn, building, template=None)
                try:
                    urls = DbUrls.for_database(admin_url, building)
                    _upgrade_and_check(urls)
                    install_touched_tracking(urls)
                    terminate_connections(admin_url, building)
                    _rename_database(conn, building, final)
                except Exception:
                    terminate_connections(admin_url, building)
                    _drop_database(conn, building)
                    raise
                logger.info("template database %s is ready", final)
                return final
            finally:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": TEMPLATE_LOCK_KEY},
                )
    finally:
        engine.dispose()


def create_worker_database(admin_url: str, template: str, name: str) -> DbUrls:
    """Drop ``name`` if it exists, then clone it from the template."""
    quote_ident(name)
    quote_ident(template)
    engine = admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            terminate_connections(admin_url, name)
            _drop_database(conn, name)
            _create_from_template(conn, name, template=template)
    finally:
        engine.dispose()
    return DbUrls.for_database(admin_url, name)


def drop_database(admin_url: str, name: str) -> None:
    engine = admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            terminate_connections(admin_url, name)
            _drop_database(conn, name)
    finally:
        engine.dispose()


def install_touched_tracking(urls: DbUrls) -> None:
    """Statement-level triggers that record tables written since the last cleanup."""
    engine = create_engine(urls.sync_url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(_TOUCHED_TABLE)
            conn.execute(_TOUCHED_FUNCTION)
            tables = conn.execute(_LIST_PUBLIC_TABLES).scalars().all()
            for table in tables:
                _install_trigger(conn, table)
    finally:
        engine.dispose()


def terminate_connections(admin_url: str, name: str) -> None:
    """Close every other session on ``name`` so ``CREATE DATABASE ... TEMPLATE`` can run."""
    quote_ident(name)
    engine = admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
    finally:
        engine.dispose()


def _database_exists(conn: Connection, name: str) -> bool:
    found = conn.execute(
        text("SELECT 1 FROM pg_database WHERE datname = :name"),
        {"name": name},
    ).scalar()
    return found is not None


def _create_from_template(conn: Connection, name: str, *, template: str | None) -> None:
    statement = f"CREATE DATABASE {quote_ident(name)}"
    if template is not None:
        statement = f"{statement} TEMPLATE {quote_ident(template)}"
    conn.execute(text(statement))


def _drop_database(conn: Connection, name: str) -> None:
    conn.execute(text(f"DROP DATABASE IF EXISTS {quote_ident(name)}"))


def _rename_database(conn: Connection, source: str, target: str) -> None:
    conn.execute(text(f"ALTER DATABASE {quote_ident(source)} RENAME TO {quote_ident(target)}"))


def _install_trigger(conn: Connection, table: str) -> None:
    ident = quote_ident(table)
    conn.execute(text(f"DROP TRIGGER IF EXISTS _mark_touched ON {ident}"))
    conn.execute(
        text(
            f"CREATE TRIGGER _mark_touched AFTER INSERT OR UPDATE OR DELETE "
            f"ON {ident} FOR EACH STATEMENT EXECUTE FUNCTION public._mark()"
        )
    )


def _upgrade_and_check(urls: DbUrls) -> None:
    migrations = migrations_dir()
    previous = Path.cwd()
    saved = _push_env(urls.postgres_env())
    os.chdir(migrations)
    try:
        with _quiet_alembic_warning():
            config = _alembic_config(migrations)
            command.upgrade(config, "head")
            command.check(config)
        logger.info("alembic upgrade head and drift check passed for %s", urls.name)
    finally:
        os.chdir(previous)
        _pop_env(saved)


def _alembic_config(migrations: Path) -> Config:
    config = Config(str(migrations / "alembic.ini"))
    config.set_main_option("script_location", str(migrations / "alembic"))
    return config


@contextmanager
def _quiet_alembic_warning() -> Generator[None]:
    """The lab ini has no ``path_separator``. Leave that file alone."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="No path_separator found in configuration",
            category=DeprecationWarning,
        )
        yield


def _push_env(updates: Mapping[str, str]) -> dict[str, str | None]:
    saved = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    return saved


def _pop_env(saved: Mapping[str, str | None]) -> None:
    for key, old in saved.items():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
