"""Data models for authentication"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class SignupRequest(BaseModel):
    """Sign-up request model"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1)
    plan: Optional[str] = Field(default="pro", pattern="^(demo|pro)$")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com",
                "password": "securepassword123",
                "full_name": "John Doe",
                "plan": "pro"
            }
        }


class SigninRequest(BaseModel):
    """Sign-in request model"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com",
                "password": "securepassword123"
            }
        }


class AuthResponse(BaseModel):
    """Authentication response model"""
    success: bool
    message: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: Optional[str] = "bearer"
    user: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Authentication successful",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "uid": "abc123",
                    "email": "user@company.com",
                    "name": "John Doe",
                    "plan": "pro"
                }
            }
        }


class UserProfile(BaseModel):
    """User profile model"""
    uid: str
    email: str
    name: str
    picture: Optional[str] = ""
    plan: str = "pro"
    tenant: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "uid": "abc123",
                "email": "user@company.com",
                "name": "John Doe",
                "picture": "",
                "plan": "pro",
                "tenant": "company-com",
                "created_at": "2024-01-01T00:00:00"
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "message": "Invalid credentials",
                "error_code": "INVALID_PASSWORD"
            }
        }


class TokenResponse(BaseModel):
    """Token response model with refresh token support"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token expiration in seconds
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800
            }
        }


class RefreshRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class ForgotPasswordRequest(BaseModel):
    """Forgot password request model"""
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com"
            }
        }


class ResetPasswordRequest(BaseModel):
    """Reset password request model"""
    oob_code: str = Field(..., description="The out-of-band code sent to the user's email")
    new_password: str = Field(..., min_length=6)

    class Config:
        json_schema_extra = {
            "example": {
                "oob_code": "some-firebase-oob-code",
                "new_password": "newsecurepassword123"
            }
        }
