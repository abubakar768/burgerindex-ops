# Running the whole stack on a Mac

Everything the VM runs, on your laptop, against the real crawlers repo and the
real scheduler schedules, without anything reaching production. Use this to
check a change end to end before it goes to the VM.

## What runs where

| Piece | Locally | What keeps it away from production |
|---|---|---|
| API + dashboard | `uvicorn` on :8090 | reads `.env.local` (`OPS_ENV_FILE`) |
| Worker (autofix, P0 watch) | `celery`, `--pool=threads` | Redis db 3; Slack and GitLab left empty |
| Schedules | your local Postgres `burgerindex`, filled from the scheduler's own code | read through `ops_ro`, which can only `SELECT` |
| Crawls (Run, autofix test crawls) | `crawlers-ops-test` worktree, via `scripts/local/scrapy-safe.sh` | pipelines, stats and Spidermon off; 90 s, 1 request / 3 s |
| Autofix branches | a clone of a bare mirror of your crawlers history | Approve's push lands in the mirror; Approve refuses anyway without GitLab settings |

Local state lives in `~/.burgerindex-ops-local/` (logs, heartbeats, audit log,
P0 state, autofix mirror and work dirs). Not `/tmp`: macOS empties that on
reboot.

**Never run the scheduler's own beat or worker locally.** Its `start_crawl` task
is `os.system(f"scrapy crawl {name}")` in the crawlers checkout with every
pipeline on, and 408 schedules are enabled. Syncing the schedules (step 2) only
writes rows; nothing ticks and nothing is sent.

## One-time setup

Paths assume the three repos sit side by side in
`~/Desktop/burgerindex_projects`.

### 1. Redis

```bash
brew install redis
```

```bash
brew services start redis
```

### 2. Sync the schedules into local Postgres

This runs the scheduler's code, in the scheduler's venv, to do what beat does at
startup: write `CELERY_BEAT_SCHEDULE` into `django_celery_beat_periodictask`.

```bash
cd ~/Desktop/burgerindex_projects/burgerindex-scheduler/burgerindexScheduler && venv/bin/python manage.py shell -c "
import sys, kombu.utils.encoding
sys.modules['celery.utils.encoding'] = kombu.utils.encoding
from scheduler.celery import app
from django_celery_beat.schedulers import DatabaseScheduler
from django_celery_beat.models import PeriodicTask
try:
    DatabaseScheduler(app=app)
except AttributeError:
    pass
print(PeriodicTask.objects.filter(task='scheduler.tasks.start_crawl').count(), 'crawl schedules')
"
```

Two workarounds are in there because the scheduler's `requirements.txt` pins
`django-celery-beat==2.0.0` next to `celery==5.4.0`, which do not work together:

- 2.0.0 imports `celery.utils.encoding`, which Celery 5 removed; kombu has the
  same two functions, so the module is aliased for this one command.
- After writing the rows, beat builds its in-memory schedule and fails on a
  `ZoneInfo` timezone (2.0.0 expects pytz). The rows are already written by
  then, so that error is caught and ignored.

Expect `408 crawl schedules` (as of scheduler `1893bed`). Re-run it after the
scheduler's schedule code changes. It adds and updates rows but never deletes
one; for an exact copy, empty the table first:

```bash
psql -h 127.0.0.1 -U postgres -d burgerindex -c "DELETE FROM django_celery_beat_periodictask"
```

