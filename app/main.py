"""burgerindex-ops API.  Run: uvicorn app.main:app --host 0.0.0.0 --port 8090"""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .config import settings
from .routers import autofix, crawlers, issues, schedules

app = FastAPI(title="burgerindex-ops", version="0.1.0")

# The dashboard is served from this app (see the mount below), so it needs no CORS
# entry. These origins are for running `npm run dev` in web/ against this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.DASHBOARD_API, *settings.dev_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every endpoint lives under /api, which leaves the root namespace to the
# dashboard: /live/, /issues/, /schedules/, /fix/. Without the prefix the API
# owned /issues and /schedules at the root and matched them before the static
# mount, so those pages could not be served from the root at all.
API_PREFIX = "/api"

for r in (crawlers.router, schedules.router, issues.router, autofix.router):
    app.include_router(r, prefix=API_PREFIX, dependencies=[Depends(require_token)])


@app.get("/health")
def health():
    """Unauthenticated liveness check. Stays at the root, where load balancers
    and `systemctl` health probes expect it, and collides with no page."""
    return {"ok": True}


# The dashboard: `cd web && npm run build` writes static files to web/out.
#
# Mounted last and at the root, so it serves /, /live/, /issues/ and the rest,
# while every /api route above still matches first. Left unmounted when the
# build is absent, so the API still starts on its own.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "out")

if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="dashboard")
