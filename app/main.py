"""burgerindex-ops API.  Run: uvicorn app.main:app --host 0.0.0.0 --port 8090"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_token
from .config import settings
from .routers import autofix, crawlers, schedules, triage

app = FastAPI(title="burgerindex-ops", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.DASHBOARD_API],
                   allow_methods=["*"], allow_headers=["*"])

for r in (crawlers.router, schedules.router, triage.router, autofix.router):
    app.include_router(r, dependencies=[Depends(require_token)])


@app.get("/health")
def health():
    return {"ok": True}
