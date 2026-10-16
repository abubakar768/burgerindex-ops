# burgerindex-ops

API + worker for the Crawler Operations Dashboard: live crawlers, server health, logs,
Stop / Run buttons, schedules, triage, P0 alerts and auto-fix.

## How it uses the other two projects

| Project | How burgerindex-ops uses it | Changes needed there |
| --- | --- | --- |
| `crawlers` | Finds spiders (allow-list for Run), runs `scrapy crawl` in it, auto-fix edits a **separate clone** of it | PR: heartbeat + evidence extensions, memory limits, log files (`crawlers_patch/`) |
| `burgerindex-scheduler` | Reads schedules through a **read-only DB user** (`SCHEDULES_SQL`) | None now. Later: tag launches with `CRAWL_SOURCE=scheduler` |

burgerindex-ops never imports code from either project.

## Layout

```
app/            FastAPI: config, auth, routers, services
web/            Next.js dashboard, built to static files the API serves
monitor/        processes, server health, stop, logs, start_crawl
triage/         failure rules, streaks, lost runs, P0 watch (served as /issues)
autofix/        Claude Code fix pipeline + validation
worker/         Celery: autofix + P0 watch (queue: burgerindex-ops)
crawlers_patch/ files + settings for the crawlers repo PR
deploy/         systemd units for the VM
tests/          26 tests (API run/stop/logs cycle, rules, dashboard mount)
```

## Local (Mac)

```bash
cd ~/Desktop/burgerindex_projects
git init burgerindex-ops   # or unzip here, next to crawlers/ and burgerindex-scheduler/
cd burgerindex-ops
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paths already point at your two folders; set API_TOKEN
uvicorn app.main:app --reload --port 8090
# http://localhost:8090/       the dashboard (sign in with API_TOKEN + your name)
# http://localhost:8090/docs   the API (click Authorize, paste API_TOKEN)
curl -H "Authorization: Bearer $API_TOKEN" localhost:8090/spiders
```

The dashboard is served from `web/out`, which is committed, so it works straight
after a clone. Changing anything under `web/src` means rebuilding it:

```bash
cd web && npm install && npm run build   # needs Node 18+, on your Mac only
```
On macOS, `/crawlers` sees processes but some details (log path, other users' env) need Linux.
Test those on the VM.

## VM (burgerindex-vm)

```bash
cd /home/arslan/arslan/projects
git clone <burgerindex-ops repo> burgerindex-ops
git clone git@gitlab.com:b1119/crawlers.git crawlers-autofix   # for auto-fix only
cd burgerindex-ops && python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env    # switch to the VM paths, set tokens and SCHEDULES_SQL
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now burgerindex-ops-api burgerindex-ops-worker
```
Both units use `KillMode=process`, so restarting burgerindex-ops never kills running crawls.

## Endpoints (all need `Authorization: Bearer <API_TOKEN>`)

| Method | Path | Does |
| --- | --- | --- |
| GET | `/server` | memory, swap, load, disk |
| GET | `/crawlers?source=` | running crawls: PID, RAM, source, env, heartbeat, P0 |
| GET | `/crawlers/{pid}/logs?lines=200` | log tail |
| GET | `/crawlers/{pid}/logs/stream` | live log (server-sent events) |
| POST | `/crawlers/{pid}/stop` | `{spider, mode: graceful/force/kill, user}` |
| GET | `/spiders` | spiders found in the crawlers repo |
| GET | `/schedules` | scheduler's schedules + running PID |
| POST | `/schedules/{spider}/run` | `{user}`; refuses unknown or already running spiders |
| GET | `/issues?days=7` | classified failures, worst first (`/triage` still works, deprecated) |
| POST | `/autofix` | `{job_id, user}` queues a fix |
| GET | `/autofix/{task_id}` | fix status + report |
| POST | `/autofix/approve` | `{report_path, user}` opens the GitLab MR |

Stop, Run, auto-fix and Approve are written to `AUDIT_LOG`.

## Dashboard

| Path | Screen |
| --- | --- |
| `/` | redirects to the live crawlers page |
| `/ui/live/` | server health, running crawls, live log, Stop / Force stop / Kill |
| `/ui/schedules/` | the scheduler's schedules, next run, Run button |
| `/ui/issues/` | classified failures, worst first, Fix button |
| `/ui/fix/?task=` | the agent's diagnosis, diff, test crawl, Approve |

It is served under `/ui` because the API already owns `/triage` and
`/schedules` at the root. Sign in with `API_TOKEN` and your name; the name is
what lands in `AUDIT_LOG`. See `web/README.md`.

## First steps
1. Run locally, check `/spiders` lists your real spiders.
2. Look at the scheduler's models, write `SCHEDULES_SQL`, check `/schedules`.
3. Deploy on the VM, check `/crawlers` shows today's runs and `/` opens the dashboard.
4. Open the crawlers repo PR from `crawlers_patch/`.
