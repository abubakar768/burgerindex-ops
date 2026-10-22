"""Check SCHEDULES_SQL against the scheduler's database before trusting /schedules.

Answers the three things that can silently break the endpoint:

  1. Does the query run at all, and does it return the columns /schedules needs?
  2. Has django_celery_beat actually synced the code-defined CELERY_BEAT_SCHEDULE
     into its tables?  If beat has never run against this DB the tables are empty
     and a perfectly correct query still returns nothing.
  3. Does the query drop rows?  SCHEDULES_SQL inner-joins crontabschedule, so
     start_crawl tasks scheduled by interval/solar/clocked are invisible to it.

It also cross-checks the spiders it finds against the crawlers repo, because
POST /schedules/{spider}/run refuses any spider that isn't in that allow-list.

Read-only: runs SELECTs inside a rolled-back transaction.

    python scripts/check_schedules.py
    python scripts/check_schedules.py --db-url postgresql+psycopg://ops_ro:pw@host/burgerindex
    python scripts/check_schedules.py --sql "SELECT ..."
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.services.schedules import split_spider
from app.services.spiders import discover

REQUIRED = {"spider", "schedule", "enabled"}
BEAT_TASK = "scheduler.tasks.start_crawl"
PERIODIC = "django_celery_beat_periodictask"

ok_count = 0
fail_count = 0


def ok(msg: str) -> None:
    global ok_count
    ok_count += 1
    print(f"  ok    {msg}")


def warn(msg: str) -> None:
    print(f"  warn  {msg}")


def fail(msg: str) -> None:
    global fail_count
    fail_count += 1
    print(f"  FAIL  {msg}")


def section(title: str) -> None:
    print(f"\n{title}")


def redact(url: str) -> str:
    """Hide the password so this can be pasted into a ticket."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", default=settings.SCHEDULER_DB_URL, help="overrides SCHEDULER_DB_URL")
    ap.add_argument("--sql", default=settings.SCHEDULES_SQL, help="overrides SCHEDULES_SQL")
    ap.add_argument("--sample", type=int, default=5, help="rows to print (default 5)")
    args = ap.parse_args()

    if not args.db_url:
        print("SCHEDULER_DB_URL is not set. Put it in .env or pass --db-url.", file=sys.stderr)
        return 2
    if not args.sql:
        print("SCHEDULES_SQL is not set. Put it in .env or pass --sql.", file=sys.stderr)
        return 2

    print(f"database  {redact(args.db_url)}")

    engine = create_engine(args.db_url, pool_pre_ping=True, pool_size=1)

    section("1. Connection")
    try:
        with engine.connect() as conn:
            try:
                who = conn.execute(text("SELECT current_user, current_database()")).first()
                ok(f"connected as {who[0]} to {who[1]}")
            except SQLAlchemyError:
                # Not PostgreSQL; the connection itself is what matters here.
                conn.rollback()
                conn.execute(text("SELECT 1"))
                ok("connected")
    except SQLAlchemyError as exc:
        fail(f"cannot connect: {exc.__class__.__name__}: {exc}")
        return 1

    section("2. Beat tables")
    tables = set(inspect(engine).get_table_names())
    if PERIODIC not in tables:
        fail(f"{PERIODIC} is missing -- django_celery_beat has never migrated here")
        return 1
    ok(f"{PERIODIC} exists")

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM {PERIODIC}")).scalar_one()
        crawls = conn.execute(
            text(f"SELECT count(*) FROM {PERIODIC} WHERE task = :t"), {"t": BEAT_TASK}
        ).scalar_one()
        by_kind = conn.execute(
            text(
                f"SELECT count(*) FILTER (WHERE crontab_id IS NOT NULL) AS crontab,"
                f"       count(*) FILTER (WHERE interval_id IS NOT NULL) AS interval,"
                f"       count(*) FILTER (WHERE crontab_id IS NULL AND interval_id IS NULL) AS other"
                f" FROM {PERIODIC} WHERE task = :t"
            ),
            {"t": BEAT_TASK},
        ).mappings().one()

    if total == 0:
        fail("periodic task table is empty -- beat has not synced CELERY_BEAT_SCHEDULE yet")
        print("        Start celery beat against this DB once, then re-run this check.")
        return 1
    ok(f"{total} periodic tasks, {crawls} of them {BEAT_TASK}")
    if crawls == 0:
        fail(f"no {BEAT_TASK} rows -- is this the right database?")

    section("3. Query")
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            rows = conn.execute(text(args.sql)).mappings().all()
            trans.rollback()
    except SQLAlchemyError as exc:
        fail(f"query failed: {exc.__class__.__name__}: {exc}")
        return 1
    ok(f"query ran, {len(rows)} rows")

    if not rows:
        fail("query returned no rows -- /schedules would render empty")
        return 1

    cols = set(rows[0].keys())
    missing = REQUIRED - cols
    if missing:
        fail(f"missing required columns: {', '.join(sorted(missing))}")
    else:
        ok(f"columns present: {', '.join(sorted(cols))}")

    null_spiders = sum(1 for r in rows if not r.get("spider"))
    if null_spiders:
        fail(f"{null_spiders} rows have a null/empty spider -- wrong args/kwargs expression?")
    else:
        ok("every row has a spider name")

    section("4. Coverage")
    if by_kind["crontab"] != crawls:
        warn(
            f"{by_kind['interval']} interval + {by_kind['other']} other-schedule {BEAT_TASK} rows "
            f"are dropped by the crontab join"
        )
    else:
        ok("every start_crawl task uses a crontab schedule")

    if len(rows) < crawls:
        warn(f"query returns {len(rows)} of {crawls} start_crawl tasks ({crawls - len(rows)} missing)")
    else:
        ok(f"query covers all {crawls} start_crawl tasks")

    section("5. Spider allow-list")
    known = discover()
    names = {split_spider(r["spider"])[0] for r in rows if r.get("spider")}
    unknown = sorted(n for n in names if n not in known)
    ok(f"{len(known)} spiders discovered in {settings.CRAWLERS_DIR}")
    if unknown:
        warn(f"{len(unknown)} scheduled spiders are not in the crawlers repo; Run will refuse them:")
        for name in unknown[:10]:
            print(f"          {name}")
        if len(unknown) > 10:
            print(f"          ... and {len(unknown) - 10} more")
    else:
        ok("every scheduled spider exists in the crawlers repo")

    section(f"Sample ({min(args.sample, len(rows))} of {len(rows)})")
    for row in rows[: args.sample]:
        print(f"  {dict(row)}")

    print(f"\n{ok_count} ok, {fail_count} failed")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
