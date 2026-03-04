from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Iterator


_LOG = logging.getLogger("storage.io")
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05
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
        _LOG.error("json_corrupt_file_quarantined path=%s backup=%s reason=%s", path, corrupt_path, reason)
    except OSError as exc:
        _LOG.error("json_corrupt_file_detected path=%s reason=%s quarantine_error=%s", path, reason, exc)


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


def locked_read_json(path: str | Path) -> dict:
    json_path = _normalize_path(path)
    with _path_io_lock(json_path):
        if not json_path.exists():
            return {}
        try:
            raw = json_path.read_text(encoding="utf-8")
        except OSError as exc:
            _LOG.error("json_read_failed path=%s error=%s", json_path, exc)
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

            os.replace(str(tmp_path), str(json_path))
            _fsync_directory(json_path.parent)
        except OSError as exc:
            raise RuntimeError(f"Unable to atomically write JSON file: {json_path}") from exc
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
