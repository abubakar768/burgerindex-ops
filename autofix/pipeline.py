"""Fix pipeline behind the dashboard's Fix button.

    python -m autofix.pipeline run  --crawler noon-ksa-crawl --job-json job.json
    python -m autofix.pipeline approve --report /var/autofix/noon-ksa-crawl-20261009/report.json

`run` never pushes anything. It leaves a local branch + report.json that the
dashboard shows (root cause, diff, test stats, sample items). `approve` pushes
the branch and opens a GitLab MR. Merge/deploy stays with your normal process.

Needs on the worker machine: git, scrapy, the crawlers repo, and the Claude Code
CLI (`claude`) with an API key configured.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone

from triage.rules import classify

from .validate import read_jsonl, validate

REGISTRY_PATH = os.environ.get("AUTOFIX_REGISTRY", "registry.json")
WORK_ROOT = os.environ.get("AUTOFIX_WORK", "/var/autofix")
MAX_ATTEMPTS = 3
TEST_SETTINGS = ["-s", "CLOSESPIDER_ITEMCOUNT=50", "-s", "CLOSESPIDER_TIMEOUT=600",
                 "-s", "LOG_LEVEL=INFO"]
# Every crawl autofix starts -- its own test crawl and any `scrapy` Claude runs --
# is a real crawl of the crawlers project, whose ITEM_PIPELINES write to the
# platform-stores DB and upload to S3. A test crawl of a half-fixed spider must
# not reach either. TESTING=True also stops CrawlerStatsExtension recording the
# run. The cost: items are validated before DuplicateStoreFiltering and the
# cleaning pipelines, so fill rates can read slightly differently from prod.
SAFE_SETTINGS = ["-s", "ITEM_PIPELINES={}", "-s", "TESTING=True"]
CLAUDE_TOOLS = "Read,Edit,Grep,Glob,Bash(scrapy crawl:*),Bash(scrapy parse:*),Bash(python -c:*)"


def sh(cmd: list[str], cwd: str | None = None, timeout: int = 900,
       env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def scrapy_bin() -> str:
    # A bare `scrapy` is this repo's venv, which cannot import the crawlers.
    return os.environ.get("SCRAPY_BIN", "scrapy")


def safe_scrapy_env() -> dict:
    """Env for the Claude session: `scrapy` on PATH is a shim adding SAFE_SETTINGS.

    Claude's allowed tools can only constrain how a command starts
    (`scrapy crawl:*`), not what flags follow, so the safety has to live in the
    binary it resolves. SAFE_SETTINGS go last so they win over any -s Claude
    passes for the same name.
    """
    bin_dir = os.path.join(WORK_ROOT, ".bin")
    os.makedirs(bin_dir, exist_ok=True)
    shim = os.path.join(bin_dir, "scrapy")
    with open(shim, "w") as f:
        f.write("#!/bin/sh\n# written by autofix.pipeline.safe_scrapy_env\n"
                f'exec {shlex.quote(scrapy_bin())} "$@" {shlex.join(SAFE_SETTINGS)}\n')
    os.chmod(shim, 0o755)
    return dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))


def load_registry() -> dict:
    """crawler name -> {repo, spider, spider_file, schema?}.

    Built automatically from the spiders found in the crawlers repo; entries in
    registry.json (optional) add or override fields such as `schema`.
    """
    from app.services.spiders import discover

    repo = os.environ.get("AUTOFIX_REPO") or os.environ["CRAWLER_PROJECT_DIR"]
    reg = {name: {"repo": repo, "spider": name, "spider_file": rel} for name, rel in discover().items()}
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH) as f:
            for name, extra in json.load(f).items():
                reg.setdefault(name, {"repo": repo, "spider": name}).update(extra)
    return reg


def fetch_evidence(path: str | None) -> str | None:
    """Download an s3:// evidence folder to a local temp dir; local paths pass through."""
    if not path or not path.startswith("s3://"):
        return path
    import tempfile

    import boto3
    bucket, prefix = path[5:].split("/", 1)
    local = tempfile.mkdtemp(prefix="evidence-")
    s3 = boto3.client("s3")
    for obj in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
        s3.download_file(bucket, obj["Key"], os.path.join(local, os.path.basename(obj["Key"])))
    return local


