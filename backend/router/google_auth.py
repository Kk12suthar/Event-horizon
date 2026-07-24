"""Google Identity Services login for new and returning users."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from utils.authentication import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, create_refresh_token
from utils.google_identity import GoogleIdentityError, verify_google_credential
from utils.refresh_token_db import store_refresh_token


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)


class GoogleSigninRequest(BaseModel):
    credential: str = Field(..., min_length=100)
    nonce: str = Field(..., min_length=16, max_length=256)


@router.get("/google/config")
async def google_signin_config() -> dict[str, str | bool]:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    return {"enabled": bool(client_id), "client_id": client_id}


@router.post("/google")
@limiter.limit("10/minute")
async def google_signin(
    payload: GoogleSigninRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not configured.")
    try:
        claims = verify_google_credential(payload.credential, payload.nonce, client_id)
    except GoogleIdentityError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    subject = str(claims["sub"])
    email = str(claims["email"]).strip().lower()
    name = str(claims.get("name") or email.split("@", 1)[0]).strip()[:150] or "Google User"
    picture = str(claims.get("picture") or "")
    user_id, role = _upsert_google_user(db, subject=subject, email=email, name=name)

    token_data = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "plan": "demo",
        "auth_method": "google",
    }
    access_token = create_access_token(token_data)
    family_id = str(uuid.uuid4())
    refresh_token, refresh_token_hash = create_refresh_token(user_id, family_id)
    store_refresh_token(
        db=db,
        user_id=user_id,
        token_hash=refresh_token_hash,
        family_id=family_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    return {
        "success": True,
        "message": "Signed in with Google.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "token_type": "bearer",
        "user": {
            "uid": user_id,
            "id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "role": role,
            "plan": "demo",
            "auth_method": "google",
        },
    }


def _upsert_google_user(db: Session, *, subject: str, email: str, name: str) -> tuple[str, str]:
    try:
        _ensure_external_identity_table(db)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"eventhorizon:google:{subject}"},
        )
        identity = db.execute(
            text(
                """
                SELECT i.user_id, u.role
                FROM instance01.mtd_external_identity i
                JOIN instance01.mtd_users u ON u.id = i.user_id
                WHERE i.provider = 'google' AND i.subject = :subject
                """
            ),
            {"subject": subject},
        ).fetchone()
        if identity:
            user_id = str(identity._mapping["user_id"])
            role = str(identity._mapping["role"])
            db.execute(
                text("UPDATE instance01.mtd_users SET name = :name, email = :email WHERE id = :user_id"),
                {"name": name, "email": email, "user_id": user_id},
            )
        else:
            existing = db.execute(
                text("SELECT id, role FROM instance01.mtd_users WHERE LOWER(email) = :email ORDER BY id LIMIT 1"),
                {"email": email},
            ).fetchone()
            if existing:
                user_id = str(existing._mapping["id"])
                role = str(existing._mapping["role"])
            else:
                user_id = f"google:{subject}"
                role = "ANALYST"
                db.execute(
                    text(
                        """
                        INSERT INTO instance01.mtd_users(id, name, email, role)
                        VALUES (:user_id, :name, :email, :role)
                        """
                    ),
                    {"user_id": user_id, "name": name, "email": email, "role": role},
                )

        db.execute(
            text(
                """
                INSERT INTO instance01.mtd_external_identity(provider, subject, user_id, email)
                VALUES ('google', :subject, :user_id, :email)
                ON CONFLICT (provider, subject) DO UPDATE SET
                    email = EXCLUDED.email,
                    last_login_at = NOW()
                """
            ),
            {"subject": subject, "user_id": user_id, "email": email},
        )
        db.commit()
        return user_id, role
    except Exception:
        db.rollback()
        raise


def _ensure_external_identity_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS instance01.mtd_external_identity (
                provider VARCHAR(32) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                user_id VARCHAR(128) NOT NULL REFERENCES instance01.mtd_users(id) ON DELETE CASCADE,
                email VARCHAR(320) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (provider, subject)
            )
            """
        )
    )
