from __future__ import annotations
from celery import Celery
from api.config import settings

celery_app = Celery(
    "senda",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["api.tasks.render_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
