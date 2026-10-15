"""Scheduled crawlers list and the Run button."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from monitor.processes import list_crawlers
from monitor.trigger import AlreadyRunning, start_crawl

from ..config import settings
from ..services import spiders
from ..services.audit import audit
from ..services.schedules import NotConfigured, list_schedules

router = APIRouter(tags=["schedules"])


@router.get("/spiders")
def all_spiders(refresh: bool = False):
    found = spiders.refresh() if refresh else spiders.discover()
    return [{"spider": k, "file": v, "p0": k in settings.p0_set} for k, v in sorted(found.items())]


@router.get("/schedules")
def schedules():
    try:
        rows = list_schedules()
    except NotConfigured as e:
        raise HTTPException(501, str(e))
    running = {c["spider"]: c["pid"] for c in list_crawlers()}
    for r in rows:
        r["running_pid"] = running.get(r["spider"])
        r["p0"] = r["spider"] in settings.p0_set
    return rows


class RunBody(BaseModel):
    user: str


@router.post("/schedules/{spider}/run")
def run(spider: str, body: RunBody):
    if spider not in spiders.discover():
        raise HTTPException(404, f"{spider} is not a spider in {settings.CRAWLERS_DIR}")
    try:
        result = start_crawl(spider, source="dashboard", triggered_by=body.user)
    except AlreadyRunning as e:
        audit("run", body.user, spider=spider, ok=False, error=str(e))
        raise HTTPException(409, str(e))
    audit("run", body.user, spider=spider, ok=True, pid=result["pid"])
    return result
