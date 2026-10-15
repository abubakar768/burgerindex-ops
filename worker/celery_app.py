"""Celery worker for long jobs.  Run: celery -A worker.celery_app worker -B -Q burgerindex-ops -c 2"""
from celery import Celery

from app.config import settings

app = Celery("burgerindex_ops", broker=settings.REDIS_URL, backend=settings.REDIS_URL,
             include=["worker.tasks"])
app.conf.update(
    task_default_queue="burgerindex-ops",          # own queue: never competes with scheduler tasks
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=7 * 24 * 3600,
    beat_schedule={"p0-watch": {"task": "worker.tasks.p0_watch", "schedule": 300.0}},
)
