import os
from celery import Celery

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "resume_engine",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Acknowledge task only after it completes — if worker crashes mid-task,
    # the job goes back to the queue instead of being lost.
    task_acks_late=True,
    # Each worker takes one task at a time (no prefetching ahead).
    # Prevents a slow Gemini call from blocking other workers.
    worker_prefetch_multiplier=1,
    # Show "started" status in result backend
    task_track_started=True,
)
