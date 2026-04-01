import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Rotas que NÃO precisam de token (health checks)
_PUBLIC_PREFIXES = ("/health", "/ready", "/docs", "/openapi.json")


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """
    Bloqueia qualquer rota que não seja pública caso o header
    X-Internal-Token esteja ausente ou incorreto.

    Se INTERNAL_API_TOKEN não estiver configurado no ambiente, o middleware
    loga um aviso mas deixa passar (útil em dev local).
    """

    def __init__(self, app, token: str | None = None):
        super().__init__(app)
        self._token = token or os.getenv("INTERNAL_API_TOKEN", "")

    def _is_public(self, path: str) -> bool:
        return any(path.startswith(p) for p in _PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        if self._is_public(request.url.path):
            return await call_next(request)

        if not self._token:
            # Token não configurado → ambiente de desenvolvimento, deixa passar
            return await call_next(request)

        header_token = request.headers.get("X-Internal-Token", "")
        if header_token != self._token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token interno inválido ou ausente"},
            )

        return await call_next(request)
