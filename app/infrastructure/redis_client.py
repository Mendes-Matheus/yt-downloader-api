from __future__ import annotations

from redis.asyncio import Redis
import ssl

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

    is_upstash = "upstash.io" in redis_url

    return Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,

        # Upstash exige SSL
        ssl=True if redis_url.startswith("rediss://") or is_upstash else False,
        ssl_cert_reqs=ssl.CERT_NONE if is_upstash else None,  # evita problema comum com Upstash

        # ⚡ tuning importante pra latência externa
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        health_check_interval=15,
        retry_on_timeout=True,
    )