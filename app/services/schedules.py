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


def split_spider(value: str | None) -> tuple[str | None, str]:
    """'ananinja-hungerstation-crawl -a hour=8:00' -> (spider, '-a hour=8:00').

    The scheduler's start_crawl runs os.system(f"scrapy crawl {crawler_name}"),
    so args[0] is a command-line fragment, not a name: some schedules carry
    spider arguments after it. Everything that matches on spider name -- the
    Run allow-list, the running PID, "not scheduled" -- needs the first token.
    """
    if not value:
        return value, ""
    spider, _, args = value.strip().partition(" ")
    return spider, args.strip()


def list_schedules() -> list[dict]:
    if not settings.SCHEDULER_DB_URL or not settings.SCHEDULES_SQL:
        raise NotConfigured("set SCHEDULER_DB_URL and SCHEDULES_SQL in .env")
    with _engine().connect() as conn:
        rows = conn.execute(text(settings.SCHEDULES_SQL)).mappings().all()
    out = []
    for r in rows:
        row = dict(r)
        row["spider"], row["args"] = split_spider(row.get("spider"))
        out.append(row)
    return out
