from __future__ import annotations

import os
from functools import lru_cache

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - compatibilidade durante rollout/deploy
    Redis = None  # type: ignore[assignment]

def get_rate_limit_redis_url() -> str | None:
    return (
        os.getenv("RATE_LIMIT_REDIS_URL", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or None
    )


@lru_cache(maxsize=1)
def get_redis_client() -> Redis | None:
    redis_url = get_rate_limit_redis_url()
    if Redis is None or not redis_url:
        return None

    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
        health_check_interval=30,
        retry_on_timeout=True,
    )
