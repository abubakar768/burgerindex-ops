"""Crawlers whose latest run needs attention, worst first.

The rules and history checks live in the `triage/` package, which keeps its
name: this is the HTTP surface, and the dashboard calls it Issues.
"""
from fastapi import APIRouter, Query

from triage.cli import fetch_jobs
from triage.history import triage as run_triage

from ..config import settings

router = APIRouter(tags=["issues"])


def _issues(days: int) -> list[dict]:
    jobs = fetch_jobs(settings.DASHBOARD_API, days)
    return run_triage(jobs, settings.p0_set)


@router.get("/issues")
def issues(days: int = Query(7, ge=1, le=30)):
    return _issues(days)


@router.get("/triage", deprecated=True)
def triage(days: int = Query(7, ge=1, le=30)):
    """Deprecated: the former name for GET /api/issues."""
    return _issues(days)
