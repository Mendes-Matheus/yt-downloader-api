import hashlib
import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from starlette import status

from app.infrastructure.redis_client import get_sync_redis_client
from app.jobs.download import download_audio_job
from app.models.download_models import (
    AudioEnqueueResponse,
    AudioRequest,
    AudioStatusResponse,
)
from app.utils.config_utils import get_config
from app.utils.logger import get_logger

router = APIRouter(prefix="/download", tags=["audio"])
logger = get_logger(__name__)
config = get_config()


def _get_audio_queue() -> Queue:
    redis_conn = get_sync_redis_client()
    if redis_conn is None:
        raise RuntimeError("Redis não configurado para fila de downloads.")
    return Queue(name=config.audio_queue_name, connection=redis_conn)


def _fetch_job(task_id: str) -> Job:
    queue = _get_audio_queue()
    return Job.fetch(task_id, connection=queue.connection)


def _build_status_payload(task_id: str, job: Job) -> AudioStatusResponse:
    job_status = job.get_status(refresh=True)
    meta = job.meta or {}
    result = job.result if isinstance(job.result, dict) else {}
    is_finished = job_status == "finished"
    is_failed = job_status == "failed"

    return AudioStatusResponse(
        task_id=task_id,
        status=job_status,
        stage=str(meta.get("stage") or job_status),
        ready=is_finished,
        error=str(meta.get("error") or job.exc_info or "") if is_failed else None,
        filename=result.get("filename") or meta.get("filename"),
        titulo=result.get("titulo") or meta.get("titulo"),
        tamanho=result.get("tamanho") or meta.get("tamanho"),
    )


@router.post("/audio", status_code=status.HTTP_202_ACCEPTED, response_model=AudioEnqueueResponse)
async def download_audio(request_body: AudioRequest):
    """Enfileira o download de áudio e responde com um task_id."""
    url_hash = hashlib.sha256(request_body.url.encode()).hexdigest()[:12]
    logger.info(
        '"action":"enqueue_audio","url_hash":"%s","quality":"%s"',
        url_hash,
        request_body.qualidade_audio,
    )

    try:
        task_id = uuid4().hex
        queue = await run_in_threadpool(_get_audio_queue)
        await run_in_threadpool(
            queue.enqueue,
            download_audio_job,
            request_body.url,
            request_body.qualidade_audio,
            job_id=task_id,
            job_timeout=config.audio_job_timeout_seconds,
            result_ttl=config.audio_result_ttl_seconds,
            failure_ttl=config.audio_failure_ttl_seconds,
            meta={"stage": "queued", "progress": 0, "url_hash": url_hash},
        )
        logger.info(
            '"action":"enqueue_audio","url_hash":"%s","status":"accepted","task_id":"%s"',
            url_hash,
            task_id,
        )
        return AudioEnqueueResponse(
            task_id=task_id,
            status="queued",
            status_url=f"/download/audio/status/{task_id}",
            download_url=f"/download/audio/file/{task_id}",
        )

    except Exception as exc:
        logger.error(
            '"action":"enqueue_audio","url_hash":"%s","error":"%s"', url_hash, str(exc)
        )
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/audio/status/{task_id}", response_model=AudioStatusResponse)
async def get_audio_status(task_id: str):
    try:
        job = await run_in_threadpool(_fetch_job, task_id)
        return await run_in_threadpool(_build_status_payload, task_id, job)
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    except Exception as exc:
        logger.error(
            '"action":"audio_status","task_id":"%s","error":"%s"',
            task_id,
            str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/audio/file/{task_id}")
async def download_audio_file(task_id: str):
    try:
        job = await run_in_threadpool(_fetch_job, task_id)
        payload = await run_in_threadpool(_build_status_payload, task_id, job)
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    except Exception as exc:
        logger.error(
            '"action":"audio_file","task_id":"%s","error":"%s"',
            task_id,
            str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))

    if payload.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Download ainda não finalizado",
        )

    result = job.result if isinstance(job.result, dict) else {}
    filepath = result.get("filepath") or job.meta.get("filepath")
    filename = result.get("filename") or job.meta.get("filename")

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo final não está mais disponível")

    return FileResponse(
        path=filepath,
        filename=filename or os.path.basename(filepath),
        media_type="audio/mpeg",
    )
