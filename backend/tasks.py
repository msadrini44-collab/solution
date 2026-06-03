"""
Celery task definitions (optional, for scaling out detection).

The API runs scans via FastAPI ``BackgroundTasks`` out of the box, so no broker
is required for development. In production you can offload the pipeline to a
Celery worker backed by Redis (see ``docker-compose.yml``):

    celery -A backend.tasks.celery_app worker --loglevel=info

and dispatch with ``run_scan_task.delay(scan_id, file_path, filename)`` from the
API instead of ``BackgroundTasks``.
"""
from __future__ import annotations

from celery import Celery

from . import config

celery_app = Celery(
    "antideepfake",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
)
celery_app.conf.update(task_track_started=True, result_expires=3600)


@celery_app.task(name="run_scan")
def run_scan_task(scan_id: str, file_path: str, filename: str) -> dict:
    """Run the detection pipeline inside a Celery worker."""
    # Imported lazily so importing this module doesn't pull in heavy deps.
    from .main import _process_scan

    _process_scan(scan_id, file_path, filename)
    return {"scan_id": scan_id, "status": "done"}
