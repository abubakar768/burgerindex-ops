"""Scrapy extension: keep evidence for failed runs.

Saves, per run:
  - the last N log lines (ring buffer)
  - up to K "bad" responses (status >= 400, or 200 responses that yielded no items)
  - stats.json
Writes to EVIDENCE_DIR/<spider>/<job_id>/ and, if EVIDENCE_S3_BUCKET is set, uploads there.
The folder path is put into stats as `evidence/path`, so it lands in rawStats
and the dashboard can link to it.

Runs inside each crawl process -- one instance per `scrapy crawl`, not a
service. Install and wire it up per crawlers_patch/README.md in the burgerindex-ops
repo. Settings it reads:

    EVIDENCE_DIR = "/var/crawler-evidence"
    EVIDENCE_S3_BUCKET = "my-bucket"          # optional
    EVIDENCE_ONLY_ON_FAILURE = True           # keep files only if the run looks bad
    EVIDENCE_LOG_LINES = 200
    EVIDENCE_MAX_SAMPLES = 3

Unset EVIDENCE_DIR raises NotConfigured, which Scrapy treats as "skip this
extension" -- a crawl never fails because of it.
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime, timezone

from scrapy import signals
from scrapy.exceptions import NotConfigured


class _RingHandler(logging.Handler):
    def __init__(self, size: int):
        super().__init__(level=logging.INFO)
        self.lines: deque[str] = deque(maxlen=size)
        self.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))

    def emit(self, record):
        try:
            self.lines.append(self.format(record))
        except Exception:  # never break the crawl because of logging
            pass


class EvidenceExtension:
    def __init__(self, crawler, base_dir, bucket, log_lines, max_samples, only_on_failure):
        self.crawler = crawler
        self.stats = crawler.stats
        self.base_dir = base_dir
        self.bucket = bucket
        self.max_samples = max_samples
        self.only_on_failure = only_on_failure
        self.ring = _RingHandler(log_lines)
        self.samples: list[dict] = []
        self.items_by_url: set[str] = set()
        self.ok_candidates: list = []   # first few 200 responses, kept in case no items come out

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        base_dir = s.get("EVIDENCE_DIR")
        if not base_dir:
            raise NotConfigured("EVIDENCE_DIR not set")
        ext = cls(crawler, base_dir, s.get("EVIDENCE_S3_BUCKET"),
                  s.getint("EVIDENCE_LOG_LINES", 200), s.getint("EVIDENCE_MAX_SAMPLES", 3),
                  s.getbool("EVIDENCE_ONLY_ON_FAILURE", True))
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.response_received, signal=signals.response_received)
        crawler.signals.connect(ext.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(ext.spider_error, signal=signals.spider_error)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    # --- signals -----------------------------------------------------------
    def spider_opened(self, spider):
        logging.getLogger().addHandler(self.ring)
        job = os.environ.get("SCRAPY_JOB") or os.environ.get("SHUB_JOBKEY") or \
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.dir = os.path.join(self.base_dir, spider.name, job.replace("/", "_"))

    def response_received(self, response, request, spider):
        if response.status >= 400:
            self._keep(response, f"http_{response.status}")
        elif response.status == 200 and len(self.ok_candidates) < self.max_samples:
            self.ok_candidates.append(response)

    def item_scraped(self, item, response, spider):
        self.items_by_url.add(response.url)

    def spider_error(self, failure, response, spider):
        self._keep(response, f"spider_error:{failure.type.__name__}", str(failure.value))

    def spider_closed(self, spider, reason):
        logging.getLogger().removeHandler(self.ring)
        stats = self.stats.get_stats()
        items = stats.get("item_scraped_count", 0)
        failed = items == 0 or reason != "finished" or stats.get("log_count/ERROR", 0) > 0
        if self.only_on_failure and not failed:
            return
        # 200 pages that produced no items: the best evidence for a broken selector
        for r in self.ok_candidates:
            if r.url not in self.items_by_url:
                self._keep(r, "http_200_no_items")
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, "log_tail.txt"), "w") as f:
            f.write("\n".join(self.ring.lines))
        with open(os.path.join(self.dir, "stats.json"), "w") as f:
            json.dump(stats, f, default=str, indent=2)
        with open(os.path.join(self.dir, "samples.json"), "w") as f:
            json.dump([{k: v for k, v in s.items() if k != "body"} for s in self.samples], f, indent=2)
        for i, s in enumerate(self.samples):
            with open(os.path.join(self.dir, f"sample_{i}.body"), "wb") as f:
                f.write(s["body"])
        path = self._upload() or self.dir
        self.stats.set_value("evidence/path", path)

    # --- helpers -----------------------------------------------------------
    def _keep(self, response, why, detail=""):
        if response is None or len(self.samples) >= self.max_samples:
            return
        self.samples.append({
            "why": why, "detail": detail[:500], "url": response.url, "status": response.status,
            "request_headers": {k.decode(): v[0].decode(errors="replace")
                                for k, v in response.request.headers.items()} if response.request else {},
            "response_headers": {k.decode(): v[0].decode(errors="replace")
                                 for k, v in response.headers.items()},
            "body": response.body[:500_000],
        })

    def _upload(self) -> str | None:
        if not self.bucket:
            return None
        try:
            import boto3
        except ImportError:
            return None
        s3 = boto3.client("s3")
        prefix = "crawler-evidence/" + os.path.relpath(self.dir, self.base_dir)
        for name in os.listdir(self.dir):
            s3.upload_file(os.path.join(self.dir, name), self.bucket, f"{prefix}/{name}")
        return f"s3://{self.bucket}/{prefix}"
