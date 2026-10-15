"""Read the scheduler's schedules with a read-only DB user.

SCHEDULES_SQL must return at least: spider, schedule, enabled.
Optional columns: last_run_at, client. See .env.example for examples.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text

from ..config import settings


class NotConfigured(Exception):
    pass


@lru_cache(maxsize=1)
def _engine():
    return create_engine(settings.SCHEDULER_DB_URL, pool_pre_ping=True, pool_size=2)


def list_schedules() -> list[dict]:
    if not settings.SCHEDULER_DB_URL or not settings.SCHEDULES_SQL:
        raise NotConfigured("set SCHEDULER_DB_URL and SCHEDULES_SQL in .env")
    with _engine().connect() as conn:
        rows = conn.execute(text(settings.SCHEDULES_SQL)).mappings().all()
    return [dict(r) for r in rows]
