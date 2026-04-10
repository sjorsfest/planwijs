from __future__ import annotations

from urllib.parse import urlparse

from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings

_pool: Redis | None = None


async def get_redis_pool() -> Redis:
    global _pool
    if _pool is None:
        _pool = Redis.from_url(settings.redis_url, decode_responses=True)
    return _pool


def get_arq_redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or "0"),
        password=parsed.password,
    )


async def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
