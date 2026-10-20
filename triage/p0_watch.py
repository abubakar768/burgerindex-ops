"""Post new P0 crawler issues to Slack. Run every 5 minutes from cron.

    */5 * * * * cd /opt/crawler-autofix && SLACK_WEBHOOK_URL=... \
        python -m triage.p0_watch --p0-client Talabat >> /var/log/p0_watch.log 2>&1

Alerts once per (crawler, job, category); state kept in a small JSON file.
That file must survive reboots: losing it re-alerts every open P0 at once, so
it lives under /var/lib, not /tmp. The worker unit creates the directory
(StateDirectory=), and $STATE_DIRECTORY is honoured when systemd sets it.
"""
from __future__ import annotations

import argparse
import json
import os

import requests

from .cli import DEFAULT_BASE, fetch_jobs, p0_crawlers_for
from .history import triage

DEFAULT_STATE_DIR = os.environ.get("STATE_DIRECTORY") or "/var/lib/burgerindex-ops"
STATE = os.environ.get("P0_WATCH_STATE") or os.path.join(DEFAULT_STATE_DIR, "p0_watch_state.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--p0-client", action="append", default=[])
    ap.add_argument("--p0-crawler", action="append", default=[], help="add crawlers by name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    p0 = p0_crawlers_for(args.base, args.p0_client) | set(args.p0_crawler)
    rows = [r for r in triage(fetch_jobs(args.base, days=7), p0) if r["p0"]]

    seen = set(json.load(open(STATE))) if os.path.exists(STATE) else set()
    new = [r for r in rows if f"{r['crawler']}|{r['jobId']}|{r['category']}" not in seen]

    for r in new:
        text = (f":rotating_light: *P0 {r['category']}* `{r['crawler']}`"
                f"{' (failed ' + str(r['streak']) + ' runs in a row)' if r['streak'] > 1 else ''}\n"
                f"Action: {r['action']}\nEvidence: {'; '.join(r['evidence'])}\n"
                f"{args.base}/health")
        if args.dry_run or not os.environ.get("SLACK_WEBHOOK_URL"):
            print(text, "\n")
        else:
            requests.post(os.environ["SLACK_WEBHOOK_URL"], json={"text": text}, timeout=15)
        seen.add(f"{r['crawler']}|{r['jobId']}|{r['category']}")

    os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(sorted(seen), f)
    print(f"{len(rows)} open P0 issues, {len(new)} new alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
