"""Classify a crawler job record into a failure category.

Works directly on the job objects returned by the dashboard's
GET /api/crawler-jobs endpoint (fields: name, status, failureReason,
itemScraped, requestsCount, rawStats, ...). rawStats is the Scrapy stats dict.

No AI here: these are cheap, deterministic rules. AI is only used later,
for categories where `fixable` is True.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Category -> (suggested action, fixable by code change)
CATEGORIES: dict[str, tuple[str, bool]] = {
    "endpoint_changed": ("fix", True),            # mostly 404 / 410
    "blocked": ("fix", True),                     # 401 / 403 / captcha / 429
    "parse_broken": ("fix", True),                # 200s but 0 items, or spider exceptions
    "proxy_auth": ("check_proxy_credentials", False),  # 407
    "zyte_error": ("retry_zyte_alt", False),      # zyte_api RequestError
    "upstream_5xx": ("retry", False),             # 5xx / 520 from site or Zyte
    "network": ("retry", False),                  # connection / DNS / disconnect
    "timeout": ("adjust_config", False),          # closespider_timeout*
    "shutdown": ("rerun", False),                 # killed / OOM / deploy restart
    "silent_drop": ("investigate", True),         # success but far below baseline
    "lost": ("close_lost", False),                # "running" far too long
    "unknown": ("investigate", False),
}

NETWORK_EXC = (
    "ClientConnectorError", "ServerDisconnectedError", "ClientOSError",
    "ResponseFailed", "ConnectionRefusedError", "DNSLookupError",
    "ConnectionLost", "TCPTimedOutError", "ConnectError",
)
TIMEOUT_EXC = ("TimeoutError", "ResponseNeverReceived")


@dataclass
class Classification:
    category: str
    action: str
    fixable: bool
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _status_counts(stats: dict) -> dict[int, int]:
    out: dict[int, int] = {}
    prefix = "downloader/response_status_count/"
    for k, v in stats.items():
        if k.startswith(prefix):
            try:
                out[int(k[len(prefix):])] = int(v)
            except ValueError:
                pass
    return out


def _exception_counts(stats: dict) -> dict[str, int]:
    """Short exception name -> count, from downloader and spider exceptions."""
    out: dict[str, int] = {}
    for prefix in ("downloader/exception_type_count/", "spider_exceptions/"):
        for k, v in stats.items():
            if k.startswith(prefix):
                name = k[len(prefix):].split(".")[-1].strip("'>")
                out[name] = out.get(name, 0) + int(v)
    return out


def _make(category: str, confidence: float, evidence: list[str]) -> Classification:
    action, fixable = CATEGORIES[category]
    return Classification(category, action, fixable, confidence, evidence)


def classify(job: dict) -> Classification | None:
    """Return a Classification for a failed job, or None for a healthy one.

    Silent drops and lost runs need history, see triage.history.
    """
    if job.get("status") != "failed":
        return None

    stats: dict = job.get("rawStats") or {}
    finish = stats.get("finish_reason", "")
    codes = _status_counts(stats)
    exc = _exception_counts(stats)
    total_resp = sum(codes.values())
    total_exc = sum(exc.values())
    items = job.get("itemScraped") or 0
    errors = int(stats.get("log_count/ERROR", 0))

    def share(n: int, of: int) -> float:
        return n / of if of else 0.0

    ev = [f"failureReason={job.get('failureReason')}", f"finish_reason={finish or 'n/a'}",
          f"items={items}", f"errors={errors}"]
    if codes:
        ev.append("http=" + ",".join(f"{c}x{n}" for c, n in sorted(codes.items())))
    if exc:
        ev.append("exceptions=" + ",".join(f"{k}x{v}" for k, v in sorted(exc.items(), key=lambda x: -x[1])))

    # 1. Process-level endings
    if finish == "shutdown":
        return _make("shutdown", 0.9, ev)
    if finish.startswith("closespider_timeout"):
        return _make("timeout", 0.85, ev)

    # 2. Proxy auth: any 407 is a config problem, not a site problem
    if codes.get(407):
        return _make("proxy_auth", 0.95, ev)

    # 3. Zyte API errors dominate
    zyte = exc.get("RequestError", 0)
    if zyte and share(zyte, total_exc + total_resp) >= 0.5:
        return _make("zyte_error", 0.85, ev)

    # 4. Network-level failures dominate
    net = sum(v for k, v in exc.items() if k in NETWORK_EXC)
    tmo = sum(v for k, v in exc.items() if k in TIMEOUT_EXC)
    if net + tmo and share(net + tmo, total_exc + total_resp) >= 0.5:
        return _make("network", 0.8, ev)

    # 5. HTTP status patterns
    if total_resp:
        c4xx_block = codes.get(401, 0) + codes.get(403, 0) + codes.get(429, 0)
        c404 = codes.get(404, 0) + codes.get(410, 0)
        c5xx = sum(n for c, n in codes.items() if c >= 500)
        if share(c404, total_resp) >= 0.5:
            return _make("endpoint_changed", 0.85, ev)
        if c4xx_block and (share(c4xx_block, total_resp) >= 0.3 or total_resp <= 3):
            return _make("blocked", 0.8, ev)
        if share(c5xx, total_resp) >= 0.5:
            return _make("upstream_5xx", 0.75, ev)
        if items == 0 and share(codes.get(200, 0), total_resp) >= 0.8:
            return _make("parse_broken", 0.7, ev)

    # 6. Spider code exceptions with few/no items
    spider_exc = sum(int(v) for k, v in stats.items() if k.startswith("spider_exceptions/"))
    if spider_exc:
        return _make("parse_broken", 0.65, ev)

    # 7. Leftover network/timeout noise
    if net + tmo:
        return _make("network", 0.5, ev)

    return _make("unknown", 0.3, ev)
