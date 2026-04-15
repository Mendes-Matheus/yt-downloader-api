from __future__ import annotations

import hashlib

from rq import get_current_job

from app.services.audio_service import AudioService
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _update_job_meta(**values) -> None:
    job = get_current_job()
    if job is None:
        return

    job.meta.update(values)
    job.save_meta()


def download_audio_job(url: str, qualidade_audio: str = "192") -> dict:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    logger.info(
        '"action":"audio_job_started","url_hash":"%s","quality":"%s"',
        url_hash,
        qualidade_audio,
    )
    _update_job_meta(stage="processing", progress=10, url_hash=url_hash)

    try:
        service = AudioService()
        resultado = service.baixar_audio_temp(
            url=url,
            qualidade_audio=qualidade_audio,
        )

        _update_job_meta(
            stage="finished",
            progress=100,
            filename=resultado["filename"],
            filepath=resultado["filepath"],
            titulo=resultado["titulo"],
            tamanho=resultado["tamanho"],
        )
        logger.info(
            '"action":"audio_job_finished","url_hash":"%s","status":"ok","size_bytes":%d',
            url_hash,
            resultado["tamanho"],
        )
        return resultado
    except Exception as exc:
        _update_job_meta(stage="failed", progress=100, error=str(exc))
        logger.error(
            '"action":"audio_job_finished","url_hash":"%s","status":"error","error":"%s"',
            url_hash,
            str(exc),
        )
        raise
