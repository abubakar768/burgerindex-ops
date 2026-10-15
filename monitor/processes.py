"""Live view of crawlers running on this machine.

Runs ON the crawler VM (e.g. inside the Django scheduler). Uses psutil only.

    from monitor.processes import list_crawlers, server_health, stop_crawler, tail_log
"""
from __future__ import annotations

import json
import os
import signal
import time
from collections import deque

import psutil

HEARTBEAT_DIR = os.environ.get("HEARTBEAT_DIR", "/var/crawler-heartbeat")
LOG_DIRS = [p for p in os.environ.get("CRAWLER_LOG_DIRS", "/var/log/crawlers").split(":") if p]


# --- discovery ---------------------------------------------------------------
def _spider_from_cmdline(cmd: list[str]) -> str | None:
    """'python .../bin/scrapy crawl deliveroo-uae-crawl -s X=1' -> 'deliveroo-uae-crawl'.

    Skips the `sh -c -- scrapy crawl ...` wrapper: its cmdline is one string
    after -c, and it is not the process that uses memory or handles signals.
    """
    if not cmd or os.path.basename(cmd[0]) in ("sh", "bash", "dash"):
        return None
    if not any(os.path.basename(c) == "scrapy" for c in cmd[:3]):  # bin/scrapy or python -m scrapy
        return None
    if "crawl" not in cmd:
        return None
    i = cmd.index("crawl")
    return cmd[i + 1] if i + 1 < len(cmd) else None


def _log_file(proc: psutil.Process, cmd: list[str]) -> str | None:
    """Log path from `-s LOG_FILE=...`, `--logfile`, or where stdout/stderr point."""
    for i, c in enumerate(cmd):
        if c.startswith("LOG_FILE="):
            return c.split("=", 1)[1]
        if c in ("--logfile", "-L") and i + 1 < len(cmd) and cmd[i + 1].startswith("/"):
            return cmd[i + 1]
        if c.startswith("--logfile="):
            return c.split("=", 1)[1]
    for fd in (2, 1):  # Scrapy logs to stderr by default
        try:
            target = os.readlink(f"/proc/{proc.pid}/fd/{fd}")
            if target.startswith("/") and os.path.isfile(target):
                return target
        except OSError:
            pass
    return None


def _heartbeat(spider: str, pid: int) -> dict | None:
    path = os.path.join(HEARTBEAT_DIR, f"{spider}-{pid}.json")
    try:
        with open(path) as f:
            hb = json.load(f)
        hb["age_seconds"] = round(time.time() - hb.get("ts", 0))
        return hb
    except (OSError, ValueError):
        return None


SHELLS = {"bash", "zsh", "sh", "fish", "tmux: server", "tmux", "screen", "sshd"}
PROD_DIRS = [p for p in os.environ.get("CRAWLER_PROD_DIRS", "").split(":") if p]


def run_source(proc: psutil.Process) -> dict:
    """Who started this crawl.

    1. Tagged runs: the scheduler (and the dashboard Run button) start crawls with
       CRAWL_SOURCE / CRAWL_TRIGGERED_BY / CRAWL_ENV in the environment.
    2. Untagged runs: walk up the parents. A terminal, ssh, tmux or screen means
       a person started it by hand.
    """
    try:
        env = proc.environ()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        env = None
    try:
        cwd = proc.cwd()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        cwd = None
    in_prod_dir = bool(cwd and any(cwd == d or cwd.startswith(d.rstrip("/") + "/") for d in PROD_DIRS))

    if env and env.get("CRAWL_SOURCE"):
        return {"source": env["CRAWL_SOURCE"], "by": env.get("CRAWL_TRIGGERED_BY"),
                "env": env.get("CRAWL_ENV") or ("prod" if in_prod_dir else "unknown"), "cwd": cwd}

    hint = "untagged"
    try:
        for parent in proc.parents():
            name = parent.name()
            if parent.terminal() or name in SHELLS - {"sh"}:
                hint = f"started from {name}" + (f" on {parent.terminal()}" if parent.terminal() else "")
                break
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    if env is None:
        hint = "another user's process"
    return {"source": "manual", "by": hint, "env": "prod" if in_prod_dir else "staging/other", "cwd": cwd}


