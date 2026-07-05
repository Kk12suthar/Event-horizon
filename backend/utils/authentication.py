"""Authentication utilities for user management"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
import os
import secrets
import hashlib
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
# SECURITY: JWT_SECRET_KEY must be set in environment variables
# No default fallback to prevent using weak secrets in production
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 180))
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days for refresh tokens


def validate_jwt_config():
    """
    Validate that JWT configuration is properly set.
    Should be called at application startup.
    
    Raises:
        ValueError: If JWT_SECRET_KEY is not configured
    """
    if not SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY environment variable is not set. "
            "This is required for secure authentication. "
            "Please set it in your .env file or environment."
        )
    
    if len(SECRET_KEY) < 32:
        raise ValueError(
            "JWT_SECRET_KEY is too short. "
            "Please use a secret key of at least 32 characters for security."
        )


def hash_token(token: str) -> str:
    """
    Hash a token for secure storage in database
    
    Args:
        token: Token to hash
        
    Returns:
        SHA-256 hash of the token
    """
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT access token
    
    Args:
        token: JWT token to decode
        
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return None
    except Exception as e:
        print(f"JWT decode error: {e}")
        return None


def validate_email(email: str) -> bool:
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength
   
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(char.isupper() for char in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(char.islower() for char in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one number"
    
    # Optional: special characters (commented out for flexibility)
    # if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in password):
    #     return False, "Password must contain at least one special character"
    
    return True, ""


def create_refresh_token(user_id: str, family_id: str) -> tuple[str, str]:
    """
    Create a refresh token with family tracking
    
    Args:
        user_id: User identifier
        family_id: Token family ID for rotation tracking
        
    Returns:
        Tuple of (token, token_hash) - token for client, hash for database
    """
    # Generate cryptographically secure random token
    token_data = {
        "sub": user_id,
        "family_id": family_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow()
    }
    
    # Create JWT refresh token
    refresh_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    # Hash for database storage
    token_hash = hash_token(refresh_token)
    
    return refresh_token, token_hash


def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a refresh token
    
    Args:
        token: Refresh token to verify
        
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            return None
            
        return payload
    except jwt.ExpiredSignatureError:
        print("Refresh token has expired")
        return None
    except jwt.JWTError as e:
        print(f"Refresh token decode error: {e}")
        return None

