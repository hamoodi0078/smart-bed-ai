"""Authentication middleware for FastAPI using JWT tokens.

Provides dependency functions to protect routes and verify user identity.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.jwt_handler import decode_access_token, JWTError, ExpiredSignatureError
from loguru import logger

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Verify JWT token and return user payload.
    
    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
        
    Returns:
        dict: Decoded token payload with user_id, email, etc.
    """
    if not credentials:
        logger.warning("Authentication attempt without credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        payload = decode_access_token(token)
        
        # Verify token type
        if payload.get("type") != "access":
            logger.warning("Invalid token type: {}", payload.get("type"))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify required fields
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("Token missing user_id (sub claim)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.debug("User authenticated: user_id={}", user_id)
        return payload
        
    except ExpiredSignatureError:
        logger.info("Expired token presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.warning("JWT verification failed: {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Verify JWT token but return None if missing (optional auth).
    
    Use this for routes that have different behavior for authenticated vs anonymous users.
    
    Returns:
        dict | None: Decoded token payload, or None if no token provided
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(*allowed_roles: str):
    """Dependency factory to enforce role-based access control.
    
    Usage:
        @router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
        async def list_users(): ...
        
    Args:
        *allowed_roles: One or more role names that are allowed access
        
    Returns:
        Dependency function that checks user role
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = current_user.get("role", "user")
        
        if user_role not in allowed_roles:
            logger.warning(
                "Access denied: user_id={} role={} required_roles={}",
                current_user.get("sub"),
                user_role,
                allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        
        logger.debug(
            "Role check passed: user_id={} role={}",
            current_user.get("sub"),
            user_role,
        )
        return current_user
    
    return role_checker


__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "require_role",
    "security",
]
