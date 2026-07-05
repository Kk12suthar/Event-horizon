"""Role-based access control (RBAC) dependencies"""

from fastapi import Depends, HTTPException, status
from typing import Dict, Any, List
from dependencies.auth import get_user_from_request
from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text


async def require_role(
    allowed_roles: List[str],
    user: Dict[str, Any] = Depends(get_user_from_request),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Dependency to require specific roles
    
    NOTE: This is a standalone function, not a factory, to avoid complex dependency injection.
    For flexibility, use get_user_role() to get the role and check manually in endpoints.
    
    Args:
        allowed_roles: List of allowed role names (e.g., ["ADMIN", "ANALYST"])
        user: Current user from request state
        db: Database session
        
    Returns:
        User dict if authorized
        
    Raises:
        HTTPException: 403 if user doesn't have required role
    """
    user_role = await get_user_role(user, db)
    
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}. Your role: {user_role}"
        )
    
    return user


async def get_user_role(user: Dict[str, Any], db: Session) -> str:
    """
    Get user role from database
    
    SECURITY FIX-008: Fail-closed model - raises exception instead of 
    defaulting to VIEWER when role cannot be determined
    
    Args:
        user: User dict from token/request
        db: Database session
        
    Returns:
        User role (ADMIN, ANALYST, or VIEWER)
        
    Raises:
        HTTPException: If user role cannot be determined (fail-closed)
    """
    try:
        user_id = user.get("sub")
        
        if not user_id:
            # SECURITY: Fail closed - no user ID means no access
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User identification missing from token"
            )
        
        # Query user role from database
        query = text("SELECT role FROM instance01.mtd_users WHERE id = :user_id")
        result = db.execute(query, {"user_id": user_id}).fetchone()
        
        if not result:
            # SECURITY: Fail closed - user not found in database
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found in database"
            )
        
        role = result[0]
        
        # Validate role is one of the expected values
        VALID_ROLES = {"ADMIN", "ANALYST", "VIEWER"}
        if role not in VALID_ROLES:
            # SECURITY: Fail closed - invalid role in database
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid user role configuration"
            )
        
        return role
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # SECURITY: Fail closed - any unexpected error denies access
        import logging
        logging.error(f"Error fetching user role for user {user.get('sub')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to determine user permissions"
        )


def require_admin(user: Dict[str, Any] = Depends(get_user_from_request), db: Session = Depends(get_db)):
    """
    Dependency to require ADMIN role
    
    Usage:
        @router.delete("/project")
        async def delete_project(user = Depends(require_admin)):
            pass
    """
    async def check():
        return await require_role(["ADMIN"], user, db)
    return check()


def require_admin_or_analyst(user: Dict[str, Any] = Depends(get_user_from_request), db: Session = Depends(get_db)):
    """
    Dependency to require ADMIN or ANALYST role
    
    Usage:
        @router.post("/project")
        async def create_project(user = Depends(require_admin_or_analyst)):
            pass
    """
    async def check():
        return await require_role(["ADMIN", "ANALYST"], user, db)
    return check()


# Helper function for manual role checking in endpoints
async def check_user_role(user: Dict[str, Any], required_roles: List[str], db: Session) -> bool:
    """
    Check if user has one of the required roles
    
    Usage in endpoint:
        if not await check_user_role(user, ["ADMIN"], db):
            raise HTTPException(status_code=403, detail="Admin access required")
    
    Args:
        user: User dict from token/request
        required_roles: List of required roles
        db: Database session
        
    Returns:
        True if user has required role, False otherwise
    """
    user_role = await get_user_role(user, db)
    return user_role in required_roles
