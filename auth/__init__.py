"""Authentication package providing JWT token handling and middleware."""

from auth.jwt_handler import (
    create_access_token,
    decode_access_token,
    decode_unverified,
    is_jwt,
    JWTError,
    ExpiredSignatureError,
)
from auth.middleware import (
    get_current_user,
    get_current_user_optional,
    require_role,
    security,
)

__all__ = [
    # JWT functions
    "create_access_token",
    "decode_access_token",
    "decode_unverified",
    "is_jwt",
    "JWTError",
    "ExpiredSignatureError",
    # Middleware
    "get_current_user",
    "get_current_user_optional",
    "require_role",
    "security",
]
