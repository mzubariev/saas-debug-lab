"""CLI flags for `python -m saas_testkit.infra.compose wait`. No Docker."""

import pytest

import saas_testkit.infra.compose as compose


@pytest.mark.parametrize(
    ("argv", "wiremock", "admin"),
    [
        (["wait"], False, False),
        (["wait", "--wiremock-catch-all"], True, False),
        (["wait", "--ensure-admin-token"], False, True),
        (["wait", "--wiremock-catch-all", "--ensure-admin-token"], True, True),
    ],
)
def test_wait_cli_parses_flags(
    argv: list[str],
    wiremock: bool,
    admin: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[bool, bool]] = []

    def capture(
        *,
        install_wiremock_catch_all: bool = False,
        ensure_admin_token: bool = False,
    ) -> None:
        seen.append((install_wiremock_catch_all, ensure_admin_token))

    monkeypatch.setattr(compose, "wait_for_stack", capture)
    compose.main(argv)

    assert seen == [(wiremock, admin)]
