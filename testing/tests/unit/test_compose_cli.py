"""CLI flags for `python -m saas_testkit.infra.compose wait`. No Docker."""

from pathlib import Path

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


def test_boot_table_total_is_the_sequential_phases(tmp_path: Path) -> None:
    phases = tmp_path / "phases.tsv"
    phases.write_text("image build/pull\t10\ncompose up\t20\nmigrations\t30\nnginx\t40\nwait\t50\n")
    summary = tmp_path / "summary.md"
    compose.write_boot_summary(phases, summary)
    text = summary.read_text()
    assert "| image build/pull | 10.0s |" in text
    assert "| compose up | 20.0s |" in text
    assert "| migrations | 30.0s |" in text
    assert "| nginx | 40.0s |" in text
    assert "| total | 80.0s |" in text
    assert "| wait |" not in text
