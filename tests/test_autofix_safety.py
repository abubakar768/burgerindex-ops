"""Autofix crawls must not write to production.

The crawlers' ITEM_PIPELINES store to the platform-stores DB and upload to S3,
so a test crawl of a half-fixed spider with pipelines on ships its output.
"""
import json
import os
import subprocess
import sys

import pytest

from autofix import pipeline

SCRAPY = os.path.join(os.path.dirname(sys.executable), "scrapy")


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_sh(cmd, cwd=None, timeout=900, env=None):
        seen.append({"cmd": cmd, "env": env})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(pipeline, "sh", fake_sh)
    return seen


def test_test_crawl_uses_scrapy_bin_with_pipelines_off(calls, monkeypatch, tmp_path):
    monkeypatch.setenv("SCRAPY_BIN", "/opt/crawlers-venv/bin/scrapy")
    pipeline.test_crawl("x-crawl", str(tmp_path), str(tmp_path / "out.jsonl"))
    cmd = calls[0]["cmd"]
    assert cmd[0] == "/opt/crawlers-venv/bin/scrapy"
    joined = " ".join(cmd)
    assert "ITEM_PIPELINES={}" in joined and "TESTING=True" in joined


def test_claude_gets_a_scrapy_that_cannot_store(monkeypatch, tmp_path):
    """Claude may run `scrapy crawl ...` with any flags; the shim's go last."""
    monkeypatch.setattr(pipeline, "WORK_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRAPY_BIN", SCRAPY)
    env = pipeline.safe_scrapy_env()
    # Real scrapy, so this also proves the later -s wins over Claude's.
    out = subprocess.run(
        ["scrapy", "settings", "--get", "ITEM_PIPELINES", "-s", 'ITEM_PIPELINES={"p.Store": 300}'],
        env=env, cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    assert out == "{}"
    testing = subprocess.run(["scrapy", "settings", "--get", "TESTING"],
                             env=env, cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    assert testing == "True"


def test_claude_never_sees_an_api_key(calls, monkeypatch, tmp_path):
    """A stray API key would bill autofix as API credits instead of the subscription."""
    monkeypatch.setattr(pipeline, "WORK_ROOT", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test")
    with pytest.raises(json.JSONDecodeError):  # fake_sh returns no output
        pipeline.run_claude("p", str(tmp_path))
    env = calls[0]["env"]
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-test"


def test_approve_refuses_before_pushing_without_gitlab(calls, monkeypatch, tmp_path):
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"status": "ready_for_review", "branch": "autofix/x",
                                  "worktree": str(tmp_path)}))
    with pytest.raises(RuntimeError, match="nothing was pushed"):
        pipeline.approve(str(report))
    assert calls == []
