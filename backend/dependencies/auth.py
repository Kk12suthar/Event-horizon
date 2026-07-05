"""Authentication dependencies for protected routes"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from utils.authentication import decode_access_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from JWT token.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["sub"]}
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    token_data = decode_access_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data


async def get_user_from_request(request: Request) -> Dict[str, Any]:
    """
    Get user data from request state (attached by authentication middleware)
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_user_from_request)):
            return {"user_id": user["sub"]}
    
    Raises:
        HTTPException: If user not found in request state
    """
    user = getattr(request.state, 'user', None)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency to ensure user is active
    Can be extended with additional checks (e.g., account disabled, email verified)
    """
    # Add additional checks here if needed
    # For example, check if user is disabled in database
    return current_user


def require_plan(required_plan: str):
    """
    Dependency factory to require specific plan level
    
    Usage:
        @router.get("/admin")
        async def admin_route(user: dict = Depends(require_plan("pro"))):
            return {"message": "Pro user only"}
    
    Args:
        required_plan: Required plan level ("demo" or "pro")
    """
    async def plan_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_plan = user.get("plan", "demo")
        
        if required_plan == "pro" and user_plan != "pro":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires a {required_plan.upper()} plan. Your current plan: {user_plan.upper()}"
            )
        
        return user
    
    return plan_checker
