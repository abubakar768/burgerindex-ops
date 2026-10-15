"""Checks that need more than one run: silent drops, streaks, lost runs.

Input is the list returned by GET /api/crawler-jobs (newest first or any order).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

from .rules import Classification, _make, classify

BASELINE_RUNS = 5          # same window the dashboard uses
SILENT_DROP_RATIO = 0.4    # success but below 40% of baseline median
LOST_RUNTIME_FACTOR = 2.0  # running longer than 2x median duration
LOST_FALLBACK_HOURS = 36   # when there is no duration history


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def group_by_crawler(jobs: list[dict]) -> dict[str, list[dict]]:
    """name -> runs sorted oldest to newest."""
    g: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        g[j["name"]].append(j)
    for runs in g.values():
        runs.sort(key=lambda j: j.get("startTime") or "")
    return g


def baseline(runs: list[dict], before_idx: int) -> tuple[float | None, float | None]:
    """Median items and median duration of the last N successful runs before index."""
    prev = [r for r in runs[:before_idx] if r.get("status") == "success"][-BASELINE_RUNS:]
    items = [r["itemScraped"] for r in prev if r.get("itemScraped")]
    durs = [r["durationSeconds"] for r in prev if r.get("durationSeconds")]
    return (median(items) if items else None, median(durs) if durs else None)


def silent_drop(run: dict, base_items: float | None) -> Classification | None:
    if run.get("status") != "success" or not base_items:
        return None
    items = run.get("itemScraped") or 0
    ratio = items / base_items
    if ratio < SILENT_DROP_RATIO:
        return _make("silent_drop", 0.7, [
            f"items={items}", f"baseline_median={int(base_items)}", f"ratio={ratio:.0%}",
        ])
    return None


def lost_run(run: dict, base_dur: float | None, now: datetime) -> Classification | None:
    if run.get("status") != "running":
        return None
    start = _ts(run.get("startTime"))
    if not start:
        return None
    elapsed = (now - start).total_seconds()
    limit = base_dur * LOST_RUNTIME_FACTOR if base_dur else LOST_FALLBACK_HOURS * 3600
    if elapsed > limit:
        return _make("lost", 0.8, [
            f"elapsed={elapsed / 3600:.1f}h",
            f"limit={limit / 3600:.1f}h" + ("" if base_dur else " (no history)"),
        ])
    return None


def streak(runs: list[dict]) -> int:
    """Consecutive failed runs at the end of the history."""
    n = 0
    for r in reversed([r for r in runs if r.get("status") in ("success", "failed")]):
        if r["status"] != "failed":
            break
        n += 1
    return n


def triage(jobs: list[dict], p0_crawlers: set[str] | None = None,
           now: datetime | None = None) -> list[dict]:
    """One row per crawler whose latest run needs attention, worst first."""
    now = now or datetime.now(timezone.utc)
    p0_crawlers = p0_crawlers or set()
    rows = []
    for name, runs in group_by_crawler(jobs).items():
        # Lost runs: any open run, not only the latest
        for i, r in enumerate(runs):
            _, base_dur = baseline(runs, i)
            c = lost_run(r, base_dur, now)
            if c:
                rows.append(_row(name, r, c, 0, name in p0_crawlers))

        finished = [r for r in runs if r.get("status") in ("success", "failed")]
        if not finished:
            continue
        last = finished[-1]
        idx = runs.index(last)
        c = classify(last)
        if c is None:
            base_items, _ = baseline(runs, idx)
            c = silent_drop(last, base_items)
        if c:
            rows.append(_row(name, last, c, streak(runs), name in p0_crawlers))

    # P0 first, then longest failure streak, then hard failures > silent drops > lost runs
    rank = {"silent_drop": 1, "lost": 2}
    rows.sort(key=lambda r: (not r["p0"], -r["streak"], rank.get(r["category"], 0), r["crawler"]))
    return rows


def _row(name: str, run: dict, c: Classification, streak_n: int, p0: bool) -> dict:
    return {
        "crawler": name,
        "jobId": run.get("jobId"),
        "status": run.get("status"),
        "started": run.get("startTime"),
        "p0": p0,
        "streak": streak_n,
        **c.to_dict(),
    }
