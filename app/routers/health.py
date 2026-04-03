import shutil
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.utils.config_utils import get_config
from app.utils.logger import get_logger

router = APIRouter(tags=["observability"])
logger = get_logger(__name__)

config = get_config()


@router.get("/health", summary="Liveness – o processo está vivo?")
async def health():
    """
    Retorna 200 enquanto o processo estiver rodando.
    Use para liveness probe no Docker / Kubernetes.
    """
    return {"status": "ok"}


@router.get("/ready", summary="Readiness – o serviço está pronto para receber tráfego?")
async def ready():
    """
    Verifica dependências críticas:
    - yt-dlp importável
    - FFmpeg presente
    - Espaço em disco suficiente (> 500 MB)
    - Cookies válidos (aviso, não erro)
    """
    checks: dict[str, str] = {}
    ok = True

    # yt-dlp
    try:
        import yt_dlp  # noqa: F401
        checks["yt_dlp"] = "ok"
    except ImportError:
        checks["yt_dlp"] = "missing"
        ok = False

    # FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        checks["ffmpeg"] = "ok"
    else:
        checks["ffmpeg"] = "missing"
        ok = False

    # Espaço em disco
    tmp = Path("/tmp")
    try:
        usage = shutil.disk_usage(tmp)
        free_mb = usage.free // (1024 * 1024)
        checks["disk_free_mb"] = str(free_mb)
        if free_mb < 500:
            checks["disk"] = "low"
            ok = False
        else:
            checks["disk"] = "ok"
    except Exception as exc:
        checks["disk"] = f"error: {exc}"
        ok = False

    # Cookies (aviso apenas)
    if config.has_valid_cookie_file():
        checks["cookies"] = "ok"
    else:
        checks["cookies"] = "warn: sem cookies válidos"
        logger.warning('"Readiness: cookies inválidos ou ausentes"')

    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if ok else "degraded", "checks": checks},
    )


@router.post("/admin/reload-cookies", include_in_schema=False)
async def reload_cookies():
    config.invalidate_cookie_cache()
    cookie_file = config.cookie_file
    return {
        "cookie_file": str(cookie_file) if cookie_file else "",
        "valid": config.has_valid_cookie_file(),
        "source": config.describe_cookie_source(),
    }
