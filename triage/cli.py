"""Daily triage from the dashboard API.

    python -m triage.cli --days 7 --p0-client Talabat
    python -m triage.cli --days 7 --json > triage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

import requests

from .history import triage

DEFAULT_BASE = "https://data-ingest-dashboard.replit.app"


def fetch_jobs(base: str, days: int, limit: int = 5000) -> list[dict]:
    to = date.today() + timedelta(days=1)
    frm = to - timedelta(days=days + 1)
    r = requests.get(f"{base}/api/crawler-jobs",
                     params={"limit": limit, "from": frm.isoformat(), "to": to.isoformat()},
                     timeout=60)
    r.raise_for_status()
    return r.json()


def p0_crawlers_for(base: str, client_names: list[str]) -> set[str]:
    """Crawler names mapped to the given clients via /api/clients.

    The exact shape of /api/clients is not known here; this looks for a
    `name` and a list of crawler names under common keys. Adjust if needed.
    """
    if not client_names:
        return set()
    r = requests.get(f"{base}/api/clients", timeout=30)
    r.raise_for_status()
    wanted = {c.lower() for c in client_names}
    out: set[str] = set()
    for c in r.json():
        if str(c.get("name", "")).lower() not in wanted:
            continue
        for key in ("crawlers", "crawlerNames", "crawler_names"):
            for item in c.get(key) or []:
                out.add(item if isinstance(item, str) else item.get("name", ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--days", type=int, default=7, help="history window for baselines")
    ap.add_argument("--p0-client", action="append", default=[], help="e.g. Talabat")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    jobs = fetch_jobs(args.base, args.days)
    rows = triage(jobs, p0_crawlers_for(args.base, args.p0_client))

    if args.json:
        json.dump(rows, sys.stdout, indent=2, default=str)
        return 0

    print(f"{'P0':3} {'STREAK':6} {'CATEGORY':17} {'ACTION':24} CRAWLER")
    for r in rows:
        print(f"{'*' if r['p0'] else '':3} {r['streak']:<6} {r['category']:17} "
              f"{r['action']:24} {r['crawler']}")
        print(f"{'':52}{'; '.join(r['evidence'])}")
    print(f"\n{len(rows)} crawlers need attention; "
          f"{sum(r['fixable'] for r in rows)} are code-fixable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
