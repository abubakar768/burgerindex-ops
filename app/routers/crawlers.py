"""Server health, running crawlers, logs, Stop."""
from __future__ import annotations

import asyncio
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from monitor.processes import list_crawlers, server_health, stop_crawler, tail_log

from ..config import settings
from ..services.audit import audit

router = APIRouter(tags=["crawlers"])


@router.get("/server")
def server():
    return server_health(("/",))


@router.get("/crawlers")
def crawlers(source: str | None = None):
    rows = list_crawlers()
    for r in rows:
        r["p0"] = r["spider"] in settings.p0_set
    return [r for r in rows if not source or r["source"] == source]


def _find(pid: int) -> dict:
    for c in list_crawlers():
        if c["pid"] == pid:
            return c
    raise HTTPException(404, f"no running crawler with PID {pid}")


@router.get("/crawlers/{pid}/logs")
def logs(pid: int, lines: int = Query(200, le=2000)):
    c = _find(pid)
    if not c["log_file"]:
        raise HTTPException(404, "this crawler does not write to a log file")
    try:
        return {"pid": pid, "log_file": c["log_file"], "lines": tail_log(c["log_file"], lines)}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/crawlers/{pid}/logs/stream")
async def logs_stream(pid: int):
    """Server-sent events: new log lines as they are written (like tail -f)."""
    c = _find(pid)
    path = c["log_file"]
    if not path:
        raise HTTPException(404, "this crawler does not write to a log file")
    try:
        tail_log(path, 1)  # same folder check as /logs
    except PermissionError as e:
        raise HTTPException(403, str(e))

    async def events():
        with open(path, errors="replace") as f:
            f.seek(0, os.SEEK_END)
            idle = 0
            while idle < 600:  # stop after 10 min without new lines
                line = f.readline()
                if line:
                    idle = 0
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    idle += 1
                    await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream")


class StopBody(BaseModel):
    spider: str                                  # must match the PID, guards against stale PIDs
    mode: Literal["graceful", "force", "kill"] = "graceful"
    user: str | None = None


@router.post("/crawlers/{pid}/stop")
def stop(pid: int, body: StopBody):
    result = stop_crawler(pid, body.mode, expect_spider=body.spider)
    audit("stop", body.user, pid=pid, spider=body.spider, mode=body.mode, ok=result["ok"],
          error=result.get("error"))
    if not result["ok"]:
        raise HTTPException(409, result["error"])
    return result
