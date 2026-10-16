"""A self-contained sandbox for trying burgerindex-ops locally, before the VM.

Nothing here touches the real crawlers repo, the scheduler, or any live site.
It builds a throwaway scrapy project whose spiders crawl a local HTTP server,
a SQLite database shaped like django_celery_beat, and a fake dashboard API.

    python scripts/local_sandbox.py smoke    # set up, exercise every endpoint, report
    python scripts/local_sandbox.py serve    # set up, run fake services, print the uvicorn line
    python scripts/local_sandbox.py clean    # delete the sandbox

`smoke` really does start and stop scrapy processes, so it proves the Run/Stop
path end to end rather than mocking it.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("OPS_SANDBOX", "/tmp/ops-sandbox")
PROJ = f"{ROOT}/crawlers"
DB = f"{ROOT}/scheduler.db"
JOBS = f"{ROOT}/jobs.json"
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.sandbox")
TARGET_PORT = 8777     # what the sandbox spiders crawl
DASH_PORT = 8788       # fake dashboard API behind /issues
P0 = "sandbox-p0-crawl"

SCHEDULES_SQL = (
    "SELECT json_extract(t.args,'$[0]') AS spider, "
    "c.minute||' '||c.hour||' '||c.day_of_month||' '||c.month_of_year||' '||c.day_of_week AS schedule, "
    "t.enabled, t.last_run_at "
    "FROM django_celery_beat_periodictask t "
    "JOIN django_celery_beat_crontabschedule c ON c.id = t.crontab_id "
    "WHERE t.task = 'scheduler.tasks.start_crawl'"
)

SPIDER = '''import scrapy


class {cls}(scrapy.Spider):
    name = "{name}"
    custom_settings = {{"DOWNLOAD_DELAY": {delay}, "ROBOTSTXT_OBEY": False,
                       "TELNETCONSOLE_ENABLED": False,
                       "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter"}}

    async def start(self):
        for i in range({n}):
            yield scrapy.Request(f"http://127.0.0.1:{port}/?p={{i}}", dont_filter=True)

    def parse(self, response):
        yield {{"url": response.url, "ok": 1}}
'''

# A name built at import time -- invisible to a source scan, found by `scrapy list`.
COMPOSED_SPIDER = '''import scrapy


class _Mixin:
    region = "uae"


class Composed(scrapy.Spider):
    name = f"sandbox-{_Mixin.region}-composed-crawl"
    custom_settings = {"ROBOTSTXT_OBEY": False, "TELNETCONSOLE_ENABLED": False}

    async def start(self):
        return
        yield
'''


# The crawlers repo gets these from crawlers_patch/. The sandbox installs the
# same extension, so the dashboard's ITEMS / REQUESTS / HEARTBEAT columns and the
# "may be frozen" banner have real data to show.
PROJECT_SETTINGS = """
# --- added by scripts/local_sandbox.py ---------------------------------------
EXTENSIONS = {{"evidence.heartbeat.HeartbeatExtension": 510}}
HEARTBEAT_DIR = "{hb}"
HEARTBEAT_INTERVAL = 5          # 30 on the VM; faster here so the UI moves
MEMUSAGE_ENABLED = True
MEMUSAGE_WARNING_MB = 1500
MEMUSAGE_LIMIT_MB = 2000        # must match MEMUSAGE_LIMIT_MB in the ops .env
"""


def install_heartbeat() -> None:
    """Copy crawlers_patch/heartbeat.py into the sandbox project and enable it."""
    patch = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "crawlers_patch", "heartbeat.py")
    # Top level, beside scrapy.cfg -- the same place it sits in the crawlers repo,
    # and what makes "evidence.heartbeat..." importable from the crawl cwd.
    pkg = f"{PROJ}/evidence"
    os.makedirs(pkg, exist_ok=True)
    open(f"{pkg}/__init__.py", "w").close()
    shutil.copyfile(patch, f"{pkg}/heartbeat.py")

    settings = f"{PROJ}/proj/settings.py"
    body = open(settings).read()
    marker = "# --- added by scripts/local_sandbox.py"
    if marker in body:
        body = body[:body.index(marker)].rstrip() + "\n"
    open(settings, "w").write(body + PROJECT_SETTINGS.format(hb=f"{ROOT}/hb"))


def scrapy_bin() -> str:
    cand = os.path.join(os.path.dirname(sys.executable), "scrapy")
    return cand if os.path.exists(cand) else "scrapy"


def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def build_jobs() -> list[dict]:
    """Crawl history shaped like GET /api/crawler-jobs, covering each failure rule."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jobs: list[dict] = []

    def job(name, days_ago, status, items=None, secs=1800, stats=None, reason=None):
        start = now - timedelta(days=days_ago)
        return {
            "name": name, "status": status,
            "startTime": iso(start),
            "endTime": iso(start + timedelta(seconds=secs)),
            "itemScraped": items, "durationSeconds": secs,
            "failureReason": reason, "rawStats": stats or {},
        }

    # healthy baseline, so silent drops and lost runs have something to compare against
    for d in range(9, 2, -1):
        jobs.append(job("sandbox-uae-crawl", d, "success", items=1000))
    # a silent drop: succeeded, but far below the baseline median
    jobs.append(job("sandbox-uae-crawl", 1, "success", items=120))

    jobs.append(job(P0, 2, "failed", items=0,
                    stats={"downloader/response_status_count/407": 12, "log_count/ERROR": 4},
                    reason="proxy error"))
    jobs.append(job("sandbox-blocked-crawl", 2, "failed", items=0,
                    stats={"downloader/response_status_count/403": 30,
                           "downloader/response_status_count/200": 2, "log_count/ERROR": 9},
                    reason="blocked"))
    jobs.append(job("sandbox-moved-crawl", 3, "failed", items=0,
                    stats={"downloader/response_status_count/404": 40, "log_count/ERROR": 2},
                    reason="not found"))
    jobs.append(job("sandbox-parse-crawl", 1, "failed", items=0,
                    stats={"downloader/response_status_count/200": 50,
                           "spider_exceptions/KeyError": 50, "log_count/ERROR": 50},
                    reason="parse error"))
    jobs.append(job("sandbox-flaky-crawl", 4, "failed", items=0,
                    stats={"downloader/exception_type_count/twisted.internet.error.TimeoutError": 20,
                           "log_count/ERROR": 20}, reason="timeouts"))
    # three failures in a row -> a streak
    for d in (5, 4, 3):
        jobs.append(job("sandbox-streak-crawl", d, "failed", items=0,
                        stats={"finish_reason": "shutdown", "log_count/ERROR": 1},
                        reason="killed"))
    return jobs


