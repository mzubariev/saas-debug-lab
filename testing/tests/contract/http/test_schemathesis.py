"""Generated calls stay inside the OpenAPI contract. A 500 is a failure, not a skip."""

from collections.abc import Callable

import pytest
from schemathesis.schemas import BaseSchema
from schemathesis.specs.openapi.schemas import OpenApiSchema

_FUZZED = frozenset({"task-service", "auth-service", "webhook-receiver"})


def test_generated_calls_match_openapi(
    fuzz_schema: OpenApiSchema,
    check_openapi: Callable[[BaseSchema], None],
    pytestconfig: pytest.Config,
) -> None:
    service = pytestconfig.getoption("service")
    if service not in _FUZZED:
        pytest.skip("Schemathesis covers task-service, auth-service, and webhook-receiver")
    check_openapi(fuzz_schema)
