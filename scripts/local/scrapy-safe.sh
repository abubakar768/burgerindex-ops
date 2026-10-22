#!/bin/sh
# SCRAPY_BIN for running burgerindex-ops on a Mac against the real crawlers repo.
# Never on the VM: this is what keeps a local Run from looking like production.
#
# Run, Stop and autofix start real crawls of real sites. The crawlers' item
# pipelines write to the platform-stores DB and upload to S3, and
# CrawlerStatsExtension records the run unless TESTING is set, so a local test
# would otherwise show up as a production crawl.
#
# Two tiers of flags:
#   LIMITS  go before the caller's, so a caller may override them (autofix asks
#           for 50 items and 600 s; the dashboard's Run passes nothing).
#   SAFE    go last, so nothing overrides them.
# They follow the command name because `scrapy -s X crawl` reads X as the command.
#
# CRAWLERS_SCRAPY is the crawlers venv's scrapy; it defaults to the sibling
# checkout next to burgerindex-ops.
here=$(cd "$(dirname "$0")" && pwd)
real=${CRAWLERS_SCRAPY:-$(cd "$here/../../.." && pwd)/crawlers/burgerindex/venv/bin/scrapy}

[ $# -eq 0 ] && exec "$real"
cmd=$1
shift
exec "$real" "$cmd" \
  -s LOG_LEVEL=INFO -s CLOSESPIDER_ITEMCOUNT=5000 -s CLOSESPIDER_TIMEOUT=90 \
  -s DOWNLOAD_DELAY=3 -s CONCURRENT_REQUESTS=1 -s HEARTBEAT_INTERVAL=5 \
  "$@" \
  -s TESTING=True -s 'ITEM_PIPELINES={}' -s SPIDERMON_ENABLED=False
