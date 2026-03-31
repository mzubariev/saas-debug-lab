"""Redis lifecycle + JSON cache — shared implementation in ``saas_shared.redis_cache``."""

from saas_shared.redis_cache import cache_get, cache_set, start_redis, stop_redis

__all__ = ["cache_get", "cache_set", "start_redis", "stop_redis"]
