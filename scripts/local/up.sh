#!/bin/sh
# Start the API and the worker against .env.local. Ctrl-C stops both.
# Crawls started from the dashboard keep running: they are in their own session
# (monitor/trigger.py), the same as on the VM. See docs/local-dev.md.
cd "$(dirname "$0")/../.." || exit 1
export OPS_ENV_FILE="${OPS_ENV_FILE:-.env.local}"
state="$HOME/.burgerindex-ops-local/state"
mkdir -p "$state"

redis-cli ping >/dev/null 2>&1 || { echo "Redis is not running: brew services start redis"; exit 1; }

venv/bin/uvicorn app.main:app --port 8090 &
api=$!
# --pool=threads: on macOS the prefork pool's children are spawned, not forked,
# and never get the worker's setup -- every task dies with "not enough values
# to unpack (expected 3, got 0)" (Celery 5.6, Python 3.14). The thread pool
# cannot enforce hard time limits, which only matters for a runaway autofix.
venv/bin/celery -A worker.celery_app worker -B -Q burgerindex-ops --pool=threads -c 2 \
  --loglevel=INFO -s "$state/celerybeat-schedule" &
worker=$!

trap 'kill $api $worker 2>/dev/null' INT TERM
echo "dashboard  http://localhost:8090/    (Ctrl-C stops the API and the worker)"
wait
