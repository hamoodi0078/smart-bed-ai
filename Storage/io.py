from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Iterator

import aiofiles
import aiofiles.os
from loguru import logger as _LOG

_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05
_ATOMIC_REPLACE_RETRIES = 6
_ATOMIC_REPLACE_BASE_DELAY_SECONDS = 0.05
_LOCAL_LOCKS_GUARD = Lock()
_LOCAL_LOCKS: dict[str, RLock] = {}


if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _normalize_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def confine_path(base_dir: Path, candidate: str | Path) -> Path:
    """Resolve *candidate* and verify it stays inside *base_dir*.

    Raises ``ValueError`` if the resolved path escapes the trusted directory.
    This is the project-wide defence against SonarCloud path-traversal findings:
      1. Resolve *base_dir* to an absolute canonical path.
      2. Resolve *candidate* — try as-is first, then joined to base.
      3. Verify the result is equal to or a descendant of the base.

    Both absolute and relative candidates are supported.
    """
    base = Path(base_dir).resolve()

    # Strategy 1: resolve the candidate directly (handles absolute paths and
    # relative paths that already include the base directory name).
    target = Path(candidate).resolve()
    if target == base or str(target).startswith(str(base) + os.sep):
        return target

    # Strategy 2: join to base_dir (handles bare filenames like "state.json").
    target = (base / Path(candidate)).resolve()
    if target == base or str(target).startswith(str(base) + os.sep):
        return target

    raise ValueError(f"Path traversal blocked: {target} is outside allowed directory {base}")


def _local_lock_for(path: Path) -> RLock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _LOCAL_LOCKS[key] = lock
        return lock


def _acquire_file_lock(handle, deadline: float) -> None:
    while True:
        try:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (BlockingIOError, OSError):
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out acquiring JSON lock")
            time.sleep(_LOCK_POLL_SECONDS)


def _release_file_lock(handle) -> None:
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _path_io_lock(path: Path) -> Iterator[None]:
    lock_file_path = path.with_name(f".{path.name}.lock")
    local_lock = _local_lock_for(path)
    with local_lock:
        with lock_file_path.open("a+b") as lock_handle:
            # Lock one byte; file-backed lock works across processes on Linux/Windows.
            lock_handle.seek(0)
            lock_handle.write(b"\0")
            lock_handle.flush()
            deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
            _acquire_file_lock(lock_handle, deadline)
            try:
                yield
            finally:
                _release_file_lock(lock_handle)


def _quarantine_corrupt_file(path: Path, reason: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    corrupt_path = path.with_name(f"{path.stem}.corrupt.{stamp}{path.suffix}")
    try:
        os.replace(str(path), str(corrupt_path))
        _LOG.error(
            "json_corrupt_file_quarantined path={} backup={} reason={}", path, corrupt_path, reason
        )
    except OSError as exc:
        _LOG.error(
            "json_corrupt_file_detected path={} reason={} quarantine_error={}", path, reason, exc
        )


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _should_retry_atomic_replace(exc: OSError) -> bool:
    if os.name != "nt":
        return False
    winerror = int(getattr(exc, "winerror", 0) or 0)
    # 5=Access denied, 32=Sharing violation while another process/thread holds a handle.
    return winerror in {5, 32}


async def async_locked_read_json(path: str | Path) -> dict:
    """Thread-offloaded read — safe for concurrent async callers (lock held in thread)."""
    return await asyncio.to_thread(locked_read_json, path)


async def async_atomic_write_json(path: str | Path, data: dict) -> None:
    """Thread-offloaded atomic write — safe for concurrent async callers."""
    await asyncio.to_thread(atomic_write_json, path, data)


# ── aiofiles-based helpers for simple cache files (no cross-process locking) ──


async def async_read_text(path: str | Path) -> str:
    """Read a text file asynchronously. Returns empty string if missing."""
    p = Path(path)
    try:
        async with aiofiles.open(p, encoding="utf-8") as fh:
            return await fh.read()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        _LOG.warning("async_read_text failed path={} error={}", p, exc)
        return ""


async def async_read_json_simple(path: str | Path) -> dict:
    """Read a JSON cache file asynchronously without file-level locking.

    Use for cache files where occasional read-write races are acceptable
    (prayer times cache, hadith cache, etc.). For authoritative data
    use async_locked_read_json instead.
    """
    raw = await async_read_text(path)
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError as exc:
        _LOG.warning("async_read_json_simple decode error path={} error={}", path, exc)
        return {}


async def async_write_json_simple(path: str | Path, data: dict) -> None:
    """Write a JSON cache file asynchronously without atomic rename.

    Safe for cache files. For authoritative data use async_atomic_write_json.
    """
    if not isinstance(data, dict):
        raise TypeError("async_write_json_simple expects a dict")
    p = Path(path)
    await aiofiles.os.makedirs(str(p.parent), exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    async with aiofiles.open(p, "w", encoding="utf-8") as fh:
        await fh.write(payload)


def locked_read_json(path: str | Path) -> dict:
    json_path = _normalize_path(path)
    with _path_io_lock(json_path):
        if not json_path.exists():
            return {}
        try:
            raw = json_path.read_text(encoding="utf-8")
        except OSError as exc:
            _LOG.error("json_read_failed path={} error={}", json_path, exc)
            return {}

        if not raw.strip():
            return {}

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            _quarantine_corrupt_file(json_path, f"decode_error: {exc}")
            return {}

        if not isinstance(payload, dict):
            _quarantine_corrupt_file(json_path, "root_not_object")
            return {}
        return payload


def atomic_write_json(path: str | Path, data: dict) -> None:
    if not isinstance(data, dict):
        raise TypeError("atomic_write_json expects a dict payload")

    json_path = _normalize_path(path)
    with _path_io_lock(json_path):
        tmp_path: Path | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                dir=str(json_path.parent),
                prefix=f".{json_path.name}.",
                suffix=".tmp",
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())

            replaced = False
            for attempt in range(_ATOMIC_REPLACE_RETRIES + 1):
                try:
                    os.replace(str(tmp_path), str(json_path))
                    replaced = True
                    break
                except OSError as exc:
                    if (attempt >= _ATOMIC_REPLACE_RETRIES) or (
                        not _should_retry_atomic_replace(exc)
                    ):
                        raise RuntimeError(
                            f"Unable to atomically write JSON file: {json_path}"
                        ) from exc
                    delay = _ATOMIC_REPLACE_BASE_DELAY_SECONDS * float(attempt + 1)
                    time.sleep(delay)
            if not replaced:
                raise RuntimeError(f"Unable to atomically write JSON file: {json_path}")
            _fsync_directory(json_path.parent)
        except OSError as exc:
            raise RuntimeError(f"Unable to atomically write JSON file: {json_path}") from exc
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
