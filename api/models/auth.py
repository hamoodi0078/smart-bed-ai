"""Pydantic models for authentication API requests and responses."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    timezone: str = Field(default="Asia/Kuwait", max_length=50)
    locale: str = Field(default="en", max_length=10)

    @validator("password")
    def validate_password_strength(cls, v):
        """Validate password has numbers and special characters."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Token response for login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class UserResponse(BaseModel):
    """User profile response."""

    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    timezone: str
    locale: str
    subscription_status: str
    created_at: datetime
    last_login: datetime | None

    class Config:
        from_attributes = True


class PasswordChangeRequest(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @validator("new_password")
    def validate_password_strength(cls, v):
        """Validate password has numbers and special characters."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "RefreshRequest",
    "TokenResponse",
    "UserResponse",
    "PasswordChangeRequest",
]
