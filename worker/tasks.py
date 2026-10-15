from autofix.pipeline import run as autofix_run
from triage import p0_watch as p0

from app.config import settings

from .celery_app import app


@app.task(time_limit=3 * 3600, soft_time_limit=3 * 3600 - 60)
def run_autofix(crawler: str, job: dict) -> dict:
    return autofix_run(crawler, job)


@app.task(time_limit=120)
def p0_watch() -> None:
    args = ["--base", settings.DASHBOARD_API]
    for name in settings.p0_set:
        args += ["--p0-crawler", name]
    p0.main(args)
