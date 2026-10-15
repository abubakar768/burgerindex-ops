# Changes for the crawlers repo (separate PR)

1. Copy `heartbeat.py` and `scrapy_evidence.py` into the crawlers project,
   e.g. `crawlers/extensions/`.
2. Add to the crawlers project's `settings.py`:

```python
EXTENSIONS = {
    "crawlers.extensions.heartbeat.HeartbeatExtension": 510,
    "crawlers.extensions.scrapy_evidence.EvidenceExtension": 500,
}
HEARTBEAT_DIR = "/var/crawler-heartbeat"     # same as burgerindex-ops .env
HEARTBEAT_INTERVAL = 30
EVIDENCE_DIR = "/var/crawler-evidence"
MEMUSAGE_ENABLED = True
MEMUSAGE_WARNING_MB = 1500                    # override per spider in custom_settings
MEMUSAGE_LIMIT_MB = 2000
```
3. Make sure every scheduled run writes a log file (`-s LOG_FILE=...`), into `CRAWLER_LOG_DIR`.
