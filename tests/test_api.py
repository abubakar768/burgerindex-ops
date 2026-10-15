"""Runs the API against a tiny local crawlers project and a SQLite 'scheduler' DB."""
import os
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
    if not os.path.exists(f"{ROOT}/crawlers/scrapy.cfg"):
        subprocess.run([SCRAPY, "startproject", "proj", f"{ROOT}/crawlers"], check=True, capture_output=True)
    open(f"{ROOT}/crawlers/proj/spiders/slow.py", "w").write(SPIDER)
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS schedules")
    con.execute("CREATE TABLE schedules (spider TEXT, schedule TEXT, enabled INT, last_run_at TEXT)")
    con.execute("INSERT INTO schedules VALUES ('slow-uae-crawl', '0 6 * * *', 1, '2026-10-13T06:00')")
    con.commit()
    site = subprocess.Popen([sys.executable, "-m", "http.server", "8777"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, headers={"Authorization": "Bearer t0ken"})
    yield c
    for cr in c.get("/crawlers").json():
        c.post(f"/crawlers/{cr['pid']}/stop", json={"spider": cr["spider"], "mode": "kill"})
    site.terminate()


def test_auth_required(client):
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/server").status_code == 401
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
    assert TestClient(app, headers={"Authorization": "Bearer nope"}).get("/server").status_code == 401


def test_spiders_found_in_crawlers_repo(client):
    assert client.get("/spiders").json() == [
        {"spider": "slow-uae-crawl", "file": "proj/spiders/slow.py", "p0": True}]


def test_schedules_from_scheduler_db(client):
    rows = client.get("/schedules").json()
    assert rows[0]["spider"] == "slow-uae-crawl" and rows[0]["running_pid"] is None


def test_run_list_logs_stop(client):
    assert client.post("/schedules/not-a-spider/run", json={"user": "abubakar"}).status_code == 404
    r = client.post("/schedules/slow-uae-crawl/run", json={"user": "abubakar"}).json()
    assert client.post("/schedules/slow-uae-crawl/run", json={"user": "abubakar"}).status_code == 409
    time.sleep(6)
    cr = client.get("/crawlers").json()[0]
    assert (cr["pid"], cr["source"], cr["by"], cr["env"], cr["p0"]) == (r["pid"], "dashboard", "abubakar", "prod", True)
    # The dashboard draws RAM against the crawlers' own MEMUSAGE_LIMIT_MB.
    assert cr["limit_mb"] == 1500
    assert client.get("/schedules").json()[0]["running_pid"] == r["pid"]
    assert any("Spider opened" in l for l in client.get(f"/crawlers/{r['pid']}/logs").json()["lines"])
    bad = client.post(f"/crawlers/{r['pid']}/stop", json={"spider": "other", "mode": "graceful"})
    assert bad.status_code == 409
    ok = client.post(f"/crawlers/{r['pid']}/stop", json={"spider": "slow-uae-crawl", "user": "abubakar"})
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


def test_dashboard_does_not_shadow_the_api(client):
    """The pages live under /ui, so the API keeps /triage and /schedules."""
    from app.main import DASHBOARD, WEB_DIR

    assert DASHBOARD == "/ui"
    # A bare /schedules is the API, never a page: it answers JSON, not HTML.
    assert isinstance(client.get("/schedules").json(), list)

    if not os.path.isdir(WEB_DIR):
        pytest.skip("web/out is not built")

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307 and root.headers["location"] == "/ui/live/"
    assert "text/html" in client.get("/ui/live/").headers["content-type"]
