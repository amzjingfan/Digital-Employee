"""Heartbeat worker that keeps active shadow runs auditable until day 14."""

from __future__ import annotations

import logging
import threading

from sqlmodel import Session

from app.config import get_settings
from app.db import engine, set_tenant_context
from app.tiktok.shadow import heartbeat_shadow_run

logger = logging.getLogger(__name__)
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def _loop(interval_seconds: float) -> None:
    while not _stop_event.is_set():
        try:
            settings = get_settings()
            tenant_ids = settings.tiktok_shadow_tenant_id_list
            if not tenant_ids:
                logger.warning("TikTok shadow heartbeat skipped: no tenant ids configured")
                if _stop_event.wait(max(5.0, interval_seconds)):
                    break
                continue
            with Session(engine) as db:
                for tenant_id in tenant_ids:
                    set_tenant_context(db, tenant_id)
                    heartbeat_shadow_run(db, tenant_id)
        except Exception:
            logger.exception("TikTok shadow heartbeat failed")
        if _stop_event.wait(max(5.0, interval_seconds)):
            break


def start_shadow_worker(*, interval_seconds: float | None = None) -> None:
    global _worker_thread
    settings = get_settings()
    if not settings.tiktok_shadow_enabled:
        return
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_loop,
        args=(interval_seconds or settings.tiktok_shadow_interval_seconds,),
        name="tiktok-shadow-heartbeat",
        daemon=True,
    )
    _worker_thread.start()


def stop_shadow_worker() -> None:
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)
