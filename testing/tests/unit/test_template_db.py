"""The template is migrated under a scratch name, then renamed. No Docker."""

import pytest

from saas_testkit.infra import DbUrls, building_database_name, ensure_template_database

_MODULE = "saas_testkit.infra.template_db"

_ADMIN = "postgresql://postgres:test@localhost:5432/postgres"
_FINAL = "app_template_0002"
_BUILDING = "app_template_0002_building"


class _Result:
    def __init__(self, found: bool) -> None:
        self._found = found

    def scalar(self) -> int | None:
        return 1 if self._found else None


class _Conn:
    def __init__(self, *, final_exists: bool) -> None:
        self.sql: list[str] = []
        self._final_exists = final_exists

    def execute(self, statement: object, _params: object = None) -> _Result:
        sql = str(statement)
        self.sql.append(sql)
        return _Result(self._final_exists and "pg_database" in sql)


class _Engine:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn
        self.disposed = False

    def connect(self) -> _Connect:
        return _Connect(self._conn)

    def dispose(self) -> None:
        self.disposed = True


class _Connect:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def __enter__(self) -> _Conn:
        return self._conn

    def __exit__(self, *_exc: object) -> None:
        return None


def test_building_name_is_the_final_name_plus_suffix() -> None:
    assert building_database_name("0002") == "app_template_0002_building"


def test_missing_template_is_built_then_renamed(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(final_exists=False)
    upgraded: list[str] = []
    monkeypatch.setattr(f"{_MODULE}.read_alembic_head", lambda: "0002")
    monkeypatch.setattr(f"{_MODULE}.admin_engine", lambda _url: _Engine(conn))
    monkeypatch.setattr(f"{_MODULE}.terminate_connections", lambda _url, _name: None)

    def upgrade(urls: DbUrls) -> None:
        upgraded.append(urls.name)

    def track(urls: DbUrls) -> None:
        upgraded.append(urls.name)

    monkeypatch.setattr(f"{_MODULE}._upgrade_and_check", upgrade)
    monkeypatch.setattr(f"{_MODULE}.install_touched_tracking", track)

    assert ensure_template_database(_ADMIN) == _FINAL

    ddl = [sql for sql in conn.sql if sql.startswith(("DROP", "CREATE", "ALTER"))]
    assert ddl == [
        f'DROP DATABASE IF EXISTS "{_BUILDING}"',
        f'CREATE DATABASE "{_BUILDING}"',
        f'ALTER DATABASE "{_BUILDING}" RENAME TO "{_FINAL}"',
    ]
    assert upgraded == [_BUILDING, _BUILDING]
    assert f'CREATE DATABASE "{_FINAL}"' not in conn.sql


def test_existing_template_is_reused_after_the_leftover_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _Conn(final_exists=True)
    monkeypatch.setattr(f"{_MODULE}.read_alembic_head", lambda: "0002")
    monkeypatch.setattr(f"{_MODULE}.admin_engine", lambda _url: _Engine(conn))
    monkeypatch.setattr(f"{_MODULE}.terminate_connections", lambda _url, _name: None)
    monkeypatch.setattr(
        f"{_MODULE}._upgrade_and_check",
        lambda _urls: pytest.fail("alembic must not run when the template exists"),
    )

    assert ensure_template_database(_ADMIN) == _FINAL

    ddl = [sql for sql in conn.sql if sql.startswith(("DROP", "CREATE", "ALTER"))]
    assert ddl == [f'DROP DATABASE IF EXISTS "{_BUILDING}"']


def test_failed_upgrade_drops_the_building_database(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn(final_exists=False)
    monkeypatch.setattr(f"{_MODULE}.read_alembic_head", lambda: "0002")
    monkeypatch.setattr(f"{_MODULE}.admin_engine", lambda _url: _Engine(conn))
    monkeypatch.setattr(f"{_MODULE}.terminate_connections", lambda _url, _name: None)

    def upgrade(_urls: DbUrls) -> None:
        raise RuntimeError("migrate failed")

    monkeypatch.setattr(f"{_MODULE}._upgrade_and_check", upgrade)

    with pytest.raises(RuntimeError, match="migrate failed"):
        ensure_template_database(_ADMIN)

    assert f'ALTER DATABASE "{_BUILDING}" RENAME TO "{_FINAL}"' not in conn.sql
    assert conn.sql.count(f'DROP DATABASE IF EXISTS "{_BUILDING}"') == 2
