from __future__ import annotations

import hashlib
import math
import os
import time
import uuid
from pathlib import Path
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
_DEFAULT_ENVIRONMENT: Final[str] = "dev"
_IDENTIFIER_HASH_LENGTH: Final[int] = 16
_RATE_LIMIT_SCRIPT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "infrastructure" / "redis_rate_limit.lua"
)

try:
    LUA_RATE_LIMIT_SCRIPT: str | None = _RATE_LIMIT_SCRIPT_PATH.read_text(encoding="utf-8")
except OSError:
    LUA_RATE_LIMIT_SCRIPT = None


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
        window_seconds: int = 180,
        scope_prefix: str = "global",
        by_route: bool = False,
    ):
        self.app = app
        self._max = max_requests
        self._window = window_seconds
        self._window_ms = window_seconds * 1000
        self._scope_prefix = scope_prefix
        self._by_route = by_route
        self._environment = os.getenv("ENV", _DEFAULT_ENVIRONMENT).strip() or _DEFAULT_ENVIRONMENT
        self._redis = get_redis_client()
        self._redis_url = get_rate_limit_redis_url()
        self._logged_missing_redis_config = False
        self._logged_redis_failure = False
        self._logged_missing_script = False
        self._script_sha: str | None = None

    def _hash_identifier(self, identifier: str) -> str:
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:_IDENTIFIER_HASH_LENGTH]

    def _get_identifier(self, headers: Headers, scope) -> str:
        api_key = headers.get("X-API-Key")
        if api_key:
            return self._hash_identifier(f"api_key:{api_key.strip()}")

        forwarded = headers.get("X-Forwarded-For")
        if forwarded:
            return self._hash_identifier(f"ip:{forwarded.split(',')[0].strip()}")

        client = scope.get("client")
        if client and client[0]:
            return self._hash_identifier(f"ip:{client[0]}")

        return f"unknown:{uuid.uuid4().hex}"

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in _EXEMPT_PREFIXES)

    def _build_rate_key(self, identifier: str, path: str) -> str:
        scope_key = self._scope_prefix
        if self._by_route:
            normalized_path = path.strip("/") or "root"
            scope_key = f"{scope_key}:{normalized_path.replace('/', ':')}"
        return f"{self._environment}:{_RATE_LIMIT_NAMESPACE}:{scope_key}:{identifier}"

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
        if LUA_RATE_LIMIT_SCRIPT is None:
            raise RuntimeError(f"Rate limit Lua script unavailable at {_RATE_LIMIT_SCRIPT_PATH}")

        member = f"{now_ms}-{uuid.uuid4().hex}"

        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(LUA_RATE_LIMIT_SCRIPT)

        try:
            raw_result = await self._redis.evalsha(
                self._script_sha,
                1,
                key,
                now_ms,
                self._window_ms,
                self._max,
                member,
            )
        except Exception as exc:
            if "NOSCRIPT" not in str(exc).upper():
                raise

            self._script_sha = await self._redis.script_load(LUA_RATE_LIMIT_SCRIPT)
            raw_result = await self._redis.evalsha(
                self._script_sha,
                1,
                key,
                now_ms,
                self._window_ms,
                self._max,
                member,
            )

        allowed, remaining, oldest_score, retry_after = (int(value) for value in raw_result)
        reset_at = math.ceil((oldest_score + self._window_ms) / 1000)

        if not allowed:
            return {
                "allowed": False,
                "remaining": 0,
                "reset_at": reset_at,
                "retry_after": max(retry_after, 1),
            }

        return {
            "allowed": True,
            "remaining": max(remaining, 0),
            "reset_at": reset_at,
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
            if LUA_RATE_LIMIT_SCRIPT is None:
                if not self._logged_missing_script:
                    logger.warning(
                        '"rate_limit_disabled":"lua_script_unavailable","script_path":"%s"',
                        str(_RATE_LIMIT_SCRIPT_PATH),
                    )
                    self._logged_missing_script = True
            elif not self._redis_url:
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
