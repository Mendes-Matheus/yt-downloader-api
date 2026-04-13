import sys
import logging
import re
from pathlib import Path

from app.utils.config_utils import get_config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers import video, audio, info, health
from app.middleware.auth import InternalTokenMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.utils.logger import get_logger

# ── Logging estruturado ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = get_logger(__name__)


class NormalizePathMiddleware:
    """Normaliza múltiplas barras no path antes do roteamento."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            raw_path = scope.get("path", "")
            if "//" in raw_path:
                new_path = re.sub(r"/{2,}", "/", raw_path)
                logger.info('"normalize_path":"%s -> %s"', raw_path, new_path)
                scope = dict(scope)
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("utf-8")

        await self.app(scope, receive, send)

# ── Config ────────────────────────────────────────────────────────────────────
config = get_config()

app = FastAPI(
    title="YouTube Downloader – Serviço dedicado",
    description="Executa yt-dlp, FFmpeg e cookies. Chamado pela Vercel via token interno.",
    version="2.0.0",
    # Desabilita docs em produção se TOKEN estiver definido
    docs_url="/docs" if not config.internal_token else None,
    redoc_url=None,
)

# ── CORS: apenas o domínio Vercel pode chamar ─────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Internal-Token"],
)

# ── Rate limit por IP (usa defaults definidos em app/middleware/rate_limit.py) ─
# app.add_middleware(RateLimitMiddleware)
# ── Rate limit por IP ─────────────────────────────────────────────────────────
app.add_middleware(RateLimitMiddleware, max_requests=1, window_seconds=3600)

# ── Autenticação token interno (protege /download/* e /info/*) ────────────────
app.add_middleware(InternalTokenMiddleware, token=config.internal_token)

# ── Normaliza paths com // (ex.: //download/audio) ────────────────────────────
# Adicionado por último para executar primeiro na cadeia de middlewares.
app.add_middleware(NormalizePathMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)   # /health e /ready — sem autenticação
app.include_router(video.router)    # /download/video
app.include_router(audio.router)    # /download/audio
app.include_router(info.router)     # /info/video

# Compatibilidade para clients que enviam path com barra dupla no início.
app.add_api_route(
    "//download/audio",
    audio.download_audio,
    methods=["POST"],
    include_in_schema=False,
)
app.add_api_route(
    "//download/video",
    video.download_video,
    methods=["POST"],
    include_in_schema=False,
)
app.add_api_route(
    "//info/video",
    info.obter_info_video,
    methods=["GET"],
    include_in_schema=False,
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error('"Unhandled exception: %s"', str(exc))
    return JSONResponse(status_code=500, content={"detail": "Erro interno no servidor"})


@app.on_event("startup")
async def startup_event():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise RuntimeError("yt-dlp não está instalado!")

    Path("/tmp/yt_downloader/videos").mkdir(parents=True, exist_ok=True)
    Path("/tmp/yt_downloader/audios").mkdir(parents=True, exist_ok=True)

    if not config.internal_token:
        logger.warning('"INTERNAL_API_TOKEN não definido — rotas protegidas estarão ABERTAS"')
    else:
        logger.info('"Serviço iniciado com token interno configurado"')

    logger.info('"Cookies válidos: %s"', config.has_valid_cookie_file())
    logger.info('"Fonte de cookies: %s"', config.describe_cookie_source())
    logger.info('"Origins permitidas: %s"', config.allowed_origins)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
