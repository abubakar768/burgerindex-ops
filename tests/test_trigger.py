"""`scrapy crawl` must run from the directory holding scrapy.cfg.

CRAWLER_PROJECT_DIR may point at the repository while the scrapy project sits a
level down. Launching from the wrong directory fails with "no active project",
so Run appeared broken even for spiders the allow-list accepted.
"""
import os
import shutil
import time

import pytest

ROOT = "/tmp/ops-test-trigger"
REPO = f"{ROOT}/repo"            # CRAWLER_PROJECT_DIR -- no scrapy.cfg here
PROJECT = f"{REPO}/inner"        # scrapy.cfg lives here

os.environ.setdefault("CRAWLER_LOG_DIR", f"{ROOT}/logs")

from monitor import trigger  # noqa: E402
from monitor.project import crawl_cwd, project_root  # noqa: E402


@pytest.fixture(scope="module")
def repo():
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(f"{PROJECT}/sub", exist_ok=True)
    os.makedirs(f"{ROOT}/logs", exist_ok=True)
    open(f"{PROJECT}/scrapy.cfg", "w").write("[settings]\ndefault = proj.settings\n")
    # a fake scrapy that records the directory it was launched from
    fake = f"{ROOT}/scrapy"
    open(fake, "w").write("#!/bin/sh\npwd > \"$CWD_RECORD\"\n")
    os.chmod(fake, 0o755)
    yield fake
    shutil.rmtree(ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    project_root.cache_clear()
    yield
    project_root.cache_clear()


def test_project_root_resolves_one_level_down(repo):
    assert project_root(REPO) == PROJECT


def test_crawl_cwd_falls_back_when_no_cfg(repo):
    """No scrapy.cfg anywhere -> behave exactly as before, don't crash."""
    bare = f"{ROOT}/bare"
    os.makedirs(bare, exist_ok=True)
    assert crawl_cwd(bare) == bare


def test_start_crawl_launches_from_project_dir(repo, monkeypatch, tmp_path):
    record = tmp_path / "cwd.txt"
    monkeypatch.setenv("CRAWLER_PROJECT_DIR", REPO)
    monkeypatch.setenv("CWD_RECORD", str(record))
    monkeypatch.setattr(trigger, "SCRAPY_BIN", repo)
    monkeypatch.setattr(trigger, "LOG_DIR", f"{ROOT}/logs")
    monkeypatch.setattr(trigger, "list_crawlers", lambda: [])

    result = trigger.start_crawl("any-spider", source="dashboard", triggered_by="tester")

    assert result["cwd"] == PROJECT, "launched from the repo root, not the scrapy project"
    for _ in range(50):
        if record.exists() and record.read_text().strip():
            break
        time.sleep(0.05)
    assert os.path.realpath(record.read_text().strip()) == os.path.realpath(PROJECT)
