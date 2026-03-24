from __future__ import annotations
from celery import Celery
from api.config import settings

celery_app = Celery(
    "senda",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["api.tasks.render_task", "api.tasks.cleanup"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "reset-stale-procesando": {
            "task": "api.tasks.render_task.reset_stale_procesando",
            "schedule": 300.0,  # every 5 minutes
        },
        "cleanup-expired-sessions": {
            "task": "api.tasks.cleanup.cleanup_expired_sessions",
            "schedule": 21600.0,  # every 6 hours
        },
    },
)
