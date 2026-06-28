"""Background SQS result consumer loop."""
from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings
from app.services.result_consumer import poll_once

logger = logging.getLogger("datasentinel.result_worker")
_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop():
    while not _stop.is_set():
        try:
            poll_once()
        except Exception:
            logger.exception("Result worker poll failed")
        time.sleep(2)


def start_result_worker():
    global _thread
    if settings.DQA_EXECUTION_MODE != "sqs" and not settings.SQS_DQA_COMPLETED_URL:
        logger.info("Result worker not started (SQS not configured)")
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="result-worker", daemon=True)
    _thread.start()
    logger.info("Result worker started")


def stop_result_worker():
    _stop.set()
