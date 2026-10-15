import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# auto_error=False so a missing header raises our own 401 rather than a 403.
# Declaring the scheme is what puts the Authorize button in /docs -- with a plain
# Header dependency the OpenAPI spec has no securitySchemes and the button is absent.
bearer = HTTPBearer(auto_error=False, description="Paste API_TOKEN (no 'Bearer ' prefix)")


def require_token(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    token = (cred.credentials if cred else "").strip()
    if not hmac.compare_digest(token, settings.API_TOKEN):
        raise HTTPException(401, "invalid token")
