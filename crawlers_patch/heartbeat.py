"""Scrapy extension: write live stats every N seconds while the crawl runs.

Gives the dashboard request count, items, errors and memory for RUNNING crawls,
and a heartbeat: no update for a few intervals = frozen spider.

Runs inside each crawl process, on the Twisted reactor -- one instance per
`scrapy crawl`, not a service.

Install and wire it up per crawlers_patch/README.md in the burgerindex-ops repo.
The entry goes into the crawlers repo's EXTENSIONS dict, which already has
entries and must not be reassigned. Settings it reads:

    HEARTBEAT_DIR = "/var/crawler-heartbeat"   # must equal the ops .env
    HEARTBEAT_INTERVAL = 30                    # seconds
    HEARTBEAT_URL = ""                         # optional: also POST the JSON here

A monitoring extension must never stop the crawl it watches. Unset HEARTBEAT_DIR
and a directory that cannot be created both raise NotConfigured, which Scrapy
treats as "skip this extension" and logs as a warning. A write that fails
mid-crawl is logged and the next beat tries again.
"""
from __future__ import annotations

import json
import logging
import os
import resource
import time

from scrapy import signals
from scrapy.exceptions import NotConfigured
from twisted.internet import task

log = logging.getLogger(__name__)

KEYS = {
    "items": "item_scraped_count",
    "requests": "downloader/request_count",
    "responses": "downloader/response_count",
    "errors": "log_count/ERROR",
    "retries": "retry/count",
    "dropped": "item_dropped_count",
}


def _rss_mb() -> int:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // 2**20
    except OSError:  # non-Linux fallback: peak, not current
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


class HeartbeatExtension:
    def __init__(self, crawler, directory, interval, url):
        self.crawler, self.stats = crawler, crawler.stats
        self.dir, self.interval, self.url = directory, interval, url
        self.loop = None
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            # Left to propagate, this is a PermissionError out of from_crawler, and
            # Scrapy only skips an extension on NotConfigured: every crawl on a
            # machine where the directory is not writable would fail to start.
            raise NotConfigured(f"HEARTBEAT_DIR {directory!r} is not usable: {e}")

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        if not s.get("HEARTBEAT_DIR"):
            raise NotConfigured
        ext = cls(crawler, s.get("HEARTBEAT_DIR"), s.getint("HEARTBEAT_INTERVAL", 30),
                  s.get("HEARTBEAT_URL"))
        crawler.signals.connect(ext.opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.closed, signal=signals.spider_closed)
        return ext

    def opened(self, spider):
        self.spider = spider
        self.path = os.path.join(self.dir, f"{spider.name}-{os.getpid()}.json")
        self.loop = task.LoopingCall(self.beat, "running")
        self.loop.start(self.interval, now=True)

    def beat(self, state, reason=None):
        data = {k: self.stats.get_value(v, 0) for k, v in KEYS.items()}
        data.update(spider=self.spider.name, pid=os.getpid(), state=state, ts=time.time(),
                    rss_mb=_rss_mb(), finish_reason=reason)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)  # atomic: readers never see half a file
        except OSError as e:
            # An exception escaping a LoopingCall stops it for good, and a stale
            # file then reads as a frozen spider. One failed write must not do that.
            log.warning("heartbeat write failed, will retry next beat: %s", e)
        if self.url:
            try:
                import requests
                requests.post(self.url, json=data, timeout=3)
            except Exception:
                pass

    def closed(self, spider, reason):
        if self.loop and self.loop.running:
            self.loop.stop()
        self.beat("finished", reason)
