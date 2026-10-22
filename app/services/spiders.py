"""Find spiders in the crawlers repo: spider name -> file path.

Used as the allow-list for Run (only real spiders can be started) and as the
auto-fix registry (which file the agent should edit).

Names come from `scrapy list`, which is authoritative: it is the same resolution
`scrapy crawl` performs, so anything it lists can actually be run. Scanning the
source with a regex is not enough -- many spiders compose their name at import
time (`name = f'{Mixin.name}-ksa'`, or names built in a loop over config), and
no static scan can resolve those. Relying on the regex alone left those spiders
out of the allow-list, so Run refused crawlers the scheduler schedules.

The regex scan is still used for two things: mapping a name to the file that
defines it (`scrapy list` prints names only), and as a fallback when scrapy
cannot run at all. A name with no known file maps to "" -- auto-fix only
interpolates the path into a prompt, so an unknown file degrades rather than
breaks.

`scrapy list` imports every spider, and the crawlers do network I/O at import
(utils/currency_converter.py fetches exchange rates with no timeout). So it
fails whenever that host is slow, and the scan behind it finds about half the
spiders. A scan-only answer is therefore never kept for long, and never
replaces a good `scrapy list` result already held.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time

from monitor.project import project_root

from ..config import settings

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"""^\s+name\s*=\s*['"]([^'"]+)['"]""", re.M)
SKIP = {".git", "venv", ".venv", "node_modules", "__pycache__"}
LIST_TIMEOUT = int(os.environ.get("SCRAPY_LIST_TIMEOUT", "120"))
# How long a scan-only answer stands in before `scrapy list` is tried again.
RETRY_SECONDS = 300

# root -> result of the last `scrapy list` that worked
_good: dict[str, dict[str, str]] = {}
# root -> (monotonic time, scan-only result) after `scrapy list` failed
_fallback: dict[str, tuple[float, dict[str, str]]] = {}


def scan_files(root: str) -> dict[str, str]:
    """Regex scan: spider name -> path relative to root.

    Only sees names written as a plain string literal, and only ones that look
    like spider names: a single token, no whitespace.
    """
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if "spiders" not in dirpath.split(os.sep):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, errors="replace").read()
            except OSError:
                continue
            for name in NAME_RE.findall(text):
                # The pattern matches any indented `name = "..."`, which includes
                # local variables inside parse methods -- the crawlers repo has
                # `name = ' '.join(...)` in one. A spider name is a single token,
                # the same rule scrapy_list applies to its output, so anything
                # with whitespace is not one.
                if not name.strip() or re.search(r"\s", name):
                    continue
                found.setdefault(name, os.path.relpath(path, root))
    return found


def scrapy_list(root: str) -> list[str] | None:
    """Spider names according to scrapy itself. None if scrapy could not run.

    None means "no answer" and is distinct from [] ("a project with no spiders"):
    only None falls back to the regex scan.
    """
    if not os.path.isdir(root):
        log.warning("crawlers dir %s does not exist", root)
        return None
    cwd = project_root(root)
    if cwd is None:
        log.warning("no scrapy.cfg at or below %s; falling back to source scan", root)
        return None
    try:
        proc = subprocess.run(
            [settings.SCRAPY_BIN, "list"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=LIST_TIMEOUT,
        )
    except FileNotFoundError:
        log.warning("SCRAPY_BIN %r not found; falling back to source scan", settings.SCRAPY_BIN)
        return None
    except subprocess.TimeoutExpired:
        log.warning("`scrapy list` timed out after %ss; falling back to source scan", LIST_TIMEOUT)
        return None
    if proc.returncode != 0:
        log.warning(
            "`scrapy list` failed (exit %s); falling back to source scan. stderr: %s",
            proc.returncode,
            (proc.stderr or "").strip()[-500:],
        )
        return None
    # The crawlers project prints its own chatter to stdout; a spider name is a
    # single token, so anything containing whitespace is not one.
    names, noise = [], []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        (noise if re.search(r"\s", line) else names).append(line)
    if noise:
        log.info("ignored %d non-spider line(s) from `scrapy list`: %r", len(noise), noise[:3])
    return names


def discover(root: str | None = None) -> dict[str, str]:
    root = root or settings.CRAWLERS_DIR
    if root in _good:
        return _good[root]
    hit = _fallback.get(root)
    if hit and time.monotonic() - hit[0] < RETRY_SECONDS:
        return hit[1]
    by_file = scan_files(root)
    names = scrapy_list(root)
    if names is None:
        _fallback[root] = (time.monotonic(), by_file)
        return by_file
    # Only what scrapy lists. The scan also matches mixin and base-class names
    # (`name = "albaik"` on a class that `albaik-ksa-crawl` extends) -- 148 of
    # them in the crawlers repo -- and `scrapy crawl` resolves names with the
    # same loader as `scrapy list`, so anything it omits fails "Spider not found".
    found = {name: by_file.get(name, "") for name in names}
    _good[root] = found
    _fallback.pop(root, None)
    return found


def authoritative(root: str | None = None) -> bool:
    """True when discover() reflects `scrapy list`, not just the source scan."""
    return (root or settings.CRAWLERS_DIR) in _good


def refresh() -> dict[str, str]:
    root = settings.CRAWLERS_DIR
    previous = _good.pop(root, None)
    _fallback.pop(root, None)
    found = discover(root)
    if previous is not None and not authoritative(root):
        log.warning("`scrapy list` failed on refresh; keeping the previous %d spiders", len(previous))
        _good[root] = previous
        _fallback.pop(root, None)
        return previous
    return found


def clear() -> None:
    _good.clear()
    _fallback.clear()
