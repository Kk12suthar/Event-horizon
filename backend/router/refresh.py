"""Refresh Token Endpoint"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy.orm import Session
from database import get_db
from dataModels.authModels import TokenResponse, RefreshRequest
from utils.authentication import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    hash_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from utils.refresh_token_db import (
    store_refresh_token,
    verify_refresh_token_in_db,
    revoke_refresh_token,
    revoke_token_family
)
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token
    
    - Validates refresh token
    - Issues new access token
    - Rotates refresh token (one-time use)
    - Detects token theft attempts
    """
    try:
        # 1. Verify refresh token format
        token_payload = verify_refresh_token(payload.refresh_token)
        if not token_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
        
        # 2. Hash token for database lookup
        token_hash = hash_token(payload.refresh_token)
        
        # 3. Verify token in database
        db_token = verify_refresh_token_in_db(db, token_hash)
        if not db_token:
            # Token not found or revoked - possible theft attempt
            # Revoke entire token family
            family_id = token_payload.get("family_id")
            if family_id:
                revoke_token_family(db, family_id)
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token - please sign in again"
            )
        
        user_id = db_token["user_id"]
        family_id = db_token["family_id"]
        
        # 4. Create new access token
        token_data = {
            "sub": user_id,
        }
        new_access_token = create_access_token(token_data)
        
        # 5. Rotate refresh token (one-time use security)
        new_refresh_token, new_token_hash = create_refresh_token(user_id, family_id)
        
        # 6. Store new refresh token
        expires_at = datetime.utcnow() + timedelta(days=7)
        new_token_id = store_refresh_token(
            db=db,
            user_id=user_id,
            token_hash=new_token_hash,
            family_id=family_id,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None
        )
        
        # 7. Revoke old refresh token
        revoke_refresh_token(db, token_hash, replaced_by=new_token_id)
        
        # 8. Return new tokens
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )


@router.post("/logout")
async def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    """
    Logout user by revoking refresh token
    """
    try:
        token_hash = hash_token(payload.refresh_token)
        revoke_refresh_token(db, token_hash)
        
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        print(f"Error during logout: {e}")
        # Don't fail logout even if token revocation fails
        return {"success": True, "message": "Logged out"}