def setup() -> None:
    os.makedirs(f"{ROOT}/logs", exist_ok=True)
    os.makedirs(f"{ROOT}/hb", exist_ok=True)

    if not os.path.exists(f"{PROJ}/scrapy.cfg"):
        subprocess.run([scrapy_bin(), "startproject", "proj", PROJ], check=True, capture_output=True)
    spiders = f"{PROJ}/proj/spiders"
    for name, cls, n, delay in [
        ("sandbox-uae-crawl", "Uae", 4000, 0.3),
        (P0, "P0", 4000, 0.3),
        ("sandbox-quick-crawl", "Quick", 3, 0.0),
    ]:
        open(f"{spiders}/{cls.lower()}.py", "w").write(
            SPIDER.format(cls=cls, name=name, n=n, delay=delay, port=TARGET_PORT))
    open(f"{spiders}/composed.py", "w").write(COMPOSED_SPIDER)
    install_heartbeat()

    con = sqlite3.connect(DB)
    con.executescript("""
        DROP TABLE IF EXISTS django_celery_beat_periodictask;
        DROP TABLE IF EXISTS django_celery_beat_crontabschedule;
        CREATE TABLE django_celery_beat_crontabschedule (
          id INTEGER PRIMARY KEY, minute TEXT, hour TEXT,
          day_of_month TEXT, month_of_year TEXT, day_of_week TEXT);
        CREATE TABLE django_celery_beat_periodictask (
          id INTEGER PRIMARY KEY, name TEXT, task TEXT, args TEXT,
          enabled INTEGER, last_run_at TEXT, crontab_id INTEGER, interval_id INTEGER);
        INSERT INTO django_celery_beat_crontabschedule VALUES
          (1,'0','6','*','*','*'), (2,'0','3','1,4,7,10','*','*');
    """)
    rows = [
        (1, "sandbox-uae-crawl", '["sandbox-uae-crawl"]', 1, "2026-10-14T06:00:00", 1, None),
        (2, P0, f'["{P0}"]', 1, "2026-10-14T03:00:00", 2, None),
        (3, "sandbox-quick-crawl", '["sandbox-quick-crawl"]', 0, None, 1, None),
        # scheduled but absent from the project -> Run must refuse it
        (4, "sandbox-retired-crawl", '["sandbox-retired-crawl"]', 1, None, 1, None),
        # interval-scheduled -> dropped by the crontab join, on purpose
        (5, "sandbox-interval-crawl", '["sandbox-interval-crawl"]', 1, None, None, 7),
    ]
    con.executemany(
        "INSERT INTO django_celery_beat_periodictask "
        "(id,name,task,args,enabled,last_run_at,crontab_id,interval_id) VALUES (?,?,'scheduler.tasks.start_crawl',?,?,?,?,?)",
        rows)
    con.commit()
    con.close()

    with open(JOBS, "w") as f:
        json.dump(build_jobs(), f, indent=1)

    env = f"""# Sandbox config -- throwaway. Use with:
#   uvicorn app.main:app --port 8090 --env-file .env.sandbox
API_TOKEN=sandbox-token
CRAWLERS_DIR={PROJ}
SCRAPY_BIN={scrapy_bin()}
CRAWLER_LOG_DIR={ROOT}/logs
HEARTBEAT_DIR={ROOT}/hb
MEMUSAGE_LIMIT_MB=2000
AUDIT_LOG={ROOT}/audit.jsonl
SCHEDULER_DB_URL=sqlite:///{DB}
SCHEDULES_SQL={SCHEDULES_SQL}
DASHBOARD_API=http://127.0.0.1:{DASH_PORT}
P0_CRAWLERS={P0}
REDIS_URL=redis://localhost:6379/9
"""
    open(ENV_FILE, "w").write(env)
    print(f"sandbox    {ROOT}")
    print(f"env file   {ENV_FILE}")


class DashHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/crawler-jobs"):
            body = open(JOBS, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def start_services() -> list:
    """The crawl target and the fake dashboard."""
    procs = []
    procs.append(subprocess.Popen([sys.executable, "-m", "http.server", str(TARGET_PORT)],
                                  cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    socketserver.TCPServer.allow_reuse_address = True
    dash = socketserver.TCPServer(("127.0.0.1", DASH_PORT), DashHandler)
    threading.Thread(target=dash.serve_forever, daemon=True).start()
    procs.append(dash)
    time.sleep(1)
    return procs


def stop_services(procs) -> None:
    for p in procs:
        try:
            p.shutdown() if isinstance(p, socketserver.TCPServer) else p.terminate()
        except Exception:
            pass


# --- smoke test --------------------------------------------------------------
ok_n = fail_n = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  ok    {label}" + (f"  [{detail}]" if detail else ""))
    else:
        fail_n += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


def smoke() -> int:
    setup()
    for k, v in [("API_TOKEN", "sandbox-token"), ("CRAWLERS_DIR", PROJ), ("SCRAPY_BIN", scrapy_bin()),
                 ("CRAWLER_LOG_DIR", f"{ROOT}/logs"), ("HEARTBEAT_DIR", f"{ROOT}/hb"),
                 ("AUDIT_LOG", f"{ROOT}/audit.jsonl"), ("SCHEDULER_DB_URL", f"sqlite:///{DB}"),
                 ("SCHEDULES_SQL", SCHEDULES_SQL), ("DASHBOARD_API", f"http://127.0.0.1:{DASH_PORT}"),
                 ("P0_CRAWLERS", P0)]:
        os.environ[k] = v

    procs = start_services()
    try:
        from fastapi.testclient import TestClient

        from app.main import app
        c = TestClient(app, headers={"Authorization": "Bearer sandbox-token"})

        print("\n1. Auth")
        check("no token is rejected", TestClient(app).get("/server").status_code == 401)
        check("token is accepted", c.get("/server").status_code == 200)

        print("\n2. Server health")
        s = c.get("/server").json()
        check("reports memory and disk", "memory" in s and "disk" in s,
              f"keys={','.join(sorted(s))[:60]}")

        print("\n3. Spiders (the Run allow-list)")
        sp = {x["spider"] for x in c.get("/spiders").json()}
        check("literal-named spider found", "sandbox-uae-crawl" in sp)
        check("composed name found via `scrapy list`", "sandbox-uae-composed-crawl" in sp,
              "this is the bug fixed on main")
        check("P0 spider flagged", any(x["p0"] for x in c.get("/spiders").json() if x["spider"] == P0))

        print("\n4. Schedules (beat-shaped tables)")
        rows = c.get("/schedules").json()
        names = [r["spider"] for r in rows]
        check("returns scheduled spiders", "sandbox-uae-crawl" in names, f"{len(rows)} rows")
        check("cron rendered", any(r["schedule"] == "0 6 * * *" for r in rows))
        check("interval task excluded by the crontab join", "sandbox-interval-crawl" not in names,
              "expected: documents the known gap")

        print("\n5. Run / list / logs / stop")
        check("unknown spider refused", c.post("/schedules/not-a-spider/run",
                                               json={"user": "abubakar"}).status_code == 404)
        check("scheduled-but-absent spider refused",
              c.post("/schedules/sandbox-retired-crawl/run",
                     json={"user": "abubakar"}).status_code == 404)
        r = c.post("/schedules/sandbox-uae-crawl/run", json={"user": "abubakar"})
        check("run accepted", r.status_code == 200, f"pid={r.json().get('pid')}")
        pid = r.json().get("pid")
        check("launched from the scrapy project dir", r.json().get("cwd") == PROJ, str(r.json().get("cwd")))
        check("second run refused while running",
              c.post("/schedules/sandbox-uae-crawl/run", json={"user": "abubakar"}).status_code == 409)

        for _ in range(40):
            live = c.get("/crawlers").json()
            if any(x["pid"] == pid for x in live):
                break
            time.sleep(0.5)
        live = c.get("/crawlers").json()
        mine = [x for x in live if x["pid"] == pid]
        check("appears in /crawlers", bool(mine),
              f"{mine[0]['spider']} ram={mine[0].get('rss_mb')}MB" if mine else "not seen")
        if mine:
            check("tagged as a dashboard run", mine[0]["source"] == "dashboard" and mine[0]["by"] == "abubakar")
            check("running pid shown on /schedules",
                  any(x["running_pid"] == pid for x in c.get("/schedules").json()))
            logs = c.get(f"/crawlers/{pid}/logs?lines=50").json()
            check("log tail readable", any("Spider opened" in l for l in logs.get("lines", [])),
                  f"{len(logs.get('lines', []))} lines")
            bad = c.post(f"/crawlers/{pid}/stop", json={"spider": "wrong-name", "mode": "graceful"})
            check("stop refuses a mismatched spider name", bad.status_code == 409)
            st = c.post(f"/crawlers/{pid}/stop", json={"spider": "sandbox-uae-crawl", "user": "abubakar"})
            check("stop accepted", st.status_code == 200, st.json().get("signal"))
            from monitor.processes import wait_gone
            check("process actually exited", wait_gone(pid, 30))

        print("\n6. Issues (synthetic crawl history)")
        t = c.get("/issues?days=7")
        check("issues endpoint responds", t.status_code == 200)
        if t.status_code == 200:
            found = t.json()
            cats = sorted({row.get("category") for row in found if row.get("category")})
            check("classifies failures", bool(cats), ",".join(cats)[:70])
            check("proxy auth detected", "proxy_auth" in cats)
            check("blocking detected", "blocked" in cats)

        print("\n7. Audit log")
        audit = open(f"{ROOT}/audit.jsonl").read() if os.path.exists(f"{ROOT}/audit.jsonl") else ""
        check("run recorded", '"action": "run"' in audit)
        check("stop recorded", '"action": "stop"' in audit)

        print(f"\n{ok_n} ok, {fail_n} failed")
        return 1 if fail_n else 0
    finally:
        try:
            for cr in c.get("/crawlers").json():
                c.post(f"/crawlers/{cr['pid']}/stop", json={"spider": cr["spider"], "mode": "kill"})
        except Exception:
            pass
        stop_services(procs)


def serve() -> int:
    setup()
    procs = start_services()
    print(f"\ncrawl target     http://127.0.0.1:{TARGET_PORT}")
    print(f"fake dashboard   http://127.0.0.1:{DASH_PORT}/api/crawler-jobs")
    print("\nNow run, in another terminal:\n")
    print("  uvicorn app.main:app --reload --port 8090 --env-file .env.sandbox\n")
    print("  http://localhost:8090/       the dashboard. Sign in with:")
    print("                                 API token  sandbox-token")
    print("                                 your name  anything")
    print("  http://localhost:8090/docs   the API. Authorize with:  sandbox-token\n")
    print("Ctrl-C here when you are done.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_services(procs)
    return 0


def clean() -> int:
    shutil.rmtree(ROOT, ignore_errors=True)
    if os.path.exists(ENV_FILE):
        os.remove(ENV_FILE)
    print(f"removed {ROOT} and {ENV_FILE}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["smoke", "serve", "setup", "clean"])
    mode = ap.parse_args().mode
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit({"smoke": smoke, "serve": serve, "clean": clean,
                      "setup": lambda: (setup(), 0)[1]}[mode]())
