"""Redis-backed circuit breaker for external service calls (voice, AI, etc.).

Replaces the file-based ``voice_circuit_reset_signal.json`` approach so that
circuit state is shared across all Gunicorn workers and survives single-worker
restarts.

States
------
CLOSED  — normal operation; calls pass through.
OPEN    — too many recent failures; calls are rejected immediately.
HALF    — cooldown elapsed; one probe call is allowed to test recovery.

Usage
-----
    from services.circuit_breaker import get_circuit_breaker

    breaker = await get_circuit_breaker("voice")

    if not await breaker.allow_request():
        raise ServiceUnavailableError("Voice circuit is open")

    try:
        result = await deepgram_call(...)
        await breaker.record_success()
    except Exception:
        await breaker.record_failure()
        raise
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "circuit:"
_DEFAULT_FAILURE_THRESHOLD = 3
_DEFAULT_RECOVERY_TIMEOUT = 60.0


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF = "half"


# ── In-memory fallback (single-process) ──────────────────────────────────────

class _InMemoryCircuit:
    def __init__(
        self,
        name: str,
        failure_threshold: int,
        recovery_timeout: float,
    ) -> None:
        self._name = name
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    async def state(self) -> CircuitState:
        async with self._lock:
            return self._current_state()

    def _current_state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self._recovery_timeout:
                self._state = CircuitState.HALF
        return self._state

    async def allow_request(self) -> bool:
        async with self._lock:
            s = self._current_state()
            if s == CircuitState.CLOSED:
                return True
            if s == CircuitState.HALF:
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED
            logger.info("Circuit %s: closed after recovery", self._name)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if self._state == CircuitState.HALF or self._failures >= self._threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit %s: OPEN after %d failures", self._name, self._failures
                )

    async def force_reset(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED
            logger.info("Circuit %s: force-reset to CLOSED", self._name)


# ── Redis-backed circuit ──────────────────────────────────────────────────────

class _RedisCircuit:
    def __init__(
        self,
        name: str,
        redis_client,
        failure_threshold: int,
        recovery_timeout: float,
    ) -> None:
        self._name = name
        self._redis = redis_client
        self._threshold = failure_threshold
        self._recovery_timeout = int(recovery_timeout)
        self._key_state = f"{_REDIS_KEY_PREFIX}{name}:state"
        self._key_failures = f"{_REDIS_KEY_PREFIX}{name}:failures"
        self._key_opened_at = f"{_REDIS_KEY_PREFIX}{name}:opened_at"

    async def state(self) -> CircuitState:
        raw = await self._redis.get(self._key_state)
        return CircuitState(raw) if raw in (s.value for s in CircuitState) else CircuitState.CLOSED

    async def allow_request(self) -> bool:
        s = await self.state()
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.OPEN:
            opened_raw = await self._redis.get(self._key_opened_at)
            if opened_raw:
                elapsed = time.time() - float(opened_raw)
                if elapsed >= self._recovery_timeout:
                    await self._redis.set(self._key_state, CircuitState.HALF.value)
                    return True
            return False
        return True  # HALF — allow one probe

    async def record_success(self) -> None:
        pipe = self._redis.pipeline()
        pipe.set(self._key_state, CircuitState.CLOSED.value)
        pipe.delete(self._key_failures)
        pipe.delete(self._key_opened_at)
        await pipe.execute()
        logger.info("Circuit %s: closed after recovery", self._name)

    async def record_failure(self) -> None:
        failures = await self._redis.incr(self._key_failures)
        await self._redis.expire(self._key_failures, self._recovery_timeout * 10)
        current = await self.state()
        if current == CircuitState.HALF or int(failures) >= self._threshold:
            pipe = self._redis.pipeline()
            pipe.set(self._key_state, CircuitState.OPEN.value)
            pipe.set(self._key_opened_at, str(time.time()))
            pipe.expire(self._key_state, self._recovery_timeout * 10)
            pipe.expire(self._key_opened_at, self._recovery_timeout * 10)
            await pipe.execute()
            logger.warning(
                "Circuit %s: OPEN after %d failures", self._name, failures
            )

    async def force_reset(self) -> None:
        pipe = self._redis.pipeline()
        pipe.set(self._key_state, CircuitState.CLOSED.value)
        pipe.delete(self._key_failures)
        pipe.delete(self._key_opened_at)
        await pipe.execute()
        logger.info("Circuit %s: force-reset to CLOSED", self._name)


# ── Factory ───────────────────────────────────────────────────────────────────

_circuits: dict[str, _RedisCircuit | _InMemoryCircuit] = {}
_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    import os
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await client.ping()
        _redis_client = client
        logger.info("Circuit breaker: using Redis backend")
        return _redis_client
    except Exception as exc:
        logger.warning("Circuit breaker: Redis unavailable (%s), using in-memory backend", exc)
        return None


async def get_circuit_breaker(
    name: str,
    failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
    recovery_timeout: float = _DEFAULT_RECOVERY_TIMEOUT,
) -> _RedisCircuit | _InMemoryCircuit:
    """Return (creating if necessary) a circuit breaker for *name*.

    Uses Redis if available, falls back to in-memory (per-process) otherwise.
    """
    if name in _circuits:
        return _circuits[name]

    redis = await _get_redis()
    if redis is not None:
        circuit: _RedisCircuit | _InMemoryCircuit = _RedisCircuit(
            name, redis, failure_threshold, recovery_timeout
        )
    else:
        circuit = _InMemoryCircuit(name, failure_threshold, recovery_timeout)

    _circuits[name] = circuit
    return circuit


async def reset_circuit(name: str) -> None:
    """Force-reset a named circuit to CLOSED state."""
    if name in _circuits:
        await _circuits[name].force_reset()
