"""The allow-list must include spiders whose names are not string literals.

Many real spiders compose their name at import time (`name = f'{Mixin.name}-ksa'`),
which a source scan cannot resolve. Those spiders are runnable, so Run must accept
them -- see app/services/spiders.py.
"""
import os
import shutil
import subprocess

import pytest

ROOT = "/tmp/ops-test-spiders"
PROJ = f"{ROOT}/crawlers"

os.environ.setdefault("API_TOKEN", "t0ken")
os.environ.setdefault("CRAWLERS_DIR", PROJ)

from app.config import settings  # noqa: E402
from app.services import spiders  # noqa: E402

LITERAL = '''import scrapy
class Literal(scrapy.Spider):
    name = "plain-crawl"
'''

# Resolves to "composed-ksa-crawl" only when the module is imported.
COMPOSED = '''import scrapy
class Mixin:
    name = "composed"
class Composed(scrapy.Spider):
    name = f"{Mixin.name}-ksa-crawl"
'''


@pytest.fixture(scope="module")
def project():
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT, exist_ok=True)
    subprocess.run(["scrapy", "startproject", "proj", PROJ], check=True, capture_output=True)
    spider_dir = f"{PROJ}/proj/spiders"
    open(f"{spider_dir}/literal.py", "w").write(LITERAL)
    open(f"{spider_dir}/composed.py", "w").write(COMPOSED)
    yield PROJ
    shutil.rmtree(ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    spiders.discover.cache_clear()
    yield
    spiders.discover.cache_clear()


def test_scan_misses_composed_names(project):
    """The regex scan is why the bug existed; pin that limitation down."""
    scanned = spiders.scan_files(project)
    assert "plain-crawl" in scanned
    assert "composed-ksa-crawl" not in scanned


def test_discover_includes_composed_names(project, monkeypatch):
    monkeypatch.setattr(settings, "CRAWLERS_DIR", project)
    monkeypatch.setattr(settings, "SCRAPY_BIN", "scrapy")
    found = spiders.discover()
    assert "composed-ksa-crawl" in found, "f-string name missing: Run would refuse it"
    assert "plain-crawl" in found
    # Literal names keep their file mapping; composed ones have no static source.
    assert found["plain-crawl"].endswith("literal.py")


def test_project_root_found_below_crawlers_dir(project):
    """CRAWLERS_DIR may be the repo while scrapy.cfg sits a level down."""
    parent = os.path.dirname(project)
    assert spiders.project_root(parent) == project
    assert spiders.project_root(project) == project


def test_falls_back_to_scan_when_scrapy_missing(project, monkeypatch):
    monkeypatch.setattr(settings, "CRAWLERS_DIR", project)
    monkeypatch.setattr(settings, "SCRAPY_BIN", "/nonexistent/scrapy")
    found = spiders.discover()
    assert found == spiders.scan_files(project), "fallback must match the old behaviour"
    assert "plain-crawl" in found


def test_ignores_non_spider_output(project, monkeypatch):
    """The real project prints chatter to stdout; names never contain whitespace."""
    monkeypatch.setattr(settings, "CRAWLERS_DIR", project)
    fake = f"{ROOT}/fake-scrapy"
    open(fake, "w").write(
        "#!/bin/sh\necho 'input mapping file not available'\necho plain-crawl\necho composed-ksa-crawl\n"
    )
    os.chmod(fake, 0o755)
    monkeypatch.setattr(settings, "SCRAPY_BIN", fake)
    found = spiders.discover()
    assert "input mapping file not available" not in found
    assert "composed-ksa-crawl" in found
