"""UI fixtures. The controller starts the stack; this layer only reads the token file."""

from collections.abc import Iterator
from typing import NamedTuple, cast
from uuid import uuid4

import httpx
import pytest
from playwright.sync_api import Page

from saas_testkit.adapters.playwright import BoardPage, LoginPage
from saas_testkit.config import KitSettings
from saas_testkit.context import RunContext, using_context
from saas_testkit.domain.tasks import Task
from saas_testkit.factories import TaskCreateFactory, seed_factories_once
from saas_testkit.infra import read_session

# frontend/src/lib/apiClient.ts TOKEN_KEY
_TOKEN_KEY = "saas_debug_token"


class SeedUser(NamedTuple):
    username: str
    password: str


class UiTasks:
    """Sync task API for data setup. UI tests cannot share the async client."""

    def __init__(self, base_url: str, token: str, ctx: RunContext) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", **ctx.headers()},
            timeout=30,
        )

    def close(self) -> None:
        self._client.close()

    def create(self, title: str | None = None) -> Task:
        """Precondition. Raises if the service does not return a task."""
        body = TaskCreateFactory.build() if title is None else TaskCreateFactory.build(title=title)
        response = self._client.post("/tasks", json=body.model_dump())
        if not response.is_success:
            raise AssertionError(f"expected a created task, got {response.status_code}")
        return Task.model_validate(cast(object, response.json()))

    def find(self, title: str) -> Task | None:
        """The first task with this title. Raises when a second one exists."""
        response = self._client.get("/tasks")
        if not response.is_success:
            raise RuntimeError(f"task list failed: {response.status_code}")
        found: Task | None = None
        for item in _rows(cast(object, response.json())):
            task = Task.model_validate(item)
            if task.title != title:
                continue
            if found is not None:
                raise RuntimeError(f"more than one task titled {title}")
            found = task
        return found


def _rows(parsed: object) -> list[object]:
    if isinstance(parsed, list):
        return cast(list[object], parsed)
    raise RuntimeError("task list was not a JSON array")


def pytest_configure(config: pytest.Config) -> None:
    """This layer keeps a trace and a screenshot when a test fails. Video stays off."""
    config.option.tracing = "retain-on-failure"
    config.option.screenshot = "only-on-failure"
    config.option.video = "off"


@pytest.fixture(scope="session", autouse=True)
def _seed_factories(pytestconfig: pytest.Config) -> None:
    seed_factories_once(pytestconfig.getoption("randomly_seed"))


@pytest.fixture(scope="session")
def base_url() -> str:
    return _ui_origin()


@pytest.fixture(scope="session")
def admin() -> SeedUser:
    return SeedUser("admin", "admin123")


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid4().hex


@pytest.fixture(autouse=True)
def run_context(run_id: str, request: pytest.FixtureRequest) -> Iterator[RunContext]:
    ctx = RunContext.create(run_id=run_id, test_id=request.node.nodeid)
    with using_context(ctx):
        yield ctx


@pytest.fixture
def browser_context_args(
    browser_context_args: dict[str, object],
    request: pytest.FixtureRequest,
) -> dict[str, object]:
    """Block service workers. Signed-in tests reuse the per-run admin token."""
    args = {
        **browser_context_args,
        "service_workers": "block",
        "viewport": {"width": 1920, "height": 1080},
    }
    if request.node.get_closest_marker("anonymous") is None:
        args["storage_state"] = _storage_state()
    return args


@pytest.fixture
def login(page: Page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def board(page: Page) -> BoardPage:
    return BoardPage(page)


@pytest.fixture
def tasks(run_context: RunContext) -> Iterator[UiTasks]:
    session = read_session()
    api = UiTasks(session.base_url, session.access_token, run_context)
    try:
        yield api
    finally:
        api.close()


def _ui_origin() -> str:
    return KitSettings().ui_url


def _storage_state() -> dict[str, object]:
    return {
        "cookies": [],
        "origins": [
            {
                "origin": _ui_origin(),
                "localStorage": [
                    {"name": _TOKEN_KEY, "value": read_session().access_token},
                ],
            }
        ],
    }
