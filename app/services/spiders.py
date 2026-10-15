"""Find spiders in the crawlers repo: spider name -> file path.

Used as the allow-list for Run (only real spiders can be started) and as the
auto-fix registry (which file the agent should edit).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

from ..config import settings

NAME_RE = re.compile(r"""^\s+name\s*=\s*['"]([^'"]+)['"]""", re.M)
SKIP = {".git", "venv", ".venv", "node_modules", "__pycache__"}


@lru_cache(maxsize=1)
def discover(root: str | None = None) -> dict[str, str]:
    root = root or settings.CRAWLERS_DIR
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
                found.setdefault(name, os.path.relpath(path, root))
    return found


def refresh() -> dict[str, str]:
    discover.cache_clear()
    return discover()
