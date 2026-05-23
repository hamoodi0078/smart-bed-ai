"""Unified retry policies for all external service calls.

Usage
-----
    from core.retry import RetryPolicy

    # Preset for HTTP APIs (Fitbit, Garmin, Google Calendar, etc.)
    @RetryPolicy.http_api()
    async def fetch_fitbit_data(self, ...): ...

    # Preset for database operations
    @RetryPolicy.database()
    async def insert_row(self, ...): ...

    # Custom policy
    @RetryPolicy.custom(max_attempts=5, base_delay=2.0, exceptions=(IOError,))
    async def upload_to_s3(self, ...): ...
"""

from __future__ import annotations

import logging
from typing import Type

from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

_log = logging.getLogger(__name__)

# Exceptions we should never retry (caller mistakes, bad credentials, etc.)
_NEVER_RETRY = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NotImplementedError,
    PermissionError,
)


class RetryPolicy:
    """Factory for tenacity retry decorators with project-standard presets."""

    @staticmethod
    def http_api(
        max_attempts: int = 4,
        min_wait: float = 1.0,
        max_wait: float = 30.0,
        reraise: bool = True,
    ):
        """Exponential backoff for HTTP APIs (Fitbit, Garmin, Calendar, weather).

        Retries on any exception except the never-retry set above.
        Uses random jitter to spread retries when many workers hit the same API.
        """
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(min=min_wait, max=max_wait),
            retry=retry_if_exception_type(Exception)
                  & ~retry_if_exception_type(_NEVER_RETRY),
            before_sleep=before_sleep_log(_log, logging.WARNING),
            reraise=reraise,
        )

    @staticmethod
    def database(
        max_attempts: int = 3,
        min_wait: float = 0.5,
        max_wait: float = 10.0,
        reraise: bool = True,
    ):
        """Modest backoff for transient database errors (deadlocks, conn drops)."""
        try:
            from asyncpg import PostgresConnectionError, TooManyConnectionsError
            _db_exceptions: tuple[Type[Exception], ...] = (
                PostgresConnectionError,
                TooManyConnectionsError,
                OSError,
            )
        except ImportError:
            _db_exceptions = (OSError,)

        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(_db_exceptions),
            before_sleep=before_sleep_log(_log, logging.WARNING),
            reraise=reraise,
        )

    @staticmethod
    def messaging(
        max_attempts: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 15.0,
        reraise: bool = True,
    ):
        """For FCM, SES, and Twilio SMS — short window, fail fast."""
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=2, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(Exception)
                  & ~retry_if_exception_type(_NEVER_RETRY),
            before_sleep=before_sleep_log(_log, logging.WARNING),
            reraise=reraise,
        )

    @staticmethod
    def storage(
        max_attempts: int = 4,
        min_wait: float = 1.0,
        max_wait: float = 60.0,
        reraise: bool = True,
    ):
        """For S3 and file I/O — larger max_wait for eventual consistency."""
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_random_exponential(min=min_wait, max=max_wait),
            retry=retry_if_exception_type(Exception)
                  & ~retry_if_exception_type(_NEVER_RETRY),
            before_sleep=before_sleep_log(_log, logging.WARNING),
            reraise=reraise,
        )

    @staticmethod
    def custom(
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_wait: float = 30.0,
        exceptions: tuple[Type[Exception], ...] = (Exception,),
        reraise: bool = True,
    ):
        """Fully configurable policy for one-off cases."""
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=base_delay, min=base_delay, max=max_wait),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(_log, logging.WARNING),
            reraise=reraise,
        )


async def retry_call(
    coro_fn,
    *args,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    **kwargs,
):
    """Imperative async retry helper for callers that can't use decorators.

    Example::

        result = await retry_call(client.fetch, user_id, max_attempts=4)
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_random_exponential(min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(_log, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            return await coro_fn(*args, **kwargs)
