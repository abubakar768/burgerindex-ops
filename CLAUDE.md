# burgerindex-ops — working rules

API + worker for burgerindex crawler ops. Read [README.md](README.md) first for
layout, endpoints and deploy; it is the source of truth for all three and this
file does not repeat them. [PRD.md](PRD.md) has the why. [tracker.md](tracker.md)
has what is in flight.

## Hard constraints

These are load-bearing. Breaking one causes damage that is not obvious in tests.

1. **The scheduler's database is read-only.** Access is through the `ops_ro`
   user in `SCHEDULER_DB_URL`. Never INSERT, UPDATE or DELETE, and never add a
   code path that could. Schedules are owned by `burgerindex-scheduler`.
2. **Never import from `crawlers` or `burgerindex-scheduler`.** Integration is
   by filesystem path, subprocess and read-only SQL only. A direct import
   couples deploys of three repos together.
3. **Auto-fix only touches `AUTOFIX_REPO`**, a separate clone. Never the
   production checkout — a crawl may be running out of it.
4. **`autofix.pipeline run` never pushes.** It leaves a local branch and a
   `report.json`. Only `approve` pushes and opens the MR, and only after a human
   clicks Approve.
5. **Restarting burgerindex-ops must not kill running crawls.** Both units in
   `deploy/` use `KillMode=process`. Keep it that way, and keep crawls started
   with `start_new_session=True` (see `monitor/trigger.py`).
6. **Run is allow-listed.** Only spiders from `app/services/spiders.py:discover`
   can be started, and never a second copy of one already running.
7. **Never run burgerindex-scheduler's beat or worker on a dev machine.** Its
   `start_crawl` is a plain `scrapy crawl` with every pipeline on, so each
   enabled schedule becomes a production write. Locally, schedules are synced
   into Postgres as rows only; see [docs/local-dev.md](docs/local-dev.md).
8. **Every mutating action is audited.** Stop, Run, autofix and Approve write to
   `AUDIT_LOG` with the operator's name. A new mutating endpoint must too.

## Conventions

- **Every endpoint lives under `/api`.** The root namespace belongs to the
  static dashboard (`/live/`, `/issues/`, `/schedules/`, `/fix/`). `/health` is
  the one exception and stays unauthenticated at the root.
- **Config comes from `.env` via `app/config.py` only.** New settings go on
  `Settings` and into `.env.example` with a comment saying what breaks without
  them. `monitor/` and `autofix/` read bare env names, which `config.py` sets.
- **Triage rules are deterministic.** `triage/rules.py` is cheap, explainable
  classification with no AI in it. AI enters only in `autofix/`, for categories
  marked `fixable`. Keep that split.
- **Classifications carry evidence.** Every `Classification` lists the stats it
  reasoned from, so a human can check the call.
- **`SCRAPY_BIN` is not this repo's `scrapy`.** It must be an interpreter with
  the crawlers' dependencies (selenium and friends). A bare `scrapy` resolves to
  the wrong venv and `scrapy list` / `scrapy crawl` fail on import.
- **The dashboard is committed as built output.** `web/out` is in git so a clone
  works immediately. Changing `web/src` means re-running `npm run build` and
  committing the result.
- **Comments explain why, not what.** The existing files document the trap that
  motivated the code (see the docstrings in `app/services/spiders.py` and
  `app/main.py`). Match that; do not add narration of obvious code.

## Platform

macOS is development only. `/api/crawlers` sees processes there, but log paths
and other users' env need Linux. Verify anything process-level on the VM.

## Checks

```bash
source venv/bin/activate && pytest -q
```

`python scripts/check_schedules.py` verifies `SCHEDULES_SQL` against the real
scheduler database.

<!-- switchboard: learned rules (edit freely) -->
## Learned rules
- Don't want to spend the money on it.
<!-- end switchboard -->
