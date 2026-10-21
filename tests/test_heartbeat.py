"""The heartbeat extension in crawlers_patch/, and the file it shares with monitor/.

crawlers_patch/heartbeat.py ships into the crawlers repo, so it is loaded here by
path rather than imported. The round-trip test is the one that matters most: the
writer lives in another repository and nothing type-checks it against
monitor.processes._heartbeat, so a changed key there blanks three dashboard
columns with no error on either side.
"""
import importlib.util
import json
import os
import pathlib
import types

import pytest
from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings

PATCH = pathlib.Path(__file__).resolve().parent.parent / "crawlers_patch" / "heartbeat.py"


@pytest.fixture(scope="module")
def hb():
    spec = importlib.util.spec_from_file_location("ops_heartbeat_under_test", PATCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crawler(**settings):
    return types.SimpleNamespace(
        settings=Settings(settings),
        stats=types.SimpleNamespace(get_value=lambda key, default=0: {
            "item_scraped_count": 41, "downloader/request_count": 96,
            "log_count/ERROR": 3}.get(key, default)),
        signals=types.SimpleNamespace(connect=lambda *a, **k: None),
    )


def test_unset_directory_skips_the_extension(hb):
    with pytest.raises(NotConfigured):
        hb.HeartbeatExtension.from_crawler(crawler())


def test_unusable_directory_skips_instead_of_failing_the_crawl(hb, tmp_path):
    """Scrapy only skips an extension on NotConfigured. A PermissionError out of
    from_crawler stops every crawl on a machine where the directory is not
    writable, so an unusable directory has to become NotConfigured.

    A regular file in the path fails the same way as a missing permission, and
    does so even when the suite runs as root."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    with pytest.raises(NotConfigured):
        hb.HeartbeatExtension.from_crawler(crawler(HEARTBEAT_DIR=str(blocker / "hb")))


def make(hb, tmp_path):
    ext = hb.HeartbeatExtension.from_crawler(crawler(HEARTBEAT_DIR=str(tmp_path)))
    ext.spider = types.SimpleNamespace(name="noon-ksa-crawl")
    ext.path = os.path.join(ext.dir, f"{ext.spider.name}-{os.getpid()}.json")
    return ext


def test_a_failed_write_does_not_escape_the_loop(hb, tmp_path, monkeypatch):
    """An exception out of a LoopingCall stops it for good, and a stale file then
    reads as a frozen spider on a healthy crawl."""
    ext = make(hb, tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(hb.os, "replace", boom)
    ext.beat("running")  # must not raise


def test_what_the_writer_produces_is_what_the_reader_expects(hb, tmp_path, monkeypatch):
    """Pins the contract between the crawlers repo and monitor/processes.py."""
    from monitor import processes

    ext = make(hb, tmp_path)
    ext.beat("running")

    on_disk = json.loads(pathlib.Path(ext.path).read_text())
    assert set(on_disk) >= {
        "spider", "pid", "state", "ts", "rss_mb", "finish_reason",
        "items", "requests", "responses", "errors", "retries", "dropped",
    }
    assert (on_disk["items"], on_disk["requests"], on_disk["errors"]) == (41, 96, 3)

    monkeypatch.setattr(processes, "HEARTBEAT_DIR", str(tmp_path))
    read = processes._heartbeat("noon-ksa-crawl", os.getpid())
    assert read is not None and read["items"] == 41
    assert read["age_seconds"] >= 0  # added by the reader, not the writer
