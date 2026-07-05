from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, status


def get_user_from_authorization(authorization: str | None) -> dict[str, Any] | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None

    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        return None

    try:
        import jwt

        return jwt.decode(token, secret, algorithms=[os.getenv("JWT_ALGORITHM", "HS256")])
    except Exception:
        return None


def require_user_from_authorization(authorization: str | None) -> dict[str, Any]:
    user = get_user_from_authorization(authorization)
    if not user or not str(user.get("sub") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

