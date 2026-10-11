"""Polyfactory seed for one pytest session. The session fixture calls this once."""

from polyfactory.factories.base import BaseFactory


def seed_factories_once(seed: object) -> None:
    """Call ``seed_random`` with the pytest-randomly integer."""
    if not isinstance(seed, int):
        raise RuntimeError("pytest-randomly did not provide an integer seed")
    BaseFactory.seed_random(seed)
