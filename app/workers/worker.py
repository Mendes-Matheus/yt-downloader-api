from __future__ import annotations

from rq import Queue, Worker

from app.infrastructure.redis_client import get_sync_redis_client
from app.utils.config_utils import get_config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    config = get_config()
    redis_conn = get_sync_redis_client()
    if redis_conn is None:
        raise RuntimeError("Redis não configurado para o worker de background.")

    queue = Queue(name=config.audio_queue_name, connection=redis_conn)
    logger.info('"worker":"starting","queue":"%s"', config.audio_queue_name)
    worker = Worker([queue], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
