# burgerindex-ops — PRD

Status: written after the fact, from the code as it stands on 2026-10-20.
Sections marked **TBC** are my reading of intent, not something the repo states.
Correct them rather than trusting them.

## 1. Problem

Burgerindex runs a fleet of Scrapy crawlers on one VM, launched by
`burgerindex-scheduler` on a django-celery-beat schedule. When something goes
wrong there is no single place to look or act:

- Whether a crawl is running at all means SSH-ing to the VM and reading `ps`.
- Why a crawl failed means opening the dashboard's job list and reading raw
  Scrapy stats, per job, by eye.
- Stopping a runaway crawl, or re-running one that died, is a manual shell
  command — unlogged, and easy to get wrong (killing the wrong PID, starting a
  second copy of a spider that is already running).
- P0 crawlers (the Talabat set, see `P0_CRAWLERS`) can fail silently for hours
  because nothing watches them.
- Fixing a broken spider — a changed endpoint, a broken parser — is a developer
  task with a multi-hour turnaround.

## 2. Users

| User | Needs |
| --- | --- |
| Ops / on-call | See what is running and its health; stop a crawl; re-run a schedule; be told when a P0 breaks. **TBC: who this is day to day.** |
| Crawler developers | A classified failure list worst-first instead of raw stats; a first-pass diagnosis and diff for a broken spider. |
| Whoever reviews the MR | Enough evidence (root cause, diff, test crawl, sample items) to accept or reject a proposed fix quickly. |

## 3. Goals

1. **One screen for live state** — server health, every running crawl with RAM
   against its limit, source, heartbeat, P0 flag, and a live log tail.
2. **Safe intervention from the browser** — Stop (graceful / force / kill) and
   Run, with guards: Run refuses a spider that is not in the `scrapy list`
   allow-list or is already running.
3. **Accountability** — every Stop, Run, auto-fix and Approve lands in
   `AUDIT_LOG` with the operator's name.
4. **Failure triage without reading stats** — deterministic rules classify each
   failed job into one of the categories in `triage/rules.py`, each with a
   suggested action and a `fixable` flag, sorted worst-first.
5. **Proactive P0 alerting** — new P0 issues go to Slack once per
   (crawler, job, category), every 5 minutes.
6. **Assisted fixes, never automatic ones** — for `fixable` categories, an agent
   proposes a branch and a report; a human approves before anything is pushed.

## 4. Non-goals

- **Replacing the scheduler.** Schedules are read-only here. burgerindex-ops
  does not own, create or edit them.
- **Replacing the crawlers repo.** No code from either project is imported;
  integration is by path, process and read-only SQL only.
- **Merging or deploying fixes.** `approve` opens a GitLab MR and stops. Merge
  and deploy stay with the existing process.
- **Multi-machine orchestration.** One crawler VM is assumed throughout
  (`monitor/processes.py` reads local processes).
- **Historical metrics / BI.** The dashboard at `DASHBOARD_API` owns job
  history; burgerindex-ops reads from it and does not duplicate it.

## 5. Scope as built

| Capability | Where |
| --- | --- |
| Server health, process list, stop, log tail + SSE stream, start | `monitor/` |
| Failure classification, streaks, lost runs, P0 watch | `triage/` |
| Fix pipeline (diagnose → branch → test crawl → validate → report → MR) | `autofix/` |
| HTTP surface, bearer auth, audit log | `app/` |
| Live / Schedules / Issues / Fix screens | `web/` |
| Background autofix + P0 watch | `worker/` |
| Heartbeat, evidence, memory limits, log files for the crawlers repo | `crawlers_patch/` |

Full endpoint and screen list: [README.md](README.md).

## 6. Success criteria

**TBC — none of these are measured today; they are the targets the design implies.**

1. Diagnosing a failed crawl takes a glance at `/issues/` rather than reading
   raw Scrapy stats.
2. No crawler is stopped or started over SSH; every intervention is in
   `AUDIT_LOG` with a name.
3. A P0 failure is in Slack within 5 minutes of the job being marked failed.
4. Classification is right often enough to trust the sort order — the top of
   `/issues/` is genuinely the worst thing. Misclassification rate: **TBC**.
5. Auto-fix proposals are accepted often enough to be worth reviewing.
   Target acceptance rate: **TBC**.

## 7. Constraints

- The scheduler's database is accessed through a read-only user. Never write.
- Auto-fix edits a **separate clone** (`AUTOFIX_REPO`), never the production
  checkout a crawl may be running from.
- Restarting burgerindex-ops must never kill a running crawl — both systemd
  units use `KillMode=process`.
- `SCRAPY_BIN` must be an interpreter carrying the crawlers' own dependencies;
  the burgerindex-ops venv does not have them.
- Process details (log path, other users' env) only work on Linux. macOS is for
  development; verify process-level behaviour on the VM.

## 8. Open questions

- Who is on call, and is Slack the right channel for P0, or should it page?
- Should scheduler-launched runs be tagged `CRAWL_SOURCE=scheduler`? The README
  lists this as a possible later change to the scheduler.
- Is `/issues/` meant to become the single queue, replacing the dashboard's job
  list, or to sit alongside it?
- Does auto-fix stay developer-triggered, or should high-confidence categories
  propose fixes unprompted (still human-approved)?
