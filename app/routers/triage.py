from fastapi import APIRouter, Query

from triage.cli import fetch_jobs
from triage.history import triage as run_triage

from ..config import settings

router = APIRouter(tags=["triage"])


@router.get("/triage")
def triage(days: int = Query(7, ge=1, le=30)):
    jobs = fetch_jobs(settings.DASHBOARD_API, days)
    return run_triage(jobs, settings.p0_set)
