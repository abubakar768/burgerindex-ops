import hmac

from fastapi import Header, HTTPException

from .config import settings


def require_token(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, settings.API_TOKEN):
        raise HTTPException(401, "invalid token")
