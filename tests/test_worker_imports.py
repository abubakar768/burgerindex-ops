"""The worker must import what its tasks need after celery has loaded it."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# What `celery -A worker.celery_app` does: cwd on sys.path for the -A import
# only. -P keeps python itself from adding the cwd.
CODE = """
from celery.utils.imports import cwd_in_path
with cwd_in_path():
    import worker.tasks
import autofix.pipeline
autofix.pipeline.load_registry
import monitor.project  # what load_registry imports lazily
print("ok")
"""


def test_lazy_imports_resolve_after_celery_loads_the_app():
    env = dict(os.environ, CRAWLERS_DIR="/nonexistent", API_TOKEN="t")
    p = subprocess.run([sys.executable, "-P", "-c", CODE], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.strip() == "ok", p.stderr[-800:]
