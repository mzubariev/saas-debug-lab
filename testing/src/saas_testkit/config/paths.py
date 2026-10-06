"""Paths shared by the kit. The package lives in the repo, so the root is fixed."""

from pathlib import Path


def repo_root() -> Path:
    """Repository root (the directory that contains `testing/` and `services/`)."""
    return Path(__file__).resolve().parents[4]


def testing_root() -> Path:
    """The `testing/` project directory."""
    return Path(__file__).resolve().parents[3]
