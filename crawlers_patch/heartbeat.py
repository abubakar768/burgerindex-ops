"""Scrapy extension: write live stats every N seconds while the crawl runs.

Gives the dashboard request count, items, errors and memory for RUNNING crawls,
and a heartbeat: no update for a few intervals = frozen spider.

settings.py:
    EXTENSIONS = {"evidence.heartbeat.HeartbeatExtension": 510}
    HEARTBEAT_DIR = "/var/crawler-heartbeat"
    HEARTBEAT_INTERVAL = 30      # seconds
    HEARTBEAT_URL = ""           # optional: also POST the JSON here
"""
from __future__ import annotations

import json
import os
import resource
import time

from scrapy import signals
from scrapy.exceptions import NotConfigured
from twisted.internet import task

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
        os.makedirs(directory, exist_ok=True)

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
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)  # atomic: readers never see half a file
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