def read_evidence(path: str | None, max_body: int = 15_000) -> str:
    path = fetch_evidence(path)
    if not path or not os.path.isdir(path):
        return "(no evidence folder saved for this run)"
    parts = []
    tail = os.path.join(path, "log_tail.txt")
    if os.path.exists(tail):
        parts.append("LAST LOG LINES:\n" + open(tail).read()[-8000:])
    meta = os.path.join(path, "samples.json")
    if os.path.exists(meta):
        for i, s in enumerate(json.load(open(meta))):
            body = open(os.path.join(path, f"sample_{i}.body"), "rb").read()[:max_body]
            parts.append(f"SAMPLE {i}: {s['why']} {s['status']} {s['url']}\n"
                         f"response headers: {json.dumps(s['response_headers'])[:1500]}\n"
                         f"body (truncated):\n{body.decode(errors='replace')}")
    return "\n\n".join(parts)


def build_prompt(crawler: str, cfg: dict, job: dict, cls, evidence: str,
                 last_failure: str | None) -> str:
    stats = {k: v for k, v in (job.get("rawStats") or {}).items()
             if any(t in k for t in ("status_count", "exception", "ERROR", "finish_reason",
                                     "item_scraped", "request_count"))}
    retry = f"\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION:\n{last_failure}\n" if last_failure else ""
    return f"""You are fixing a broken Scrapy spider in this repository.

Crawler: {crawler}
Spider name: {cfg['spider']}
Spider file: {cfg['spider_file']}
Failure category (rule-based): {cls.category} (confidence {cls.confidence})
Evidence summary: {'; '.join(cls.evidence)}

Relevant Scrapy stats from the failed run:
{json.dumps(stats, indent=2)}

{evidence}
{retry}
Instructions:
1. Find the root cause using the evidence above. Compare saved responses with what the spider expects.
2. Make the smallest change to the spider that fixes it. Do not change item field names or output format.
3. Do not touch settings for proxies, Zyte keys or credentials.
4. You may run `scrapy crawl {cfg['spider']} -s CLOSESPIDER_ITEMCOUNT=5` to check your change.
   `scrapy` here has item pipelines switched off, so nothing is stored or uploaded.
5. Finish with a JSON object on the last line only:
   {{"root_cause": "...", "change": "...", "confidence": 0.0-1.0}}
"""


