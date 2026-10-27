"""Runs the API against a tiny local crawlers project and a SQLite 'scheduler' DB."""
import os
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest

ROOT = "/tmp/ops-test"
os.makedirs(f"{ROOT}/logs", exist_ok=True)
os.makedirs(f"{ROOT}/hb", exist_ok=True)
DB = f"{ROOT}/scheduler.db"

# Pin scrapy to this venv. Without it the suite picks up whatever SCRAPY_BIN
# the developer's .env points at -- which is the crawlers venv, an older Scrapy
# that cannot run the spider below.
SCRAPY = os.path.join(os.path.dirname(sys.executable), "scrapy")
if not os.path.exists(SCRAPY):
    SCRAPY = "scrapy"

os.environ.update(
    SCRAPY_BIN=SCRAPY,
    API_TOKEN="t0ken", CRAWLERS_DIR=f"{ROOT}/crawlers", CRAWLER_LOG_DIR=f"{ROOT}/logs",
    HEARTBEAT_DIR=f"{ROOT}/hb", AUDIT_LOG=f"{ROOT}/audit.jsonl", SCHEDULER_DB_URL=f"sqlite:///{DB}",
    SCHEDULES_SQL="SELECT spider, schedule, enabled, last_run_at FROM schedules",
    P0_CRAWLERS="slow-uae-crawl", MEMUSAGE_LIMIT_MB="1500",
)

SPIDER = '''import scrapy
class Slow(scrapy.Spider):
    name = "slow-uae-crawl"
    custom_settings = {"DOWNLOAD_DELAY": 0.3, "ROBOTSTXT_OBEY": False, "TELNETCONSOLE_ENABLED": False,
                       "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter"}
    async def start(self):
        for i in range(5000):
            yield scrapy.Request(f"http://127.0.0.1:8777/?p={i}")
    def parse(self, r):
        yield {"ok": 1}
'''


