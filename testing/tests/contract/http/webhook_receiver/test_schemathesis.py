"""POST /webhooks/inbound returns 500 after a successful publish (BUG-5)."""

from collections.abc import Callable

import pytest
from schemathesis.schemas import BaseSchema
from schemathesis.specs.openapi.schemas import OpenApiSchema

pytestmark = pytest.mark.xfail(
    strict=True,
    reason="BUG-5: the success log passes event= and POST /webhooks/inbound returns 500",
)


def test_inbound_generated_calls_are_not_server_errors(
    fuzz_schema: OpenApiSchema,
    check_openapi: Callable[[BaseSchema], None],
) -> None:
    schema = fuzz_schema.include(method="POST", path="/webhooks/inbound")

    check_openapi(schema)
