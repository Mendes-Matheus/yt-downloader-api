import hashlib

from fastapi import APIRouter, HTTPException, Request

from app.services.download_service import BaseDownloadService
from app.utils.logger import get_logger

router = APIRouter(prefix="/info", tags=["info"])
logger = get_logger(__name__)


@router.get("/video")
async def obter_info_video(url: str, request: Request):
    """Retorna metadados do vídeo sem fazer download."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    logger.info('"action":"info","url_hash":"%s"', url_hash)

    try:
        service = BaseDownloadService()
        info = service.obter_info_video(url)
        logger.info('"action":"info","url_hash":"%s","status":"ok"', url_hash)
        return {"status": "sucesso", "dados": info}
    except Exception as exc:
        logger.error('"action":"info","url_hash":"%s","error":"%s"', url_hash, str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
