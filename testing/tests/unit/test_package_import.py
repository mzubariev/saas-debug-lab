"""Bootstrap check that the installed kit imports."""

import importlib


def test_package_imports_when_installed_succeeds() -> None:
    module = importlib.import_module("saas_testkit")
    assert module.__name__ == "saas_testkit"
