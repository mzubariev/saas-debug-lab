"""One Polyfactory seed per process."""

from polyfactory.factories.base import BaseFactory

_seeded = False


def seed_factories_once(seed: object) -> None:
    """Call ``seed_random`` once. A second call would rewind ids already inserted."""
    global _seeded
    if _seeded:
        return
    if not isinstance(seed, int):
        raise RuntimeError("pytest-randomly did not provide an integer seed")
    BaseFactory.seed_random(seed)
    _seeded = True
