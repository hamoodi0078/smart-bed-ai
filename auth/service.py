"""Authentication service layer for user management and token operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets

import bcrypt
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt_handler import create_access_token
from database.models import User, RefreshToken
from config import settings


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Bcrypt hashed password
        """
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: Plain text password to verify
            hashed: Bcrypt hashed password

        Returns:
            True if password matches
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception as e:
            logger.warning("Password verification failed: {}", e)
            return False

    @staticmethod
    async def create_user(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user",
    ) -> User:
        """Create a new user account.

        Args:
            db: Database session
            email: User email (will be lowercased)
            password: Plain text password (will be hashed)
            full_name: Optional full name
            role: User role (default: "user")

        Returns:
            Created user object

        Raises:
            ValueError: If email already exists
        """
        email = email.lower().strip()

        # Check if user already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise ValueError(f"User with email {email} already exists")

        # Create new user
        password_hash = AuthService.hash_password(password)

        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            is_active=True,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info("User created: email={} role={}", email, role)
        return user

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate a user by email and password.

        Args:
            db: Database session
            email: User email
            password: Plain text password

        Returns:
            User object if authentication successful, None otherwise
        """
        email = email.lower().strip()

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            logger.debug("Authentication failed: user not found email={}", email)
            return None

        if not user.is_active:
            logger.warning("Authentication failed: user inactive email={}", email)
            return None

        if not AuthService.verify_password(password, user.password_hash):
            logger.debug("Authentication failed: invalid password email={}", email)
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await db.commit()

        logger.info("User authenticated: email={} user_id={}", email, user.id)
        return user

    @staticmethod
    async def create_tokens(
        db: AsyncSession,
        user: User,
    ) -> dict[str, str | int]:
        """Create access and refresh tokens for a user.

        Args:
            db: Database session
            user: User object

        Returns:
            Dict with access_token, refresh_token, expires_in
        """
        # Create access token (15 minutes)
        access_exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        jti = secrets.token_urlsafe(32)

        access_token = create_access_token(
            user_id=user.id,
            jti=jti,
            exp=access_exp,
            email=user.email,
        )

        # Create refresh token (7 days)
        refresh_exp = datetime.now(timezone.utc) + timedelta(days=7)
        refresh_token_value = secrets.token_urlsafe(64)

        refresh_token_obj = RefreshToken(
            user_id=user.id,
            token=refresh_token_value,
            expires_at=refresh_exp,
            revoked=False,
        )

        db.add(refresh_token_obj)
        await db.commit()

        logger.debug("Tokens created for user_id={}", user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token_value,
            "expires_in": 900,  # 15 minutes in seconds
        }

    @staticmethod
    async def refresh_access_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> Optional[dict[str, str | int]]:
        """Refresh an access token using a refresh token.

        Args:
            db: Database session
            refresh_token: Refresh token value

        Returns:
            Dict with new access_token, refresh_token, expires_in, or None if invalid
        """
        # Find refresh token
        result = await db.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
        token_obj = result.scalar_one_or_none()

        if not token_obj:
            logger.debug("Refresh failed: token not found")
            return None

        if token_obj.revoked:
            logger.warning("Refresh failed: token revoked")
            return None

        if datetime.now(timezone.utc) > token_obj.expires_at:
            logger.debug("Refresh failed: token expired")
            return None

        # Get user
        result = await db.execute(select(User).where(User.id == token_obj.user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            logger.warning("Refresh failed: user not found or inactive")
            return None

        # Revoke old refresh token (token rotation)
        token_obj.revoked = True

        # Create new tokens
        tokens = await AuthService.create_tokens(db, user)

        logger.info("Tokens refreshed for user_id={}", user.id)
        return tokens

    @staticmethod
    async def revoke_refresh_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> bool:
        """Revoke a refresh token.

        Args:
            db: Database session
            refresh_token: Refresh token value

        Returns:
            True if token was revoked, False if not found
        """
        result = await db.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
        token_obj = result.scalar_one_or_none()

        if not token_obj:
            return False

        token_obj.revoked = True
        await db.commit()

        logger.info("Refresh token revoked for user_id={}", token_obj.user_id)
        return True

    @staticmethod
    async def revoke_all_user_tokens(
        db: AsyncSession,
        user_id: str,
    ) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Number of tokens revoked
        """
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        tokens = result.scalars().all()

        count = 0
        for token in tokens:
            token.revoked = True
            count += 1

        await db.commit()

        logger.info("Revoked {} tokens for user_id={}", count, user_id)
        return count


__all__ = ["AuthService"]
