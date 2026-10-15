import json
import os
from datetime import datetime, timezone

from ..config import settings


def audit(action: str, user: str | None, **details) -> None:
    """One JSON line per Stop / Run / Approve, so you know who did what."""
    os.makedirs(os.path.dirname(settings.AUDIT_LOG), exist_ok=True)
    with open(settings.AUDIT_LOG, "a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "action": action,
                            "user": user, **details}) + "\n")
