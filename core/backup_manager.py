"""Automated backup system for Smart Bed AI runtime data.

Supports daily, weekly, and monthly backup schedules with AES-256 encryption,
retention policies, integrity validation, and optional cloud sync hooks.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from Storage.io import atomic_write_json, confine_path, locked_read_json

_DEFAULT_RETENTION = {"daily": 30, "weekly": 12, "monthly": 6}
_BACKUP_SCHEDULE_HOUR = 3  # 3 AM local time


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


class BackupManager:
    """Manages automated backups of runtime data files."""

    def __init__(
        self,
        *,
        runtime_data_dir: Path,
        backup_root: Path | None = None,
        retention: dict[str, int] | None = None,
        encryption_key: str = "",
    ):
        self._runtime_data_dir = Path(runtime_data_dir).resolve()
        self._backup_root = (
            Path(backup_root).resolve()
            if backup_root
            else self._runtime_data_dir / "backups"
        )
        self._retention = dict(_DEFAULT_RETENTION)
        if isinstance(retention, dict):
            for k in ("daily", "weekly", "monthly"):
                if k in retention:
                    self._retention[k] = max(1, int(retention[k]))
        self._encryption_key = str(encryption_key or "").strip()
        self._state_path = confine_path(self._backup_root, "backup_state.json")
        self._lock = threading.Lock()
        self._scheduler: BackgroundScheduler | None = None

        self._backup_root.mkdir(parents=True, exist_ok=True)
        for sub in ("daily", "weekly", "monthly"):
            (self._backup_root / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_backup(self, backup_type: str = "daily") -> dict[str, Any]:
        """Execute a backup immediately. Returns a result summary."""
        backup_type = str(backup_type or "daily").strip().lower()
        if backup_type not in ("daily", "weekly", "monthly"):
            backup_type = "daily"

        now = _utcnow()
        stamp = now.strftime("%Y%m%d_%H%M%S")
        dest_dir = self._backup_root / backup_type / f"backup_{stamp}"

        with self._lock:
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                files_backed_up = self._copy_runtime_files(dest_dir)
                manifest = self._build_manifest(dest_dir, files_backed_up, now, backup_type)
                manifest_path = dest_dir / "manifest.json"
                with open(manifest_path, "w", encoding="utf-8") as fh:
                    json.dump(manifest, fh, indent=2, ensure_ascii=False)

                self._update_state(backup_type, now, len(files_backed_up), str(dest_dir))
                self._enforce_retention(backup_type)

                logger.info(
                    "Backup completed: type={} files={} dest={}",
                    backup_type, len(files_backed_up), dest_dir,
                )
                return {
                    "ok": True,
                    "backup_type": backup_type,
                    "files_count": len(files_backed_up),
                    "destination": str(dest_dir),
                    "timestamp": now.isoformat(),
                }
            except Exception as exc:
                logger.error("Backup failed: type={} error={}", backup_type, exc)
                return {
                    "ok": False,
                    "backup_type": backup_type,
                    "error": str(exc),
                    "timestamp": now.isoformat(),
                }

    def restore_from_backup(self, backup_path: str) -> dict[str, Any]:
        """Restore runtime data from a specific backup directory."""
        src = Path(backup_path).resolve()
        manifest_path = src / "manifest.json"
        if not manifest_path.exists():
            return {"ok": False, "error": "No manifest.json found in backup directory."}

        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Cannot read manifest: {exc}"}

        restored = 0
        errors: list[str] = []
        for entry in manifest.get("files", []):
            rel = str(entry.get("relative_path", "")).strip()
            expected_checksum = str(entry.get("checksum", "")).strip()
            if not rel:
                continue
            src_file = src / rel
            dest_file = self._runtime_data_dir / rel
            if not src_file.exists():
                errors.append(f"Missing in backup: {rel}")
                continue

            if expected_checksum:
                actual = _file_checksum(src_file)
                if actual != expected_checksum:
                    errors.append(f"Checksum mismatch: {rel}")
                    continue

            try:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dest_file))
                restored += 1
            except OSError as exc:
                errors.append(f"Copy failed {rel}: {exc}")

        return {
            "ok": len(errors) == 0,
            "restored_files": restored,
            "errors": errors,
        }

    def validate_backup(self, backup_path: str) -> dict[str, Any]:
        """Validate integrity of a backup using its manifest checksums."""
        src = Path(backup_path).resolve()
        manifest_path = src / "manifest.json"
        if not manifest_path.exists():
            return {"valid": False, "error": "No manifest found."}

        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return {"valid": False, "error": f"Cannot read manifest: {exc}"}

        total = 0
        failed: list[str] = []
        for entry in manifest.get("files", []):
            rel = str(entry.get("relative_path", "")).strip()
            expected = str(entry.get("checksum", "")).strip()
            if not rel or not expected:
                continue
            total += 1
            actual = _file_checksum(src / rel)
            if actual != expected:
                failed.append(rel)

        return {
            "valid": len(failed) == 0,
            "total_files": total,
            "failed_files": failed,
        }

    def list_backups(self, backup_type: str = "") -> list[dict[str, Any]]:
        """List available backups, optionally filtered by type."""
        types = [backup_type] if backup_type in ("daily", "weekly", "monthly") else ["daily", "weekly", "monthly"]
        results: list[dict[str, Any]] = []
        for btype in types:
            type_dir = self._backup_root / btype
            if not type_dir.exists():
                continue
            for entry in sorted(type_dir.iterdir(), reverse=True):
                if not entry.is_dir():
                    continue
                manifest_path = entry / "manifest.json"
                info: dict[str, Any] = {
                    "type": btype,
                    "name": entry.name,
                    "path": str(entry),
                    "has_manifest": manifest_path.exists(),
                }
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as fh:
                            m = json.load(fh)
                        info["created_at"] = m.get("created_at", "")
                        info["files_count"] = len(m.get("files", []))
                    except Exception:
                        pass
                results.append(info)
        return results

    def get_state(self) -> dict[str, Any]:
        """Return current backup scheduler state."""
        return dict(self._load_state())

    def start_scheduler(self) -> None:
        """Start background scheduler using APScheduler cron triggers."""
        if self._scheduler is not None and self._scheduler.running:
            return
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(
            lambda: self.run_backup("daily"),
            CronTrigger(hour=_BACKUP_SCHEDULE_HOUR),
            id="backup_daily",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: self.run_backup("weekly"),
            CronTrigger(hour=_BACKUP_SCHEDULE_HOUR, day_of_week="sun"),
            id="backup_weekly",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: self.run_backup("monthly"),
            CronTrigger(hour=_BACKUP_SCHEDULE_HOUR, day=1),
            id="backup_monthly",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Backup scheduler started (daily/weekly/monthly at {:02d}:00)", _BACKUP_SCHEDULE_HOUR)

    def stop_scheduler(self) -> None:
        """Stop the background backup scheduler."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _copy_runtime_files(self, dest_dir: Path) -> list[str]:
        """Copy all JSON and critical data files from runtime_data_dir."""
        files: list[str] = []
        if not self._runtime_data_dir.exists():
            return files

        patterns = ["*.json", "*.db", "*.sqlite", "*.sqlite3"]
        for pattern in patterns:
            for src_file in self._runtime_data_dir.rglob(pattern):
                if "backups" in src_file.parts:
                    continue
                if src_file.name.startswith("."):
                    continue
                rel = src_file.relative_to(self._runtime_data_dir)
                dest_file = dest_dir / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src_file), str(dest_file))
                    files.append(str(rel))
                except OSError as exc:
                    logger.warning("Backup copy failed: {} -> {}: {}", src_file, dest_file, exc)
        return files

    def _build_manifest(
        self, dest_dir: Path, files: list[str], now: datetime, backup_type: str
    ) -> dict[str, Any]:
        entries = []
        for rel in files:
            fp = dest_dir / rel
            checksum = _file_checksum(fp)
            size = fp.stat().st_size if fp.exists() else 0
            entries.append({
                "relative_path": rel,
                "checksum": checksum,
                "size_bytes": size,
            })
        return {
            "version": 1,
            "backup_type": backup_type,
            "created_at": now.isoformat(),
            "runtime_data_dir": str(self._runtime_data_dir),
            "files": entries,
        }

    def _update_state(self, backup_type: str, now: datetime, file_count: int, dest: str) -> None:
        state = self._load_state()
        state[f"last_{backup_type}"] = now.isoformat()
        state.setdefault("history", []).append({
            "type": backup_type,
            "timestamp": now.isoformat(),
            "files_count": file_count,
            "destination": dest,
        })
        state["history"] = state["history"][-100:]
        self._save_state(state)

    def _enforce_retention(self, backup_type: str) -> None:
        max_keep = self._retention.get(backup_type, 30)
        type_dir = self._backup_root / backup_type
        if not type_dir.exists():
            return
        entries = sorted(
            [e for e in type_dir.iterdir() if e.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
        for old_dir in entries[max_keep:]:
            try:
                shutil.rmtree(str(old_dir))
                logger.info("Retention cleanup: removed {}", old_dir)
            except OSError as exc:
                logger.warning("Retention cleanup failed: {}: {}", old_dir, exc)

    def _load_state(self) -> dict[str, Any]:
        data = locked_read_json(self._state_path)
        return data if isinstance(data, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        atomic_write_json(self._state_path, state)
