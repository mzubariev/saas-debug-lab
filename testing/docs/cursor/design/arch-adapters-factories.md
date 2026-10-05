# Testing architecture: adapters, flows, factories
Used by P1 and P2. Every identifier inside the code skeletons below is illustrative. Anything marked `PLACEHOLDER`, `<SHA>`, `<pinned-version>` or described as "from SUT_MAP" must be replaced with a real value before use.

## 6.3 Adapters -> flows -> tests
```python
# domain: ApiResponse[T] = frozen dataclass(status, data: T | None, error: ProblemBody | None, headers, elapsed); ProblemBody mirrors the FastAPI error body {"detail": str | list of validation errors}, there is no error code field

# adapters/http/tasks.py: concrete class; the transport is the injected client's concern
class HttpTaskApi:
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None: ...
    async def create(self, body: TaskCreate) -> ApiResponse[Task]: ...
    async def start(self, task_id: UUID) -> ApiResponse[Task]: ...

# adapters/kafka/reader.py: real Redpanda/Kafka consumer, same class at component and integration
class KafkaEventReader:
    async def wait_for(self, topic: str, *, match: Callable[[Envelope], bool], timeout: float) -> Envelope: ...

# flows/task_lifecycle.py: business language; takes concrete adapters via DI
class TaskLifecycle:
    def __init__(self, tasks: HttpTaskApi, events: KafkaEventReader | None = None) -> None: ...
    async def new_task(self, **overrides) -> Task: ...             # precondition step: asserts 201 + schema inside
    async def move_to_completed(self, task: Task) -> Task: ...     # precondition step
    async def start(self, task: Task) -> ApiResponse[Task]: ...    # behaviour under test: NO assertion inside
    async def task_created_event(self, task: Task) -> Envelope: ...   # uses eventually()

# test: the assertion is visible in the test body
async def test_completed_task_cannot_be_started_again(lifecycle: TaskLifecycle):
    task = await lifecycle.new_task()
    await lifecycle.move_to_completed(task)

    response = await lifecycle.start(task)

    assert response.status == 409
    assert "Cannot start task" in response.error.detail           # PLACEHOLDER: exact message from SUT_MAP (409 body is {"detail": "..."})
```
Rule: precondition steps may assert inside flows; the behaviour under test is asserted in the test body. Raw status access never leaves adapters/flows, but the verdict always stays in the test.

## 6.5 Factories (Polyfactory)
One factory family for all layers; the method decides the layer behaviour:
- F.build(**kw) / F.batch(n): no I/O, plain Python object. Unit, contract, API payloads, event envelopes.
- await F.create_async(**kw) / create_batch_async(n): async SQLAlchemy session. Component/contract rows (SQLAlchemyFactory).
- F.create_sync(**kw): sync SQLAlchemy session. Sync contexts: one-time seed under FileLock (extra users, synthetic user), Playwright/integration/smoke setup against the stack's PG.
```python
from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

class TaskCreateFactory(ModelFactory[TaskCreate]):      # Pydantic v2 DTO -> .build() only
    __model__ = TaskCreate
    title = Use(unique_title, "task")                   # constraints (min_length...) are respected automatically

class TaskRowFactory(SQLAlchemyFactory[Task]):          # ORM row from saas_shared.models
    __set_relationships__ = False                       # set explicitly (required by newer Polyfactory)
    status = Use(lambda: TaskStatus.CREATED)

# tests/component/conftest.py: bind the factories to THIS test's session without global state
@pytest.fixture
def rows(db: AsyncSession) -> Rows:
    class BoundTask(TaskRowFactory):
        __async_session__ = db                          # a session or a zero-arg callable
    class BoundUser(UserRowFactory):
        __async_session__ = db
    return Rows(task=BoundTask, user=BoundUser)

task = await rows.task.create_async(status=TaskStatus.COMPLETED)     # really committed to the worker DB; unique values keep it isolated
```
Notes (binding rules for session binding, seeding and argon2 caching: testing-core.mdc "Data and isolation"):
1. Polyfactory's SQLAlchemy persistence commits by default: rows are really committed, so the app's engine, the scheduler and other processes see them.
2. One seed per run: a session fixture calls Factory.seed_random(config.getoption("randomly_seed")), so the number printed by pytest-randomly reproduces both the test order and the factory data (Polyfactory has its own Random instance that pytest-randomly does not reseed). There is no separate run_seed; the failure report prints this seed.
3. Random data may violate business rules: override constrained fields (status, FKs, unique titles).
4. Faker is bundled (Factory.__faker__); custom providers in factories/providers.py (unique_title, jwt_claims).
5. UserRow.password_hash = one cached argon2 hash.
6. Event factories (ModelFactory[Envelope[TaskCreatedPayload]]) build envelopes; a Builder only for Envelope/webhook bodies with many optional parts. Internal trusted dataclasses use DataclassFactory.
