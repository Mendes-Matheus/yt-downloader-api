from __future__ import annotations

import os
import ssl
from functools import lru_cache

try:
    from redis import Redis as SyncRedis
    from redis.asyncio import Redis as AsyncRedis
except ImportError:  # pragma: no cover - compatibilidade durante rollout/deploy
    SyncRedis = None  # type: ignore[assignment]
    AsyncRedis = None  # type: ignore[assignment]


def get_rate_limit_redis_url() -> str | None:
    return (
        os.getenv("RATE_LIMIT_REDIS_URL", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or None
    )


@lru_cache(maxsize=1)
def get_redis_client() -> AsyncRedis | None:
    redis_url = get_rate_limit_redis_url()
    if AsyncRedis is None or not redis_url:
        return None

    is_upstash = "upstash.io" in redis_url

    return AsyncRedis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        ssl_cert_reqs=ssl.CERT_NONE if is_upstash else ssl.CERT_REQUIRED,
        socket_connect_timeout=3.0,
        socket_timeout=3.0,
        health_check_interval=15,
        retry_on_timeout=True,
        max_connections=10,
        socket_keepalive=True,
    )


@lru_cache(maxsize=1)
def get_sync_redis_client() -> SyncRedis | None:
    redis_url = get_rate_limit_redis_url()
    if SyncRedis is None or not redis_url:
        return None

    is_upstash = "upstash.io" in redis_url

    return SyncRedis.from_url(
        redis_url,
        # encoding="utf-8",
        decode_responses=False,  # RQ espera bytes, não strings
        ssl_cert_reqs=ssl.CERT_NONE if is_upstash else ssl.CERT_REQUIRED,
        socket_connect_timeout=3.0,
        socket_timeout=3.0,
        health_check_interval=15,
        retry_on_timeout=True,
        max_connections=10,
        socket_keepalive=True,
    )
