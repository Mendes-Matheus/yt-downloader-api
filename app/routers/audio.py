import hashlib
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.models.download_models import AudioRequest
from app.services.audio_service import AudioService
from app.utils.logger import get_logger

router = APIRouter(prefix="/download", tags=["audio"])
logger = get_logger(__name__)


@router.post("/audio")
async def download_audio(request_body: AudioRequest, request: Request):
    """Baixa áudio via yt-dlp+FFmpeg e retorna o arquivo MP3."""
    url_hash = hashlib.sha256(request_body.url.encode()).hexdigest()[:12]
    logger.info(
        '"action":"download_audio","url_hash":"%s","quality":"%s"',
        url_hash,
        request_body.qualidade_audio,
    )

    try:
        service = AudioService()
        resultado = service.baixar_audio_temp(
            url=request_body.url,
            qualidade_audio=request_body.qualidade_audio,
        )

        if resultado["status"] == "sucesso" and os.path.exists(resultado["filepath"]):
            logger.info(
                '"action":"download_audio","url_hash":"%s","status":"ok","size_bytes":%d',
                url_hash,
                resultado["tamanho"],
            )
            return FileResponse(
                path=resultado["filepath"],
                filename=resultado["filename"],
                media_type="audio/mpeg",
            )

        raise Exception("Arquivo não encontrado após download")

    except Exception as exc:
        logger.error(
            '"action":"download_audio","url_hash":"%s","error":"%s"', url_hash, str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc))
