# burgerindex-ops dashboard

The Crawler Operations Dashboard: live crawlers, schedules, triage and auto-fix
review. Next.js (App Router, TypeScript), compiled to **static files** that the
FastAPI app in `../app` serves. There is no Node runtime in production.

## Screens

| Route | Reads | Writes |
| --- | --- | --- |
| `/live/` | `GET /server`, `GET /crawlers`, `GET /crawlers/{pid}/logs` + `/logs/stream` | `POST /crawlers/{pid}/stop` |
| `/schedules/` | `GET /schedules`, `GET /issues` | `POST /schedules/{spider}/run` |
| `/issues/` | `GET /issues`, `GET /spiders` | `POST /autofix` |
| `/fix/?task=…` | `GET /api/autofix/{task_id}` | `POST /api/autofix/approve`, `POST /api/autofix` |

`/` redirects to `/live/`.

### Why `/ui` and not `/`

The API owns `/triage`, `/api/schedules`, `/api/crawlers`, `/api/spiders` and `/api/server` at
the root, and FastAPI matches those routes before any static mount. With the
pages at `/`, a bare `/api/issues` would return 401 JSON instead of the page. The
`basePath` in `next.config.mjs` and the mount in `app/main.py` must agree.

## Sign-in

The API has no login route: it checks `Authorization: Bearer <API_TOKEN>` on
every request. The first screen asks for

- **API token** — the `API_TOKEN` from the ops `.env`, kept in `localStorage`
  for this browser only,
- **your name** — sent as `user` on Stop, Run, autofix and Approve, which the
  backend writes to `AUDIT_LOG`,
- **API base URL** — empty means the API that served the page. Set it only when
  running `npm run dev` separately.

Anyone with the token has full control of the crawlers, so serve this over TLS
and treat the token as a shared password.

## Local development

Against the API that serves the built files (one process, no CORS):

```bash
cd web && npm run build          # writes web/out
cd .. && venv/bin/uvicorn app.main:app --reload --port 8090
open http://localhost:8090/
```

With hot reload, as two processes:

```bash
venv/bin/uvicorn app.main:app --reload --port 8090   # terminal 1
cd web && npm run dev                                # terminal 2 -> :3000
```

Then open <http://localhost:3000/live/> and set the API base URL to
`http://localhost:8090` on the sign-in screen. `DEV_ORIGINS` in the ops `.env`
already allows `localhost:3000`.

## Build and deploy

```bash
cd web
npm install
npm run build        # -> web/out
npm run typecheck    # tsc --noEmit
```

`web/out` **is committed**. The crawler VM has no Node, so the built dashboard
ships with the repo and `git pull && systemctl restart burgerindex-ops-api`
deploys it. Rebuild and commit `web/out` whenever you change `web/src`.

## Layout

```
src/app/            one folder per screen, plus layout.tsx and the / redirect
src/components/     shared chrome: Primitives, PageHeader, Table, Gate, Providers
src/components/live/  the live page's log panel and stop controls
src/lib/api.ts      typed client; one function per endpoint
src/lib/types.ts    the API's response shapes
src/lib/cron.ts     schedule parsing and next-run, Celery semantics, UTC
src/lib/diff.ts     unified-diff parsing for the fix-review page
src/lib/format.ts   durations, UTC stamps, category and action labels
src/lib/hooks.ts    usePoll (interval + AbortSignal), useTicker
```

Design tokens from the canvas artboards live in `src/app/globals.css`; every
component reads them, so a palette change is a one-file change.

## Where the UI and the API do not line up

- **RAM limit.** The designs show `RAM / LIMIT` per crawler. The limit is the
  crawlers' own `MEMUSAGE_LIMIT_MB`, which lives in the crawlers repo, so it is
  mirrored as `MEMUSAGE_LIMIT_MB` in the ops `.env` and returned as `limit_mb`.
  Left at `0` the column shows RAM with no limit bar. A spider that overrides
  the limit in `custom_settings` is not reflected.
- **Non-fixable issue actions.** Rows such as "Retry with Zyte alt" or
  "Check proxy" name an action the API cannot perform; they render as labels
  marked *manual*, not as buttons that do nothing.
- **Last run.** The scheduler database stores `last_run_at` but no outcome, so
  the LAST RUN column shows the timestamp and borrows a failure label from
  `GET /issues` when that crawler has one.
- **"Retry with a note".** `POST /autofix` takes only a job id and a user, so
  the button is "Retry fix" and queues a fresh attempt without a note.
- **Reject.** There is no endpoint for it. Reject returns to triage and leaves
  the branch and report in the worktree.
