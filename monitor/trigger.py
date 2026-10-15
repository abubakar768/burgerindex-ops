"""Start a crawl from the scheduler or the dashboard Run button.

Every run started here is tagged, so the Live crawlers page can tell it apart
from manual runs. In Django, call `start_crawl` from a Celery task, never
directly in the web request.
"""
from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone

from .processes import list_crawlers
from .project import crawl_cwd

PROJECT_DIR = os.environ.get("CRAWLER_PROJECT_DIR", "/opt/crawlers")
SCRAPY_BIN = os.environ.get("SCRAPY_BIN", "scrapy")
LOG_DIR = os.environ.get("CRAWLER_LOG_DIR", "/var/log/crawlers")


class AlreadyRunning(Exception):
    pass


def start_crawl(spider: str, source: str = "scheduler", triggered_by: str | None = None,
                env_name: str = "prod", extra_settings: dict | None = None,
                allow_parallel: bool = False) -> dict:
    """source: 'scheduler' | 'dashboard'. Refuses a second copy of a running spider."""
    if not allow_parallel:
        running = [c for c in list_crawlers() if c["spider"] == spider]
        if running:
            raise AlreadyRunning(f"{spider} already running as PID {running[0]['pid']}")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_file = os.path.join(LOG_DIR, f"{spider}-{stamp}.log")
    cmd = [SCRAPY_BIN, "crawl", spider, "-s", f"LOG_FILE={log_file}"]
    for k, v in (extra_settings or {}).items():
        cmd += ["-s", f"{k}={v}"]

    env = dict(os.environ, CRAWL_SOURCE=source, CRAWL_ENV=env_name,
               CRAWL_TRIGGERED_BY=triggered_by or source)
    # `scrapy crawl` only works from the directory holding scrapy.cfg, which is
    # not always PROJECT_DIR itself. Resolved per call so a changed env is picked up.
    cwd = crawl_cwd(os.environ.get("CRAWLER_PROJECT_DIR", PROJECT_DIR))
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Reap it when it ends, so a long-lived worker doesn't collect zombie processes
    threading.Thread(target=proc.wait, daemon=True).start()
    return {"pid": proc.pid, "spider": spider, "source": source, "by": env["CRAWL_TRIGGERED_BY"],
            "log_file": log_file, "started": stamp, "cwd": cwd}
