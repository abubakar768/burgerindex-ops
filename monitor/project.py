"""Locate the scrapy project directory.

CRAWLER_PROJECT_DIR / CRAWLERS_DIR may point at the repository while the scrapy
project sits a level down (crawlers/ vs crawlers/burgerindex/). Scrapy's project
commands -- crawl, list, check, parse -- only work from the directory holding
scrapy.cfg, and fail with "no active project" anywhere else.

Lives in monitor/ because monitor/ runs standalone on the crawler VM and must
not import app/; app/ imports from monitor/, never the other way round.
"""
from __future__ import annotations

import os
from functools import lru_cache

SKIP = {".git", "venv", ".venv", "node_modules", "__pycache__"}
MAX_DEPTH = 3


@lru_cache(maxsize=8)
def project_root(root: str) -> str | None:
    """The directory holding scrapy.cfg at or below root, or None."""
    if os.path.isfile(os.path.join(root, "scrapy.cfg")):
        return root
    if not os.path.isdir(root):
        return None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if os.path.relpath(dirpath, root).count(os.sep) + 1 > MAX_DEPTH:
            dirnames[:] = []
            continue
        if "scrapy.cfg" in filenames:
            return dirpath
    return None


def crawl_cwd(root: str) -> str:
    """Where to run scrapy. Falls back to root so behaviour never gets worse."""
    return project_root(root) or root
