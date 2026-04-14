from __future__ import annotations

import math
import time
import uuid
from typing import Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.infrastructure.redis_client import get_rate_limit_redis_url, get_redis_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Rotas que NÃO sofrem rate limiting
_EXEMPT_PREFIXES = ("/health", "/ready")
_RATE_LIMIT_NAMESPACE: Final[str] = "rate_limit"
_RESPONSE_HEADER_NAMES: Final[tuple[bytes, bytes, bytes]] = (
    b"x-ratelimit-limit",
    b"x-ratelimit-remaining",
    b"x-ratelimit-reset",
)


class RateLimitMiddleware:
    """
    Rate limit distribuído usando Sliding Window com Redis ZSET.

    Compatibilidade:
    - Mantém uso como middleware ASGI puro.
    - Mantém assinatura de configuração atual.
    - Em falhas de Redis opera em fail-open para não indisponibilizar a API.
    """

    def __init__(
        self,
        app,
        max_requests: int = 1,
        window_seconds: int = 3600,
        scope_prefix: str = "global",
        by_route: bool = False,
    ):
        self.app = app
        self._max = max_requests
        self._window = window_seconds
        self._window_ms = window_seconds * 1000
        self._scope_prefix = scope_prefix
        self._by_route = by_route
        self._redis = get_redis_client()
        self._redis_url = get_rate_limit_redis_url()
        self._logged_missing_redis_config = False
        self._logged_redis_failure = False

    def _get_identifier(self, headers: Headers, scope) -> str:
        api_key = headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key.strip()}"

        forwarded = headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client = scope.get("client")
        if client and client[0]:
            return f"ip:{client[0]}"

        return "unknown"

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in _EXEMPT_PREFIXES)

    def _build_rate_key(self, identifier: str, path: str) -> str:
        scope_key = self._scope_prefix
        if self._by_route:
            normalized_path = path.strip("/") or "root"
            scope_key = f"{scope_key}:{normalized_path.replace('/', ':')}"
        return f"{_RATE_LIMIT_NAMESPACE}:{scope_key}:{identifier}"

    def _build_headers(self, limit: int, remaining: int, reset_at: int) -> list[tuple[bytes, bytes]]:
        return [
            (_RESPONSE_HEADER_NAMES[0], str(limit).encode("latin-1")),
            (_RESPONSE_HEADER_NAMES[1], str(max(remaining, 0)).encode("latin-1")),
            (_RESPONSE_HEADER_NAMES[2], str(max(reset_at, 0)).encode("latin-1")),
        ]

    def _default_headers(self, now_ms: int) -> list[tuple[bytes, bytes]]:
        reset_at = math.ceil((now_ms + self._window_ms) / 1000)
        return self._build_headers(self._max, self._max, reset_at)

    def _merge_headers(
        self,
        current_headers: list[tuple[bytes, bytes]],
        rate_limit_headers: list[tuple[bytes, bytes]],
    ) -> list[tuple[bytes, bytes]]:
        filtered_headers = [
            header for header in current_headers if header[0].lower() not in _RESPONSE_HEADER_NAMES
        ]
        filtered_headers.extend(rate_limit_headers)
        return filtered_headers

    async def _evaluate_request(self, key: str, now_ms: int) -> dict[str, int | bool]:
        if self._redis is None:
            raise RuntimeError("Redis client unavailable")

        window_start_ms = now_ms - self._window_ms
        member = f"{now_ms}-{uuid.uuid4().hex}"

        pipeline = self._redis.pipeline(transaction=False)
        pipeline.zremrangebyscore(key, 0, window_start_ms)
        pipeline.zadd(key, {member: now_ms})
        pipeline.zcard(key)
        pipeline.expire(key, max(self._window + 1, 1))
        pipeline.zrange(key, 0, 0, withscores=True)
        _, _, current_count, _, oldest_entries = await pipeline.execute()

        try:
            _, _, current_count, _, oldest_entries = await pipeline.execute()
        except Exception:
            raise  # já tratado no fail-open (middleware)

        oldest_score = now_ms
        if oldest_entries:
            oldest_score = int(oldest_entries[0][1])

        if current_count > self._max:
            rollback = self._redis.pipeline(transaction=True)
            rollback.zrem(key, member)
            rollback.expire(key, max(self._window + 1, 1))
            await rollback.execute()

            retry_after = max(1, math.ceil(((oldest_score + self._window_ms) - now_ms) / 1000))
            return {
                "allowed": False,
                "remaining": 0,
                "reset_at": math.ceil((oldest_score + self._window_ms) / 1000),
                "retry_after": retry_after,
            }

        return {
            "allowed": True,
            "remaining": max(self._max - current_count, 0),
            "reset_at": math.ceil((oldest_score + self._window_ms) / 1000),
            "retry_after": 0,
        }

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        now_ms = int(time.time() * 1000)

        if self._is_exempt(path):
            default_headers = self._default_headers(now_ms)

            async def send_exempt(message):
                if message["type"] == "http.response.start":
                    message["headers"] = self._merge_headers(
                        list(message.get("headers", [])),
                        default_headers,
                    )
                await send(message)

            await self.app(scope, receive, send_exempt)
            return

        headers = Headers(scope=scope)
        identifier = self._get_identifier(headers, scope)
        key = self._build_rate_key(identifier, path)

        try:
            result = await self._evaluate_request(key, now_ms)
            self._logged_redis_failure = False
            response_headers = self._build_headers(
                self._max,
                int(result["remaining"]),
                int(result["reset_at"]),
            )
        except Exception as exc:
            if not self._redis_url:
                if not self._logged_missing_redis_config:
                    logger.warning(
                        '"rate_limit_disabled":"redis_not_configured","path":"%s"',
                        path,
                    )
                    self._logged_missing_redis_config = True
            elif not self._logged_redis_failure:
                logger.warning(
                    '"rate_limit_redis_failure":"%s","path":"%s","identifier":"%s"',
                    str(exc),
                    path,
                    identifier,
                )
                self._logged_redis_failure = True
            response_headers = self._default_headers(now_ms)

            async def send_fail_open(message):
                if message["type"] == "http.response.start":
                    message["headers"] = self._merge_headers(
                        list(message.get("headers", [])),
                        response_headers,
                    )
                await send(message)

            await self.app(scope, receive, send_fail_open)
            return

        if not result["allowed"]:
            logger.warning(
                '"rate_limit_blocked":true,"identifier":"%s","path":"%s","limit":%s,"window_seconds":%s',
                identifier,
                path,
                self._max,
                self._window,
            )
            response = JSONResponse(
                status_code=429,
                content={"detail": f"Muitas requisições. Tente novamente em {self._window}s."},
                headers={
                    "Retry-After": str(result["retry_after"]),
                    "X-RateLimit-Limit": str(self._max),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result["reset_at"]),
                },
            )
            await response(scope, receive, send)
            return

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                message["headers"] = self._merge_headers(
                    list(message.get("headers", [])),
                    response_headers,
                )
            await send(message)

        await self.app(scope, receive, send_wrapped)
