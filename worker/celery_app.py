"""Celery worker for long jobs.  Run: celery -A worker.celery_app worker -B -Q burgerindex-ops -c 2"""
import os
import sys

# `celery -A worker.celery_app` puts the cwd on sys.path only while it imports
# this module (celery.utils.imports.cwd_in_path) and takes it off again after.
# A top-level package first imported later is then not found: autofix imports
# app.services.spiders lazily, which imports monitor/, and every autofix task
# failed with "No module named 'monitor'". So add the repo root ourselves --
# unconditionally: during that import it is already there (celery's copy, at
# the front), and celery's remove() takes the first match, leaving ours.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery  # noqa: E402

from app.config import settings  # noqa: E402

app = Celery("burgerindex_ops", broker=settings.REDIS_URL, backend=settings.REDIS_URL,
             include=["worker.tasks"])
app.conf.update(
    task_default_queue="burgerindex-ops",          # own queue: never competes with scheduler tasks
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=7 * 24 * 3600,
    beat_schedule={"p0-watch": {"task": "worker.tasks.p0_watch", "schedule": 300.0}},
)