def list_crawlers() -> list[dict]:
    out = []
    for p in psutil.process_iter(["pid", "ppid", "cmdline", "create_time", "username", "status"]):
        cmd = p.info["cmdline"] or []
        spider = _spider_from_cmdline(cmd)
        if not spider:
            continue
        try:
            rss = p.memory_info().rss
            for ch in p.children(recursive=True):  # e.g. Playwright browsers
                rss += ch.memory_info().rss
            cpu = p.cpu_percent(interval=0.1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        out.append({
            "pid": p.info["pid"],
            "wrapper_pid": p.info["ppid"],
            "spider": spider,
            "user": p.info["username"],
            "status": p.info["status"],
            "started": p.info["create_time"],
            "runtime_seconds": round(time.time() - p.info["create_time"]),
            "rss_mb": round(rss / 2**20),
            "cpu_percent": cpu,
            "log_file": _log_file(p, cmd),
            **run_source(p),
            "heartbeat": _heartbeat(spider, p.info["pid"]),
        })
    return sorted(out, key=lambda c: -c["rss_mb"])


def server_health(paths: tuple[str, ...] = ("/",)) -> dict:
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    return {
        "memory": {"total_mb": vm.total // 2**20, "available_mb": vm.available // 2**20,
                   "percent": vm.percent},
        "swap": {"used_mb": sw.used // 2**20, "percent": sw.percent},
        "load_avg": os.getloadavg(),
        "cpu_count": psutil.cpu_count(),
        "disk": {p: {"percent": psutil.disk_usage(p).percent,
                     "free_gb": round(psutil.disk_usage(p).free / 2**30, 1)} for p in paths},
    }


# --- stop --------------------------------------------------------------------
def stop_crawler(pid: int, mode: str = "graceful", expect_spider: str | None = None) -> dict:
    """mode: 'graceful' = SIGTERM (Scrapy finishes in-flight work, runs close hooks,
    saves stats; finish_reason 'shutdown'). 'force' = second SIGTERM (Scrapy stops
    the reactor without cleanup). 'kill' = SIGKILL (nothing saved).

    Only signals a process that is still a `scrapy crawl` (checked right before
    sending), so a reused PID or a typo can't kill something else.
    """
    try:
        p = psutil.Process(pid)
        spider = _spider_from_cmdline(p.cmdline())
    except psutil.NoSuchProcess:
        return {"ok": False, "error": "process not running"}
    if not spider:
        return {"ok": False, "error": "not a scrapy crawl process"}
    if expect_spider and spider != expect_spider:
        return {"ok": False, "error": f"pid {pid} is {spider}, not {expect_spider}"}

    sig = {"graceful": signal.SIGTERM, "force": signal.SIGTERM, "kill": signal.SIGKILL}[mode]
    if mode == "kill":
        for ch in p.children(recursive=True):  # don't leave orphan browsers behind
            try:
                ch.send_signal(signal.SIGKILL)
            except psutil.NoSuchProcess:
                pass
    p.send_signal(sig)
    return {"ok": True, "pid": pid, "spider": spider, "signal": sig.name, "mode": mode}


def wait_gone(pid: int, timeout: float) -> bool:
    try:
        psutil.Process(pid).wait(timeout=timeout)
        return True
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        return False


# --- logs --------------------------------------------------------------------
def tail_log(path: str, lines: int = 200, allowed_dirs: list[str] | None = None) -> list[str]:
    """Last N lines of a crawler log. Refuses paths outside the allowed log dirs."""
    real = os.path.realpath(path)
    allowed = [os.path.realpath(d) for d in (allowed_dirs or LOG_DIRS)]
    if not any(real == d or real.startswith(d + os.sep) for d in allowed):
        raise PermissionError(f"{path} is outside the crawler log dirs")
    with open(real, errors="replace") as f:
        return list(deque(f, maxlen=min(lines, 2000)))
