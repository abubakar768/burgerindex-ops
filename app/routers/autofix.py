"""Queue an auto-fix, poll it, approve it. The work runs in the Celery worker."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from triage.cli import fetch_jobs

from ..config import settings
from ..services.audit import audit

router = APIRouter(tags=["autofix"])


class FixBody(BaseModel):
    job_id: str
    user: str


@router.post("/autofix")
def start(body: FixBody):
    from worker.tasks import run_autofix

    job = next((j for j in fetch_jobs(settings.DASHBOARD_API, 14) if j.get("jobId") == body.job_id), None)
    if not job:
        raise HTTPException(404, "job not found in the last 14 days")
    task = run_autofix.delay(job["name"], job)
    audit("autofix", body.user, job_id=body.job_id, crawler=job["name"], task_id=task.id)
    return {"task_id": task.id, "crawler": job["name"]}


@router.get("/autofix/{task_id}")
def status(task_id: str):
    from worker.celery_app import app

    r = app.AsyncResult(task_id)
    return {"task_id": task_id, "state": r.state,
            "result": r.result if r.successful() else None,
            "error": str(r.result) if r.failed() else None}


class ApproveBody(BaseModel):
    report_path: str
    user: str


@router.post("/autofix/approve")
def approve(body: ApproveBody):
    from autofix.pipeline import approve as do_approve

    if not body.report_path.startswith(settings.AUTOFIX_WORK):
        raise HTTPException(400, "report must be inside AUTOFIX_WORK")
    result = do_approve(body.report_path)
    audit("approve", body.user, report=body.report_path, **result)
    return result