Production's admin can hold schedules edited by hand that are not in the code.
If the local count differs from what the
[scheduler admin](http://burgerindex.arbisoft.com:8089/admin/django_celery_beat/periodictask/)
shows, that is why.

### 3. A read-only user, like the VM's

```bash
psql -h 127.0.0.1 -U postgres -d burgerindex
```

```sql
CREATE ROLE ops_ro LOGIN PASSWORD 'pick-one';
GRANT CONNECT ON DATABASE burgerindex TO ops_ro;
GRANT USAGE ON SCHEMA public TO ops_ro;
GRANT SELECT ON django_celery_beat_periodictask, django_celery_beat_crontabschedule TO ops_ro;
```

### 4. A crawlers worktree to crawl from

Run and autofix never touch your crawlers checkout; crawls run from a worktree
on its own branch.

```bash
cd ~/Desktop/burgerindex_projects/crawlers && git worktree add -b ops-heartbeat-test ../crawlers-ops-test master
```

For Live's heartbeat column, add the extension on that branch as
[crawlers_patch/README.md](../crawlers_patch/README.md) describes and commit it
there (locally; it is not pushed). Without it Live still lists the crawl, with
no items or heartbeat.

A worktree has no `burgerindex/.env` (it is untracked), so spiders that need
`GOOGLE_MAPS_API_KEY`, the Zyte smart-proxy keys or `SHOPEE_MY_COOKIES` fail
there. Spiders without those work.

### 5. The autofix repo

A bare mirror of your crawlers history, and a clone of it. Autofix fetches from
and pushes to the mirror, never GitLab. Local clones hardlink objects, so this
costs almost no disk.

```bash
mkdir -p ~/.burgerindex-ops-local/{logs,hb,state,autofix-work} && cd ~/.burgerindex-ops-local
```

```bash
git clone --bare ~/Desktop/burgerindex_projects/crawlers crawlers-origin.git && git -C crawlers-origin.git symbolic-ref HEAD refs/heads/master
```

```bash
git clone --no-checkout crawlers-origin.git crawlers-autofix
```

To pick up newer crawlers commits later:
`git -C ~/.burgerindex-ops-local/crawlers-origin.git fetch ~/Desktop/burgerindex_projects/crawlers master:master`.

### 6. `.env.local`

In the burgerindex-ops checkout, gitignored. Replace `YOU` and the two
placeholders.

```ini
API_TOKEN=any-local-string
CRAWLERS_DIR=/Users/YOU/Desktop/burgerindex_projects/crawlers-ops-test
SCHEDULER_DIR=/Users/YOU/Desktop/burgerindex_projects/burgerindex-scheduler
SCRAPY_BIN=/Users/YOU/Desktop/burgerindex_projects/burgerindex-ops/scripts/local/scrapy-safe.sh
SCHEDULER_DB_URL=postgresql+psycopg://ops_ro:pick-one@127.0.0.1:5432/burgerindex
# copy SCHEDULES_SQL from .env.example
SCHEDULES_SQL=...
MEMUSAGE_LIMIT_MB=0
CRAWLER_LOG_DIR=/Users/YOU/.burgerindex-ops-local/logs
HEARTBEAT_DIR=/Users/YOU/.burgerindex-ops-local/hb
AUDIT_LOG=/Users/YOU/.burgerindex-ops-local/audit.jsonl
P0_WATCH_STATE=/Users/YOU/.burgerindex-ops-local/state/p0_watch.json
DASHBOARD_API=https://data-ingest-dashboard.replit.app
P0_CRAWLERS=talabat-app-deliveroo-1-crawl,talabat-app-deliveroo-2-crawl,talabat-app-deliveroo-3-crawl,talabat-app-mart-uae-crawl
SLACK_WEBHOOK_URL=
REDIS_URL=redis://localhost:6379/3
AUTOFIX_REPO=/Users/YOU/.burgerindex-ops-local/crawlers-autofix
AUTOFIX_WORK=/Users/YOU/.burgerindex-ops-local/autofix-work
GITLAB_PROJECT_ID=
GITLAB_TOKEN=
GITLAB_TARGET=master
```

Check it:

```bash
OPS_ENV_FILE=.env.local venv/bin/python scripts/check_schedules.py
```

## Every time

```bash
scripts/local/up.sh
```

Open http://localhost:8090/ and sign in with `API_TOKEN` and your name.
Ctrl-C stops the API and the worker; crawls you started keep going until their
90 s limit or until you Stop them.

| Try | Where | Expect |
|---|---|---|
| Schedules | `/schedules/` | 408 rows; `Not scheduled` lists the other runnable spiders |
| Run | Run on any row → Run now | 409 if already running; row turns Running |
| Live + Stop | `/live/` | items, requests, heartbeat every 5 s, log tail; Stop sends SIGTERM |
| Issues | `/issues/` | the real dashboard's failures, classified |
| Fix, not fixable | Fix on a `network`/`lost` row | "Not a code fix" within seconds |
| Fix, fixable | Fix on a `parse_broken` row | **runs Claude on your account**, up to 3 attempts, plus test crawls; ends in a diff to review |
| Approve | on a ready fix | refuses: GitLab is not configured, nothing is pushed |
| P0 watch | worker log every 5 min | `N open P0 issues, 0 new alerts`; nothing posted |

Audit entries go to `~/.burgerindex-ops-local/audit.jsonl`.

## When something looks wrong

- **The first page load takes 10–30 s.** That is `scrapy list` building the
  allow-list. The crawlers fetch exchange rates when imported
  (`utils/currency_converter.py`, no timeout); when that host is slow
  `scrapy list` fails and the API falls back to a source scan that misses
  composed names. It retries after 5 minutes; until then "Not in crawlers
  repo" is not shown, because it cannot be told apart from "not scanned".
- **Schedules says not configured (501).** `SCHEDULER_DB_URL` or
  `SCHEDULES_SQL` is empty in `.env.local`, or you started uvicorn without
  `OPS_ENV_FILE=.env.local`.
- **Worker tasks fail with `not enough values to unpack`.** The worker was
  started without `--pool=threads`; use `up.sh`.

## Stopping everything

```bash
brew services stop redis
```

Remove `~/.burgerindex-ops-local` and the `crawlers-ops-test` worktree
(`git -C ~/Desktop/burgerindex_projects/crawlers worktree remove ../crawlers-ops-test`)
to undo the setup.
