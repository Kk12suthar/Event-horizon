"""Refresh token database operations"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid


def store_refresh_token(
    db: Session,
    user_id: str,
    token_hash: str,
    family_id: str,
    expires_at: datetime,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> str:
    """
    Store refresh token in database
    
    Returns:
        Token ID (UUID)
    """
    token_id = str(uuid.uuid4())
    
    query = text("""
        INSERT INTO instance01.mtd_refresh_tokens 
        (id, user_id, token_hash, family_id, expires_at, user_agent, ip_address)
        VALUES (:id, :user_id, :token_hash, :family_id, :expires_at, :user_agent, :ip_address)
    """)
    
    db.execute(query, {
        "id": token_id,
        "user_id": user_id,
        "token_hash": token_hash,
        "family_id": family_id,
        "expires_at": expires_at,
        "user_agent": user_agent,
        "ip_address": ip_address
    })
    db.commit()
    
    return token_id


def verify_refresh_token_in_db(db: Session, token_hash: str) -> Optional[Dict[str, Any]]:
    """
    Verify refresh token exists in database and is not revoked
    
    Returns:
        Token data or None if invalid
    """
    query = text("""
        SELECT id, user_id, family_id, expires_at, revoked, replaced_by_token
        FROM instance01.mtd_refresh_tokens
        WHERE token_hash = :token_hash
    """)
    
    result = db.execute(query, {"token_hash": token_hash}).fetchone()
    
    if not result:
        return None
    
    # Check if revoked
    if result.revoked:
        return None
    
    # Check if expired
    if result.expires_at < datetime.utcnow():
        return None
    
    return {
        "id": str(result.id),
        "user_id": result.user_id,
        "family_id": str(result.family_id),
        "expires_at": result.expires_at
    }


def revoke_refresh_token(db: Session, token_hash: str, replaced_by: Optional[str] = None):
    """
    Revoke a refresh token
    """
    query = text("""
        UPDATE instance01.mtd_refresh_tokens
        SET revoked = TRUE, replaced_by_token = :replaced_by
        WHERE token_hash = :token_hash
    """)
    
    db.execute(query, {"token_hash": token_hash, "replaced_by": replaced_by})
    db.commit()


def revoke_token_family(db: Session, family_id: str):
    """
    Revoke all tokens in a family (used when token theft is detected)
    """
    query = text("""
        UPDATE instance01.mtd_refresh_tokens
        SET revoked = TRUE
        WHERE family_id = CAST(:family_id AS UUID)
    """)
    
    db.execute(query, {"family_id": family_id})
    db.commit()


def cleanup_expired_tokens(db: Session):
    """
    Delete expired refresh tokens (should be run periodically)
    """
    query = text("""
        DELETE FROM instance01.mtd_refresh_tokens
        WHERE expires_at < :now
    """)
    
    db.execute(query, {"now": datetime.utcnow()})
    db.commit()
