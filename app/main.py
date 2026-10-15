"""burgerindex-ops API.  Run: uvicorn app.main:app --host 0.0.0.0 --port 8090"""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .config import settings
from .routers import autofix, crawlers, schedules, triage

app = FastAPI(title="burgerindex-ops", version="0.1.0")

# The dashboard is served from this app (see the mount below), so it needs no CORS
# entry. These origins are for running `npm run dev` in web/ against this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.DASHBOARD_API, *settings.dev_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (crawlers.router, schedules.router, triage.router, autofix.router):
    app.include_router(r, dependencies=[Depends(require_token)])


@app.get("/health")
def health():
    return {"ok": True}


# The dashboard: `cd web && npm run build` writes static files to web/out.
#
# It is served under /ui, not /, because the API owns /triage, /schedules,
# /crawlers, /spiders and /server at the root and those routes match first --
# mounting the pages at / would make a bare /triage return 401 JSON instead of
# the page. Left unmounted when the build has not been run, so the API still
# starts on its own.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "out")
DASHBOARD = "/ui"

if os.path.isdir(WEB_DIR):
    app.mount(DASHBOARD, StaticFiles(directory=WEB_DIR, html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    def dashboard_root():
        return RedirectResponse(f"{DASHBOARD}/live/")
