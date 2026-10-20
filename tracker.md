# Tracker

Working log for burgerindex-ops. Newest first within each section. Statuses
inferred from the code and git history on 2026-10-20 — fix any I read wrong.

## In flight

_Nothing claimed. Add a line here when you pick something up._

## Next

| # | Item | Notes |
| --- | --- | --- |
| 1 | Verify `/api/spiders` lists the real spiders locally | `scrapy list` is authoritative; needs `SCRAPY_BIN` pointing at the crawlers' venv |
| 2 | Verify `/api/schedules` against the live scheduler DB | `SCHEDULES_SQL` is written in `.env.example`; confirm with `python scripts/check_schedules.py` |
| 3 | Deploy on burgerindex-vm | systemd units in `deploy/`; check `/api/crawlers` shows today's runs and `/` opens the dashboard |
| 4 | Open the crawlers repo PR from `crawlers_patch/` | heartbeat + evidence extensions, memory limits, log files — the Live page's heartbeat and P0 columns depend on it |
| 5 | Exercise auto-fix end to end on the VM | needs git, scrapy, the `crawlers-autofix` clone and the Claude Code CLI on the worker |
| 6 | Decide on tagging scheduler launches `CRAWL_SOURCE=scheduler` | would let the Live page tell scheduled from manual runs; a change in the scheduler repo |
| 7 | `test_run_list_logs_stop` fails on macOS | the started crawl is not listed; expected to be the Linux-only process detail the README warns about — confirm on the VM, then skip it locally rather than leaving a red suite |

## Known gaps

- No measurement of classification accuracy, so the `/issues/` sort order is
  trusted on faith. See PRD §6.
- ~~P0 watch state lives in a JSON file (`P0_WATCH_STATE`, `/tmp` by default) —
  wiping it re-alerts every open P0.~~ Fixed in #14: it moves to
  `/var/lib/burgerindex-ops`, created by the worker unit's `StateDirectory=`.
- Process details (log path, other users' env) are Linux-only; local runs on
  macOS show less than the VM will.
- No alert if burgerindex-ops itself is down; `/health` exists but nothing polls it.

## Done

| Date | Item |
| --- | --- |
| 2026-10-19 | Keep local variables out of the spider allow-list (#11) |
| 2026-10-19 | Move navigation into a left sidebar (#10) |
| 2026-10-19 | Ignore `.env.local` (#12) |
| 2026-10-19 | Stop the `/api/triage` alias test comparing two live payloads (#9) |
| 2026-10-19 | Name the product burgerindex ops (#8) |
| 2026-10-16 | Serve the dashboard at the root, namespace the API under `/api` (#7) |
| 2026-10-16 | Rename the Triage page to Issues (#6) |
| 2026-10-16 | Add a light theme, exercise the dashboard end to end (#5) |
| 2026-10-16 | Add the Crawler Operations Dashboard front end (#4) |
| 2026-10-15 | Declare the bearer scheme so `/docs` can authenticate (#3) |
| 2026-10-15 | Add a local sandbox for trying the API before deploying (#2) |
| 2026-10-15 | Take the spider allow-list from `scrapy list`, run `scrapy crawl` from the scrapy.cfg directory (#1) |
