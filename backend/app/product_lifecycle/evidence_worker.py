"""Background expiry sweep for the independent creative evidence registry."""

from __future__ import annotations

import logging
import threading

from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import engine
from app.product_lifecycle.service import expire_creative_evidence_records

logger = logging.getLogger(__name__)
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def run_evidence_expiry_worker(
    *, once: bool = False, settings: Settings | None = None
) -> None:
    settings = settings or get_settings()
    while not _stop_event.is_set():
        try:
            with Session(engine) as db:
                expired = expire_creative_evidence_records(db)
            if expired:
                logger.info("Creative evidence expiry sweep updated %d records", expired)
        except Exception:
            # One failed sweep must not kill the process or hide the next retry.
            logger.exception("Creative evidence expiry sweep failed")
        if once or _stop_event.wait(max(5.0, settings.creative_evidence_sync_interval_seconds)):
            return


def start_creative_evidence_worker(*, settings: Settings | None = None) -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=run_evidence_expiry_worker,
        kwargs={"settings": settings},
        name="creative-evidence-expiry-sweep",
        daemon=True,
    )
    _worker_thread.start()


def stop_creative_evidence_worker(timeout_seconds: float = 2.0) -> None:
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=timeout_seconds)


__all__ = [
    "run_evidence_expiry_worker",
    "start_creative_evidence_worker",
    "stop_creative_evidence_worker",
]
