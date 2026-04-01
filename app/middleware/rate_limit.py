import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Rotas que NÃO sofrem rate limiting
_EXEMPT_PREFIXES = ("/health", "/ready")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit simples em memória por IP.
    Padrão: 10 requisições por minuto por IP.

    Nota: em produção com múltiplos workers, use Redis para estado compartilhado.
    Para um único processo (Uvicorn single-worker ou Gunicorn), isso já é suficiente.
    """

    def __init__(self, app, max_requests: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        # { ip: [timestamp, ...] }
        self._store: dict[str, list[float]] = defaultdict(list)

    def _get_ip(self, request: Request) -> str:
        # Respeita X-Forwarded-For quando atrás de proxy (Vercel, Render, etc.)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in _EXEMPT_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        if self._is_exempt(request.url.path):
            return await call_next(request)

        ip = self._get_ip(request)
        now = time.time()
        window_start = now - self._window

        # Limpa timestamps fora da janela
        self._store[ip] = [t for t in self._store[ip] if t > window_start]

        if len(self._store[ip]) >= self._max:
            logger.warning('"Rate limit atingido ip=%s path=%s"', ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": f"Muitas requisições. Tente novamente em {self._window}s."},
                headers={"Retry-After": str(self._window)},
            )

        self._store[ip].append(now)
        return await call_next(request)
