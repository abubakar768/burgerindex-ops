"""All settings come from .env (see .env.example).

The two existing projects are used through these paths:
  CRAWLERS_DIR      crawlers repo: where `scrapy crawl` runs and where spiders are found
  AUTOFIX_REPO      a separate clone of the crawlers repo for auto-fix branches
  SCHEDULER_DB_URL  read-only connection to the scheduler's database
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    API_TOKEN: str = "change-me"

    # Existing projects
    CRAWLERS_DIR: str
    SCHEDULER_DIR: str = ""                 # for reference; the scheduler is read via its DB
    SCHEDULER_DB_URL: str = ""              # read-only DB user, e.g. postgresql://ops_ro:...@host/db
    SCHEDULES_SQL: str = ""                 # query returning spider, schedule, enabled[, last_run_at]
    SCRAPY_BIN: str = "scrapy"              # on the VM: the scheduler venv's bin/scrapy

    # Runtime folders on the crawler machine
    CRAWLER_LOG_DIR: str = "/var/log/crawlers"
    HEARTBEAT_DIR: str = "/var/crawler-heartbeat"
    AUDIT_LOG: str = "/var/log/burgerindex-ops/audit.jsonl"

    # Dashboard + alerts
    DASHBOARD_API: str = "https://data-ingest-dashboard.replit.app"
    P0_CRAWLERS: str = ""                   # comma-separated, e.g. Talabat crawlers
    SLACK_WEBHOOK_URL: str = ""

    # Worker + auto-fix
    REDIS_URL: str = "redis://localhost:6379/3"
    AUTOFIX_REPO: str = ""                  # defaults to CRAWLERS_DIR; a separate clone is safer
    AUTOFIX_WORK: str = "/var/autofix"
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_PROJECT_ID: str = ""
    GITLAB_TOKEN: str = ""
    GITLAB_TARGET: str = "main"

    @property
    def p0_set(self) -> set[str]:
        return {s.strip() for s in self.P0_CRAWLERS.split(",") if s.strip()}


settings = Settings()

# The shared modules (monitor/, autofix/) read these env names directly.
for name, value in {
    "CRAWLER_PROJECT_DIR": settings.CRAWLERS_DIR,
    "CRAWLER_PROD_DIRS": settings.CRAWLERS_DIR,
    "CRAWLER_LOG_DIR": settings.CRAWLER_LOG_DIR,
    "CRAWLER_LOG_DIRS": settings.CRAWLER_LOG_DIR,
    "HEARTBEAT_DIR": settings.HEARTBEAT_DIR,
    "SCRAPY_BIN": settings.SCRAPY_BIN,
    "AUTOFIX_WORK": settings.AUTOFIX_WORK,
    "AUTOFIX_REPO": settings.AUTOFIX_REPO or settings.CRAWLERS_DIR,
    "GITLAB_URL": settings.GITLAB_URL,
    "GITLAB_PROJECT_ID": settings.GITLAB_PROJECT_ID,
    "GITLAB_TOKEN": settings.GITLAB_TOKEN,
    "GITLAB_TARGET": settings.GITLAB_TARGET,
}.items():
    os.environ.setdefault(name, value)
