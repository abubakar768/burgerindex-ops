# Changes for the crawlers repo (separate PR)

Two Scrapy extensions. Both run **inside each crawl process** — they are not
services, and nothing in burgerindex-ops can enable them. They have to be
installed in the crawlers repo and switched on in its `settings.py`.

| File | Gives the dashboard | Without it |
| --- | --- | --- |
| `heartbeat.py` | live ITEMS / REQUESTS / HEARTBEAT columns, the "may be frozen" banner | those three columns read `—` |
| `scrapy_evidence.py` | log tail and bad responses for auto-fix to read | the agent gets "(no evidence folder saved for this run)" |

Neither breaks a crawl when it is missing or unconfigured: both raise
`NotConfigured`, which Scrapy treats as "skip this extension".

## 1. Copy the files

The crawlers repo already has an extensions package. Put them beside the
existing ones:

```
burgerindex/burgerindex/extensions/
├── __init__.py
├── crawlerstats.py          # already there
├── update_spider_params.py  # already there
├── heartbeat.py             # <- add
└── scrapy_evidence.py       # <- add
```

The import path is therefore `burgerindex.extensions.<module>`, matching
`crawlerstats.py` next to it. Older copies of this file said
`evidence.heartbeat...` or `crawlers.extensions...`; both are wrong for this
repo and will fail at startup with `ModuleNotFoundError`.

## 2. Add two entries to EXTENSIONS — do not reassign it

`settings.py` **already defines `EXTENSIONS`**:

```python
EXTENSIONS = {
   'scrapy_zyte_smartproxy.ZyteSmartProxyMiddleware': 350,
   'spidermon.contrib.scrapy.extensions.Spidermon': 500,
   'burgerindex.extensions.crawlerstats.CrawlerStatsExtension': 550,
}
```

Pasting a fresh `EXTENSIONS = {...}` block **overwrites those three** and
silently disables the Zyte proxy, Spidermon and your own stats extension.
Crawls that depend on the proxy then start failing with no obvious cause.
Add the two entries to the existing dict instead:

```python
EXTENSIONS = {
   'scrapy_zyte_smartproxy.ZyteSmartProxyMiddleware': 350,
   'spidermon.contrib.scrapy.extensions.Spidermon': 500,
   'burgerindex.extensions.crawlerstats.CrawlerStatsExtension': 550,
   'burgerindex.extensions.scrapy_evidence.EvidenceExtension': 560,   # add
   'burgerindex.extensions.heartbeat.HeartbeatExtension': 570,        # add
}
```

The numbers are load order only, and need not be unique — 560 and 570 are
chosen simply to sit after the existing entries.

## 3. Add the settings

```python
# heartbeat.py
HEARTBEAT_DIR = "/var/crawler-heartbeat"   # must equal HEARTBEAT_DIR in the ops .env
HEARTBEAT_INTERVAL = 30                    # seconds
HEARTBEAT_URL = ""                         # optional: also POST each beat here

# scrapy_evidence.py
EVIDENCE_DIR = "/var/crawler-evidence"
EVIDENCE_ONLY_ON_FAILURE = True            # keep files only when the run looks bad
EVIDENCE_LOG_LINES = 200
EVIDENCE_MAX_SAMPLES = 3
EVIDENCE_S3_BUCKET = ""                    # optional upload

# memory, so the dashboard's RAM column has a limit to draw against
MEMUSAGE_ENABLED = True
MEMUSAGE_WARNING_MB = 1500                 # override per spider in custom_settings
MEMUSAGE_LIMIT_MB = 2000                   # must equal MEMUSAGE_LIMIT_MB in the ops .env
```

`HEARTBEAT_DIR` and `MEMUSAGE_LIMIT_MB` appear in both projects. They are not
shared through code — the crawlers write, burgerindex-ops reads — so a change
on one side needs the same change on the other.

The directories must exist and be writable by the user the crawls run as.

## 4. Log files

Every scheduled run must write a log file inside the ops `CRAWLER_LOG_DIR`
(`-s LOG_FILE=...`). `GET /api/crawlers/{pid}/logs` refuses any path outside
that directory, so the log panel stays empty otherwise.

## How this relates to CrawlerStatsExtension

`burgerindex/extensions/crawlerstats.py` already reports to the dashboard, but
only **twice per run** — once on `spider_opened`, once on `spider_closed` — and
it posts to `CRAWLER_JOBS_API_URL`. That is where the dashboard's run history
comes from, and what the Issues page classifies.

`heartbeat.py` fills the gap in between: it fires every `HEARTBEAT_INTERVAL`
seconds **while the crawl is running**, and writes to a local file rather than
an HTTP endpoint, so the Live crawlers page keeps working when the dashboard
API is unreachable.

The two do not overlap, but they are siblings. If `CrawlerStatsExtension` is
ever reworked, folding the heartbeat into it is reasonable — it already holds
the stats handle and the same lifecycle signals.

## The file heartbeat.py writes

This shape is a contract: `monitor/processes.py::_heartbeat` in burgerindex-ops
reads it and adds `age_seconds`. Change a key here and three dashboard columns
go blank, with no error on either side.

```
/var/crawler-heartbeat/{spider}-{pid}.json

{ "spider": "noon-ksa-crawl",  "pid": 6708,   "state": "running",
  "items": 18240,              "requests": 21905,
  "responses": 21880,          "errors": 14,
  "retries": 31,               "dropped": 0,
  "rss_mb": 3610,              "ts": 1792093048.2,
  "finish_reason": null }
```

`rss_mb` reads `/proc/self/statm` and falls back to `getrusage` off Linux,
which reports *peak* rather than current memory — so the figure is only
accurate on the VM.

## Testing it before opening the PR

`scripts/local_sandbox.py` installs `heartbeat.py` into a throwaway Scrapy
project and runs real crawls against a local server, which exercises the whole
path without touching the crawlers repo:

```bash
python scripts/local_sandbox.py serve
```