@pytest.fixture(scope="module")
def client():
    # ROOT lives in /tmp, which macOS sweeps of files untouched for a few days.
    # That reaps proj/settings.py while leaving scrapy.cfg and the directories,
    # so guarding on scrapy.cfg alone leaves a half-project that `scrapy crawl`
    # cannot load ("No module named 'proj.settings'") -- and the crawl dies
    # before it writes a log, which reads here as "the spider never started".
    # Check the settings module too, and rebuild from scratch when it is gone.
    if not os.path.exists(f"{ROOT}/crawlers/proj/settings.py"):
        shutil.rmtree(f"{ROOT}/crawlers", ignore_errors=True)
        subprocess.run([SCRAPY, "startproject", "proj", f"{ROOT}/crawlers"], check=True, capture_output=True)
    open(f"{ROOT}/crawlers/proj/spiders/slow.py", "w").write(SPIDER)
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS schedules")
    con.execute("CREATE TABLE schedules (spider TEXT, schedule TEXT, enabled INT, last_run_at TEXT)")
    con.execute("INSERT INTO schedules VALUES ('slow-uae-crawl', '0 6 * * *', 1, '2026-10-13T06:00')")
    con.execute("INSERT INTO schedules VALUES ('renamed-uae-crawl', '0 3 * * *', 1, NULL)")
    con.execute("INSERT INTO schedules VALUES ('slow-uae-crawl -a hour=8:00', '0 8 * * *', 1, NULL)")
    con.commit()
    site = subprocess.Popen([sys.executable, "-m", "http.server", "8777"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, headers={"Authorization": "Bearer t0ken"})
    yield c
    for cr in c.get("/api/crawlers").json():
        c.post(f"/api/crawlers/{cr['pid']}/stop", json={"spider": cr["spider"], "mode": "kill"})
    site.terminate()


def test_auth_required(client):
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/api/server").status_code == 401
    assert client.get("/health").status_code == 200


def test_openapi_declares_bearer_auth(client):
    """Without a declared scheme /docs has no Authorize button and every
    "Try it out" returns 401, with no way to supply the token."""
    schemes = client.get("/openapi.json").json().get("components", {}).get("securitySchemes", {})
    assert schemes, "no securitySchemes: /docs cannot send a token"
    assert any(v.get("scheme") == "bearer" for v in schemes.values()), schemes


def test_wrong_token_rejected(client):
    from fastapi.testclient import TestClient

    from app.main import app
    assert TestClient(app, headers={"Authorization": "Bearer nope"}).get("/api/server").status_code == 401


def test_spiders_found_in_crawlers_repo(client):
    assert client.get("/api/spiders").json() == [
        {"spider": "slow-uae-crawl", "file": "proj/spiders/slow.py", "p0": True}]


def test_schedules_from_scheduler_db(client):
    rows = {r["spider"]: r for r in client.get("/api/schedules").json()}
    assert rows["slow-uae-crawl"]["running_pid"] is None
    # Scheduled but no longer a spider in the repo: flagged, and Run refuses it.
    assert rows["slow-uae-crawl"]["in_repo"] and not rows["renamed-uae-crawl"]["in_repo"]
    assert client.post("/api/schedules/renamed-uae-crawl/run", json={"user": "abubakar"}).status_code == 404
    # The scheduler stores a command fragment; the spider is its first token.
    with_args = [r for r in client.get("/api/schedules").json() if r["args"]]
    assert [(r["spider"], r["args"], r["in_repo"]) for r in with_args] == [
        ("slow-uae-crawl", "-a hour=8:00", True)]


def test_run_list_logs_stop(client):
    assert client.post("/api/schedules/not-a-spider/run", json={"user": "abubakar"}).status_code == 404
    r = client.post("/api/schedules/slow-uae-crawl/run", json={"user": "abubakar"}).json()
    assert client.post("/api/schedules/slow-uae-crawl/run", json={"user": "abubakar"}).status_code == 409
    time.sleep(6)
    cr = client.get("/api/crawlers").json()[0]
    assert (cr["pid"], cr["source"], cr["by"], cr["env"], cr["p0"]) == (r["pid"], "dashboard", "abubakar", "prod", True)
    # The dashboard draws RAM against the crawlers' own MEMUSAGE_LIMIT_MB.
    assert cr["limit_mb"] == 1500
    assert client.get("/api/schedules").json()[0]["running_pid"] == r["pid"]
    assert any("Spider opened" in l for l in client.get(f"/api/crawlers/{r['pid']}/logs").json()["lines"])
    bad = client.post(f"/api/crawlers/{r['pid']}/stop", json={"spider": "other", "mode": "graceful"})
    assert bad.status_code == 409
    ok = client.post(f"/api/crawlers/{r['pid']}/stop", json={"spider": "slow-uae-crawl", "user": "abubakar"})
    assert ok.json()["signal"] == "SIGTERM"
    from monitor.processes import wait_gone
    assert wait_gone(r["pid"], 30)
    audit = open(f"{ROOT}/audit.jsonl").read()
    assert '"action": "run"' in audit and '"action": "stop"' in audit


def test_autofix_registry_uses_crawlers_repo(client):
    from autofix.pipeline import load_registry
    reg = load_registry()
    assert reg["slow-uae-crawl"]["spider_file"] == "proj/spiders/slow.py"
    assert reg["slow-uae-crawl"]["repo"] == f"{ROOT}/crawlers"


def test_autofix_refused_when_disabled(client, monkeypatch):
    """The VM has no Claude login: Fix must refuse before queuing or fetching jobs."""
    from app.config import settings

    monkeypatch.setattr(settings, "AUTOFIX_ENABLED", False)
    r = client.post("/api/autofix", json={"job_id": "j1", "user": "tester"})
    assert r.status_code == 503 and "AUTOFIX_ENABLED" in r.json()["detail"]
    r = client.post("/api/autofix/approve",
                    json={"report_path": f"{settings.AUTOFIX_WORK}/x/report.json", "user": "tester"})
    assert r.status_code == 503


def test_issues_endpoint_and_deprecated_alias(client):
    """The endpoint was renamed /triage -> /issues; the old path still answers.

    The two payloads are not compared field by field: both reach the live
    dashboard API, and a "lost" row carries an `elapsed=NNh` evidence string
    computed from `now`, so two calls a moment apart legitimately differ.
    What matters is that both routes work and are served by the same handler.
    """
    fresh = client.get("/api/issues?days=7")
    legacy = client.get("/api/triage?days=7")
    assert fresh.status_code == legacy.status_code == 200
    assert isinstance(fresh.json(), list) and isinstance(legacy.json(), list)

    # Same handler behind both paths, and only the old one is flagged.
    spec = client.get("/openapi.json").json()["paths"]
    assert spec["/api/triage"]["get"]["deprecated"] is True
    assert spec["/api/issues"]["get"].get("deprecated", False) is False


def test_api_is_namespaced_and_dashboard_owns_the_root(client):
    """The API lives under /api, so the dashboard owns the root paths."""
    from app.main import API_PREFIX, WEB_DIR

    assert API_PREFIX == "/api"
    # The API answers under the prefix, and nowhere else.
    assert isinstance(client.get("/api/schedules").json(), list)
    assert client.get("/schedules").headers.get("content-type", "").startswith("text/html")

    if not os.path.isdir(WEB_DIR):
        pytest.skip("web/out is not built")

    # The dashboard now owns the root, including the paths the API used to hold.
    for page in ("/", "/live/", "/issues/", "/schedules/", "/fix/"):
        res = client.get(page)
        assert res.status_code == 200, page
        assert "text/html" in res.headers["content-type"], page