def run_claude(prompt: str, cwd: str) -> dict:
    p = sh(["claude", "-p", prompt, "--output-format", "json",
            "--allowedTools", CLAUDE_TOOLS, "--permission-mode", "acceptEdits"],
           cwd=cwd, timeout=1800, env=safe_scrapy_env())
    if p.returncode != 0:
        raise RuntimeError(f"claude failed: {p.stderr[-2000:]}")
    out = json.loads(p.stdout)
    text = out.get("result", "")
    try:
        summary = json.loads(text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        summary = {"root_cause": text[-1500:], "change": "", "confidence": None}
    return {"session_id": out.get("session_id"), **summary}


def test_crawl(spider: str, cwd: str, out_file: str) -> tuple[list[dict], str]:
    if os.path.exists(out_file):
        os.remove(out_file)
    # The worktree root is not necessarily the scrapy project dir; out_file is
    # absolute, so running a level down does not move the output.
    from monitor.project import crawl_cwd

    p = sh([scrapy_bin(), "crawl", spider, *TEST_SETTINGS, *SAFE_SETTINGS, "-O", out_file],
           cwd=crawl_cwd(cwd), timeout=900)
    items = read_jsonl(out_file) if os.path.exists(out_file) else []
    return items, p.stderr[-4000:]


def run(crawler: str, job: dict, baseline_fill: dict | None = None) -> dict:
    cfg = load_registry()[crawler]
    cls = classify(job)
    if not cls or not cls.fixable:
        return {"status": "not_fixable", "category": cls and cls.category,
                "action": cls and cls.action}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"autofix/{crawler}-{stamp}"
    work = os.path.join(WORK_ROOT, f"{crawler}-{stamp}")
    os.makedirs(WORK_ROOT, exist_ok=True)

    # Isolated checkout of the crawlers repo on a new branch
    sh(["git", "fetch", "origin"], cwd=cfg["repo"])
    r = sh(["git", "worktree", "add", "-b", branch, work, "origin/HEAD"], cwd=cfg["repo"])
    if r.returncode != 0:
        raise RuntimeError(r.stderr)

    schema = json.load(open(cfg["schema"])) if cfg.get("schema") else None
    evidence = read_evidence((job.get("rawStats") or {}).get("evidence/path"))
    out_file = os.path.join(work, "_autofix_test.jsonl")

    attempts, last_failure, result = [], None, None
    for n in range(1, MAX_ATTEMPTS + 1):
        diag = run_claude(build_prompt(crawler, cfg, job, cls, evidence, last_failure), work)
        items, log_tail = test_crawl(cfg["spider"], work, out_file)
        result = validate(items, schema, baseline_fill)
        attempts.append({"attempt": n, "diagnosis": diag, "validation": asdict(result) | {"sample": []}})
        if result.ok:
            break
        last_failure = "\n".join(result.problems) + "\n\nTest crawl log tail:\n" + log_tail

    if os.path.exists(out_file):
        os.remove(out_file)
    diff = sh(["git", "diff"], cwd=work).stdout
    if result.ok and diff:
        sh(["git", "commit", "-am", f"autofix({crawler}): {attempts[-1]['diagnosis'].get('change', '')[:72]}"],
           cwd=work)

    report = {
        "status": "ready_for_review" if result.ok and diff else "needs_human",
        "crawler": crawler, "jobId": job.get("jobId"), "branch": branch, "worktree": work,
        "classification": cls.to_dict(), "attempts": attempts, "diff": diff,
        "test": {"items": result.items, "fill_rates": result.fill_rates, "problems": result.problems},
        "sample_items": result.sample,
        "created": stamp,
    }
    with open(os.path.join(work, "report.json"), "w") as f:
        json.dump(report, f, indent=2, default=str)
    return report


def approve(report_path: str) -> dict:
    """Push the branch and open a GitLab MR. Merge stays manual."""
    import requests

    rep = json.load(open(report_path))
    if rep["status"] != "ready_for_review":
        raise RuntimeError("report is not ready_for_review")
    # Checked before the push: a pushed branch with no MR is one nobody reviews.
    if not (os.environ.get("GITLAB_PROJECT_ID") and os.environ.get("GITLAB_TOKEN")):
        raise RuntimeError("GITLAB_PROJECT_ID and GITLAB_TOKEN are not set; nothing was pushed")
    p = sh(["git", "push", "-u", "origin", rep["branch"]], cwd=rep["worktree"])
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    last = rep["attempts"][-1]["diagnosis"]
    body = (f"Automated fix for `{rep['crawler']}` (job {rep['jobId']}).\n\n"
            f"**Category:** {rep['classification']['category']}\n\n"
            f"**Root cause:** {last.get('root_cause')}\n\n**Change:** {last.get('change')}\n\n"
            f"**Test crawl:** {rep['test']['items']} items, fill rates {rep['test']['fill_rates']}")
    r = requests.post(
        f"{os.environ.get('GITLAB_URL', 'https://gitlab.com')}/api/v4/projects/"
        f"{os.environ['GITLAB_PROJECT_ID']}/merge_requests",
        headers={"PRIVATE-TOKEN": os.environ["GITLAB_TOKEN"]},
        json={"source_branch": rep["branch"], "target_branch": os.environ.get("GITLAB_TARGET", "master"),
              "title": f"autofix: {rep['crawler']}", "description": body,
              "remove_source_branch": True},
        timeout=30)
    r.raise_for_status()
    return {"mr_url": r.json().get("web_url")}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("--crawler", required=True)
    a.add_argument("--job-json", required=True, help="the job object from /api/crawler-jobs")
    a.add_argument("--baseline-fill", help="JSON file of field -> fill rate from the last good run")
    b = sub.add_parser("approve")
    b.add_argument("--report", required=True)
    args = ap.parse_args()

    if args.cmd == "run":
        job = json.load(open(args.job_json))
        base = json.load(open(args.baseline_fill)) if args.baseline_fill else None
        print(json.dumps(run(args.crawler, job, base), indent=2, default=str))
    else:
        print(json.dumps(approve(args.report), indent=2))


if __name__ == "__main__":
    main()
