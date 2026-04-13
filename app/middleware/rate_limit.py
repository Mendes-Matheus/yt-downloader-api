import time
from collections import defaultdict
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Rotas que NÃO sofrem rate limiting
_EXEMPT_PREFIXES = ("/health", "/ready")


class RateLimitMiddleware:
    """
    Rate limit simples em memória por IP.
    Padrão: 3 requisições por hora (3600s) por IP.

    Nota: em produção com múltiplos workers, use Redis para estado compartilhado.
    Para um único processo (Uvicorn single-worker ou Gunicorn), isso já é suficiente.
    """

    def __init__(self, app, max_requests: int = 1, window_seconds: int = 3600):
        self.app = app
        self._max = max_requests
        self._window = window_seconds
        # { ip: [timestamp, ...] }
        self._store: dict[str, list[float]] = defaultdict(list)

    def _get_ip(self, headers: Headers, scope) -> str:
        # Respeita X-Forwarded-For quando atrás de proxy (Vercel, Render, etc.)
        forwarded = headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in _EXEMPT_PREFIXES)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if self._is_exempt(path):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        ip = self._get_ip(headers, scope)
        now = time.time()
        window_start = now - self._window

        # Limpa timestamps fora da janela
        self._store[ip] = [t for t in self._store[ip] if t > window_start]

        if len(self._store[ip]) >= self._max:
            logger.warning('"Rate limit atingido ip=%s path=%s"', ip, path)
            response = JSONResponse(
                status_code=429,
                content={"detail": f"Muitas requisições. Tente novamente em {self._window}s."},
                headers={"Retry-After": str(self._window)},
            )
            await response(scope, receive, send)
            return

        self._store[ip].append(now)
        await self.app(scope, receive, send)
