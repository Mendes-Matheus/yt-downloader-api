import hashlib
import mimetypes
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.models.download_models import DownloadRequest
from app.services.video_service import VideoService
from app.utils.logger import get_logger

router = APIRouter(prefix="/download", tags=["video"])
logger = get_logger(__name__)


@router.post("/video")
async def download_video(request_body: DownloadRequest, request: Request):
    """Baixa vídeo via yt-dlp e retorna o arquivo MP4."""
    url_hash = hashlib.sha256(request_body.url.encode()).hexdigest()[:12]
    logger.info(
        '"action":"download_video","url_hash":"%s","quality":"%s"',
        url_hash,
        request_body.qualidade,
    )

    try:
        service = VideoService()
        resultado = service.baixar_video_temp(
            url=request_body.url,
            qualidade=request_body.qualidade,
        )

        if resultado["status"] == "sucesso" and os.path.exists(resultado["filepath"]):
            logger.info(
                '"action":"download_video","url_hash":"%s","status":"ok","size_bytes":%d',
                url_hash,
                resultado["tamanho"],
            )
            return FileResponse(
                path=resultado["filepath"],
                filename=resultado["filename"],
                media_type=mimetypes.guess_type(resultado["filename"])[0] or "application/octet-stream",
            )

        raise Exception("Arquivo não encontrado após download")

    except Exception as exc:
        logger.error(
            '"action":"download_video","url_hash":"%s","error":"%s"', url_hash, str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc))
