import hashlib
import hmac
import threading
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from typing import Dict, Optional

from config import SUBSCRIPTION_DB_PATH
from Storage.io import atomic_write_json, locked_read_json
from time_utils import from_iso, to_iso, utcnow

try:
    import bcrypt
except ImportError:
    bcrypt = None


DB_PATH = SUBSCRIPTION_DB_PATH
SUBSCRIPTION_DB_SCHEMA_VERSION = 1


PLAN_DEFINITIONS = {
    "free": {
        "tier": "free",
        "monthly_price_kwd": 0.0,
        "yearly_price_kwd": 0.0,
        "daily_token_limit": 0,
        "monthly_token_cap": 0,
        "rate_limit_per_minute": 5,
        "cloud_enabled": False,
    },
    "standard": {
        "tier": "standard",
        "monthly_price_kwd": 4.9,
        "yearly_price_kwd": 49.0,
        "daily_token_limit": 120000,
        "monthly_token_cap": 3000000,
        "rate_limit_per_minute": 25,
        "cloud_enabled": True,
    },
    "pro": {
        "tier": "pro",
        "monthly_price_kwd": 9.9,
        "yearly_price_kwd": 99.0,
        "daily_token_limit": 300000,
        "monthly_token_cap": 8000000,
        "rate_limit_per_minute": 60,
        "cloud_enabled": True,
    },
}


class SubscriptionStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._io_lock = threading.RLock()
        self.db = self._load()

    @staticmethod
    def _utc_now() -> datetime:
        return utcnow()

    @staticmethod
    def _parse_datetime_utc(value: str) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return from_iso(raw)
        except Exception:
            return None

    def _now_iso(self) -> str:
        return to_iso(self._utc_now().replace(microsecond=0))

    def _load(self) -> dict:
        file_existed = self.db_path.exists()
        with self._io_lock:
            loaded = locked_read_json(self.db_path)
            data, changed = self._normalize_db(loaded)
            if changed and file_existed:
                atomic_write_json(self.db_path, data)
        return data

    @staticmethod
    def _empty() -> dict:
        return {
            "schema_version": SUBSCRIPTION_DB_SCHEMA_VERSION,
            "users": [],
            "subscriptions": [],
            "devices": [],
            "bed_profiles": [],
            "usage_daily": [],
            "usage_monthly": [],
            "user_sessions": {},
            "mobile_sessions": {},
            "mobile_refresh_sessions": {},
            "device_sessions": {},
            "device_refresh_sessions": {},
            "checkout_sessions": [],
            "payment_events": [],
            "app_releases": [],
            "firmware_releases": [],
            "device_update_reports": [],
            "admin_users": [],
            "admin_sessions": {},
            "admin_audit_logs": [],
            "incidents": [],
        }

    def _normalize_db(self, payload: dict) -> tuple[dict, bool]:
        defaults = self._empty()
        data = dict(payload) if isinstance(payload, dict) else {}
        changed = False

        schema = data.get("schema_version")
        if not isinstance(schema, int) or schema < 1:
            data["schema_version"] = SUBSCRIPTION_DB_SCHEMA_VERSION
            changed = True

        for key, default_value in defaults.items():
            if key not in data:
                data[key] = deepcopy(default_value)
                changed = True

        return data, changed

    @staticmethod
    def _version_key(version: str):
        text = str(version or "").strip().lstrip("v")
        parts = text.split(".")
        out = []
        for p in parts[:4]:
            num = "".join(ch for ch in p if ch.isdigit())
            out.append(int(num or "0"))
        while len(out) < 4:
            out.append(0)
        return tuple(out)

    def save(self):
        with self._io_lock:
            self.db, _ = self._normalize_db(self.db)
            atomic_write_json(self.db_path, self.db)

    @staticmethod
    def _is_legacy_sha256_hash(password_hash: str) -> bool:
        text = (password_hash or "").strip().lower()
        return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)

    @staticmethod
    def hash_password(password: str) -> str:
        if bcrypt is None:
            raise RuntimeError("bcrypt is required for secure password hashing")
        # bcrypt embeds a random per-password salt in the encoded hash value.
        secret = (password or "").encode("utf-8")
        return bcrypt.hashpw(secret, bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def check_password(password: str, stored_hash: str) -> bool:
        secret = (password or "").encode("utf-8")
        text = (stored_hash or "").strip()
        if not text:
            return False
        if SubscriptionStore._is_legacy_sha256_hash(text):
            legacy = hashlib.sha256(secret).hexdigest()
            return hmac.compare_digest(text.lower(), legacy)
        if bcrypt is None:
            return False
        try:
            return bcrypt.checkpw(secret, text.encode("utf-8"))
        except Exception:
            return False

    def create_user(self, email: str, password: str, name: str = "") -> dict:
        email_norm = (email or "").strip().lower()
        if any(u.get("email") == email_norm for u in self.db["users"]):
            raise ValueError("Email already registered")

        user = {
            "user_id": f"usr_{token_urlsafe(8)}",
            "email": email_norm,
            "name": (name or "").strip(),
            "password_hash": self.hash_password(password),
            "created_at": self._now_iso(),
        }
        self.db["users"].append(user)

        sub = {
            "user_id": user["user_id"],
            "tier": "free",
            "interval": "monthly",
            "status": "active",
            "payment_provider": "none",
            "price_kwd": 0.0,
            "next_renewal_at": "",
            "grace_end_at": "",
            "updated_at": self._now_iso(),
        }
        self.db["subscriptions"].append(sub)
        self.save()
        return user

    def issue_mobile_tokens(
        self,
        user_id: str,
        client_name: str = "",
        access_minutes: int = 60,
        refresh_days: int = 30,
    ) -> dict:
        access_token = token_urlsafe(32)
        refresh_token = token_urlsafe(48)
        issued_at = self._now_iso()
        access_exp = to_iso((self._utc_now() + timedelta(minutes=access_minutes)).replace(microsecond=0))
        refresh_exp = to_iso((self._utc_now() + timedelta(days=refresh_days)).replace(microsecond=0))
        session_payload = {
            "user_id": str(user_id or "").strip(),
            "client_name": str(client_name or "").strip(),
            "issued_at": issued_at,
            "revoked": False,
        }
        self.db["mobile_sessions"][access_token] = {
            **session_payload,
            "expires_at": access_exp,
        }
        self.db["mobile_refresh_sessions"][refresh_token] = {
            **session_payload,
            "expires_at": refresh_exp,
        }
        self.save()
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_at": access_exp,
            "expires_in": access_minutes * 60,
            "refresh_token": refresh_token,
            "refresh_expires_at": refresh_exp,
            "client_name": str(client_name or "").strip(),
        }

    def validate_mobile_access_token(self, token: str) -> Optional[dict]:
        sess = self.db.get("mobile_sessions", {}).get(token)
        if not sess or sess.get("revoked"):
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None or expires_at < self._utc_now():
            return None
        user = self.get_user(sess.get("user_id", ""))
        if not isinstance(user, dict):
            return None
        payload = dict(user)
        payload["client_name"] = str(sess.get("client_name", "") or "")
        payload["auth_type"] = "mobile_bearer"
        return payload

    def refresh_mobile_access_token(
        self,
        refresh_token: str,
        access_minutes: int = 60,
        refresh_days: int = 30,
    ) -> Optional[dict]:
        token_key = str(refresh_token or "").strip()
        if not token_key:
            return None
        sess = self.db.get("mobile_refresh_sessions", {}).get(token_key)
        if not sess or sess.get("revoked"):
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None or expires_at < self._utc_now():
            return None
        self.db["mobile_refresh_sessions"][token_key]["revoked"] = True
        self.save()
        return self.issue_mobile_tokens(
            user_id=str(sess.get("user_id", "") or ""),
            client_name=str(sess.get("client_name", "") or ""),
            access_minutes=access_minutes,
            refresh_days=refresh_days,
        )

    def revoke_mobile_tokens(self, access_token: str = "", refresh_token: str = "") -> bool:
        removed = False
        access_key = str(access_token or "").strip()
        refresh_key = str(refresh_token or "").strip()
        if access_key and access_key in self.db.get("mobile_sessions", {}):
            del self.db["mobile_sessions"][access_key]
            removed = True
        if refresh_key and refresh_key in self.db.get("mobile_refresh_sessions", {}):
            del self.db["mobile_refresh_sessions"][refresh_key]
            removed = True
        if removed:
            self.save()
        return removed

    def authenticate_user(self, email: str, password: str) -> Optional[dict]:
        email_norm = (email or "").strip().lower()
        for user in self.db["users"]:
            if user.get("email") != email_norm:
                continue
            stored_hash = str(user.get("password_hash", ""))
            if not self.check_password(password, stored_hash):
                continue
            # Migration path: keep legacy SHA-256 login working, then replace the
            # stored hash with bcrypt so future logins use the stronger scheme.
            if self._is_legacy_sha256_hash(stored_hash) and bcrypt is not None:
                user["password_hash"] = self.hash_password(password)
                self.save()
                return user
            return user
        return None

    def get_user(self, user_id: str) -> Optional[dict]:
        for user in self.db["users"]:
            if user.get("user_id") == user_id:
                return user
        return None

    def issue_user_token(self, user_id: str, ttl_hours: int = 24 * 7) -> dict:
        token = token_urlsafe(32)
        expires_at = to_iso((self._utc_now() + timedelta(hours=ttl_hours)).replace(microsecond=0))
        self.db["user_sessions"][token] = {
            "user_id": user_id,
            "expires_at": expires_at,
        }
        self.save()
        return {"access_token": token, "expires_at": expires_at}

    def validate_user_token(self, token: str) -> Optional[dict]:
        sess = self.db.get("user_sessions", {}).get(token)
        if not sess:
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None:
            return None
        if expires_at < self._utc_now():
            return None
        return self.get_user(sess.get("user_id", ""))

    def revoke_session(self, token: str) -> bool:
        token_key = str(token or "").strip()
        if not token_key:
            return False
        removed = False
        if token_key in self.db.get("user_sessions", {}):
            del self.db["user_sessions"][token_key]
            removed = True
        if token_key in self.db.get("admin_sessions", {}):
            del self.db["admin_sessions"][token_key]
            removed = True
        if token_key in self.db.get("mobile_sessions", {}):
            del self.db["mobile_sessions"][token_key]
            removed = True
        if token_key in self.db.get("mobile_refresh_sessions", {}):
            del self.db["mobile_refresh_sessions"][token_key]
            removed = True
        if removed:
            self.save()
        return removed

    def provision_device(self, device_id: str, claim_code: str, model: str = "", factory_secret: str = "") -> dict:
        existing = self.get_device(device_id)
        if existing:
            return existing
        device = {
            "device_id": device_id,
            "claim_code": claim_code,
            "model": model,
            "factory_secret": factory_secret,
            "owner_user_id": "",
            "status": "available",
            "current_user_id": "",
            "linked_at": "",
            "replaced_at": "",
            "last_seen_at": "",
            "created_at": self._now_iso(),
        }
        self.db["devices"].append(device)
        self.save()
        return device

    def get_device(self, device_id: str) -> Optional[dict]:
        for d in self.db["devices"]:
            if d.get("device_id") == device_id:
                return d
        return None

    @staticmethod
    def _device_belongs_to_user(device: dict, user_id: str) -> bool:
        if str(device.get("current_user_id", "")).strip() == user_id:
            return True
        # Replaced devices stay visible only to the user that previously owned
        # them. This prevents cross-user history leaks.
        status_key = str(device.get("status", "")).strip().lower()
        owner_key = str(device.get("owner_user_id", "")).strip()
        return status_key == "replaced" and owner_key == user_id

    def list_user_devices(self, user_id: str) -> list:
        user_key = str(user_id or "").strip()
        return [d for d in self.db["devices"] if self._device_belongs_to_user(d, user_key)]

    def get_active_device_for_user(self, user_id: str) -> Optional[dict]:
        for d in self.db["devices"]:
            if d.get("current_user_id") == user_id and d.get("status") == "active":
                return d
        return None

    def claim_device(self, user_id: str, device_id: str, claim_code: str) -> dict:
        device = self.get_device(device_id)
        if not device:
            raise ValueError("Device not found")
        if device.get("claim_code") != claim_code:
            raise ValueError("Invalid claim code")

        active = self.get_active_device_for_user(user_id)
        if active and active.get("device_id") != device_id:
            return {
                "linked": False,
                "transfer_required": True,
                "active_device_id": active.get("device_id"),
                "target_device_id": device_id,
            }

        device["current_user_id"] = user_id
        device["owner_user_id"] = user_id
        device["status"] = "active"
        device["linked_at"] = self._now_iso()
        self.save()
        return {
            "linked": True,
            "transfer_required": False,
            "active_device_id": device.get("device_id"),
        }

    def transfer_device(self, user_id: str, from_device_id: str, to_device_id: str) -> dict:
        old_device = self.get_device(from_device_id)
        new_device = self.get_device(to_device_id)
        if not old_device or not new_device:
            raise ValueError("Device not found")
        if old_device.get("current_user_id") != user_id:
            raise ValueError("Old device not linked to this user")

        old_device["status"] = "replaced"
        old_device["replaced_at"] = self._now_iso()
        old_device["owner_user_id"] = user_id
        old_device["current_user_id"] = ""

        new_device["status"] = "active"
        new_device["owner_user_id"] = user_id
        new_device["current_user_id"] = user_id
        new_device["linked_at"] = self._now_iso()

        revoked = 0
        for token, sess in list(self.db.get("device_sessions", {}).items()):
            if sess.get("device_id") == from_device_id and not sess.get("revoked", False):
                self.db["device_sessions"][token]["revoked"] = True
                revoked += 1

        for token, sess in list(self.db.get("device_refresh_sessions", {}).items()):
            if sess.get("device_id") == from_device_id and not sess.get("revoked", False):
                self.db["device_refresh_sessions"][token]["revoked"] = True

        self.save()
        return {
            "status": "completed",
            "old_device_status": "replaced",
            "new_device_status": "active",
            "revoked_tokens": revoked,
        }

    def issue_device_tokens(self, device_id: str, user_id: str, access_minutes: int = 15, refresh_days: int = 30) -> dict:
        access_token = token_urlsafe(32)
        refresh_token = token_urlsafe(48)
        access_exp = to_iso((self._utc_now() + timedelta(minutes=access_minutes)).replace(microsecond=0))
        refresh_exp = to_iso((self._utc_now() + timedelta(days=refresh_days)).replace(microsecond=0))

        self.db["device_sessions"][access_token] = {
            "device_id": device_id,
            "user_id": user_id,
            "expires_at": access_exp,
            "revoked": False,
        }
        self.db["device_refresh_sessions"][refresh_token] = {
            "device_id": device_id,
            "user_id": user_id,
            "expires_at": refresh_exp,
            "revoked": False,
        }
        self.save()
        return {
            "device_access_token": access_token,
            "expires_at": access_exp,
            "expires_in": access_minutes * 60,
            "refresh_token": refresh_token,
            "refresh_expires_at": refresh_exp,
        }

    def validate_device_access_token(self, token: str) -> Optional[dict]:
        sess = self.db.get("device_sessions", {}).get(token)
        if not sess or sess.get("revoked"):
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None:
            return None
        if expires_at < self._utc_now():
            return None
        return sess

    def refresh_device_access_token(self, device_id: str, refresh_token: str) -> Optional[dict]:
        sess = self.db.get("device_refresh_sessions", {}).get(refresh_token)
        if not sess or sess.get("revoked"):
            return None
        if sess.get("device_id") != device_id:
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None:
            return None
        if expires_at < self._utc_now():
            return None
        return self.issue_device_tokens(device_id=device_id, user_id=sess.get("user_id", ""))

    def get_subscription(self, user_id: str) -> dict:
        for sub in self.db["subscriptions"]:
            if sub.get("user_id") == user_id:
                return sub
        sub = {
            "user_id": user_id,
            "tier": "free",
            "interval": "monthly",
            "status": "active",
            "payment_provider": "none",
            "price_kwd": 0.0,
            "next_renewal_at": "",
            "grace_end_at": "",
            "updated_at": self._now_iso(),
        }
        self.db["subscriptions"].append(sub)
        self.save()
        return sub

    def create_checkout_session(
        self,
        user_id: str,
        tier: str,
        interval: str = "monthly",
        payment_provider: str = "paypal",
        base_url: str = "",
    ) -> dict:
        tier_norm = (tier or "free").lower().strip()
        interval_norm = (interval or "monthly").lower().strip()
        if tier_norm not in PLAN_DEFINITIONS:
            raise ValueError("Unsupported tier")
        if interval_norm not in ("monthly", "yearly"):
            raise ValueError("Unsupported interval")

        plan = PLAN_DEFINITIONS[tier_norm]
        price_kwd = plan["monthly_price_kwd"] if interval_norm == "monthly" else plan["yearly_price_kwd"]
        session_id = f"chk_{token_urlsafe(10)}"
        base = (base_url or "").rstrip("/")
        approve_url = (
            f"{base}/billing/paypal/approve?session_id={session_id}"
            if base
            else f"https://paypal.example/checkout/{session_id}"
        )

        checkout = {
            "session_id": session_id,
            "user_id": user_id,
            "tier": tier_norm,
            "interval": interval_norm,
            "payment_provider": payment_provider,
            "price_kwd": price_kwd,
            "status": "created",
            "created_at": self._now_iso(),
            "approve_url": approve_url,
        }
        self.db["checkout_sessions"].append(checkout)
        self.save()
        return checkout

    def apply_billing_webhook(
        self,
        event_type: str,
        user_id: str,
        tier: str = "",
        interval: str = "monthly",
        payment_provider: str = "paypal",
        raw_payload: Optional[dict] = None,
    ) -> dict:
        event = {
            "event_id": f"evt_{token_urlsafe(10)}",
            "event_type": event_type,
            "user_id": user_id,
            "tier": (tier or "").lower().strip(),
            "interval": (interval or "monthly").lower().strip(),
            "payment_provider": payment_provider,
            "created_at": self._now_iso(),
            "raw": raw_payload or {},
        }
        self.db["payment_events"].append(event)

        typ = (event_type or "").strip().lower()
        if typ in ("checkout.completed", "subscription.renewed", "payment.succeeded"):
            target_tier = event["tier"] or self.get_subscription(user_id).get("tier", "free")
            self.upsert_subscription(
                user_id=user_id,
                tier=target_tier,
                interval=event["interval"],
                payment_provider=payment_provider,
            )
        elif typ in ("payment.failed", "subscription.past_due"):
            self.set_subscription_grace(user_id, grace_days=7)
        elif typ in ("subscription.cancelled", "subscription.expired"):
            sub = self.get_subscription(user_id)
            sub["status"] = "inactive"
            sub["tier"] = "free"
            sub["price_kwd"] = 0.0
            sub["updated_at"] = self._now_iso()

        self.save()
        return self.get_subscription(user_id)

    def upsert_subscription(self, user_id: str, tier: str, interval: str, payment_provider: str = "paypal") -> dict:
        tier_norm = (tier or "free").lower().strip()
        interval_norm = (interval or "monthly").lower().strip()
        if tier_norm not in PLAN_DEFINITIONS:
            raise ValueError("Unsupported tier")
        if interval_norm not in ("monthly", "yearly"):
            raise ValueError("Unsupported interval")

        plan = PLAN_DEFINITIONS[tier_norm]
        sub = self.get_subscription(user_id)
        sub["tier"] = tier_norm
        sub["interval"] = interval_norm
        sub["status"] = "active"
        sub["grace_end_at"] = ""
        sub["payment_provider"] = payment_provider
        sub["price_kwd"] = plan["monthly_price_kwd"] if interval_norm == "monthly" else plan["yearly_price_kwd"]
        months = 1 if interval_norm == "monthly" else 12
        sub["next_renewal_at"] = to_iso((self._utc_now() + timedelta(days=30 * months)).replace(microsecond=0))
        sub["updated_at"] = self._now_iso()
        self.save()
        return sub

    def set_subscription_grace(self, user_id: str, grace_days: int = 7) -> dict:
        sub = self.get_subscription(user_id)
        sub["status"] = "grace"
        sub["grace_end_at"] = to_iso((self._utc_now() + timedelta(days=grace_days)).replace(microsecond=0))
        sub["updated_at"] = self._now_iso()
        self.save()
        return sub

    def enforce_grace_expiry(self, user_id: str) -> dict:
        sub = self.get_subscription(user_id)
        if sub.get("status") != "grace":
            return sub
        grace_end_at = self._parse_datetime_utc(sub.get("grace_end_at", ""))
        if grace_end_at and grace_end_at < self._utc_now():
            sub["status"] = "inactive"
            sub["tier"] = "free"
            sub["price_kwd"] = 0.0
            sub["updated_at"] = self._now_iso()
            self.save()
        return sub

    def get_usage_daily(self, user_id: str, date_iso: str) -> Dict:
        for row in self.db["usage_daily"]:
            if row.get("user_id") == user_id and row.get("date") == date_iso:
                return row
        row = {"user_id": user_id, "date": date_iso, "tokens_used": 0, "requests_used": 0}
        self.db["usage_daily"].append(row)
        self.save()
        return row

    def get_usage_monthly(self, user_id: str, month_key: str) -> Dict:
        for row in self.db["usage_monthly"]:
            if row.get("user_id") == user_id and row.get("month") == month_key:
                return row
        row = {"user_id": user_id, "month": month_key, "tokens_used": 0, "requests_used": 0}
        self.db["usage_monthly"].append(row)
        self.save()
        return row

    def add_usage(self, user_id: str, tokens: int, requests_count: int = 1):
        now = self._utc_now()
        day = now.date().isoformat()
        month_key = f"{now.year:04d}-{now.month:02d}"
        daily = self.get_usage_daily(user_id, day)
        monthly = self.get_usage_monthly(user_id, month_key)
        daily["tokens_used"] = int(daily.get("tokens_used", 0)) + max(0, int(tokens))
        daily["requests_used"] = int(daily.get("requests_used", 0)) + max(0, int(requests_count))
        monthly["tokens_used"] = int(monthly.get("tokens_used", 0)) + max(0, int(tokens))
        monthly["requests_used"] = int(monthly.get("requests_used", 0)) + max(0, int(requests_count))
        self.save()

    def get_bed_profile(self, user_id: str) -> dict:
        for row in self.db.get("bed_profiles", []):
            if row.get("user_id") == user_id:
                return row

        profile = {
            "user_id": user_id,
            "lighting": {
                "power": True,
                "color": "warm_white",
                "brightness": 60,
                "mode": "calm",
            },
            "alarms": [],
            "bluetooth": {
                "enabled": True,
                "paired_devices": [],
                "connected_device": "",
            },
            "updated_at": self._now_iso(),
        }
        self.db.setdefault("bed_profiles", []).append(profile)
        self.save()
        return profile

    def update_bed_profile(self, user_id: str, patch: dict) -> dict:
        profile = self.get_bed_profile(user_id)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(profile.get(key), dict):
                profile[key].update(value)
            else:
                profile[key] = value
        profile["updated_at"] = self._now_iso()
        self.save()
        return profile

    def build_entitlement(self, user_id: str) -> dict:
        sub = self.enforce_grace_expiry(user_id)
        plan = PLAN_DEFINITIONS.get(sub.get("tier", "free"), PLAN_DEFINITIONS["free"])

        now = self._utc_now()
        today = now.date().isoformat()
        month_key = now.strftime("%Y-%m")
        daily = self.get_usage_daily(user_id, today)
        monthly = self.get_usage_monthly(user_id, month_key)

        daily_limit = int(plan["daily_token_limit"])
        monthly_cap = int(plan["monthly_token_cap"])
        daily_used = int(daily.get("tokens_used", 0))
        monthly_used = int(monthly.get("tokens_used", 0))

        cloud_enabled = bool(plan["cloud_enabled"])
        status = sub.get("status", "active")
        if status == "inactive":
            cloud_enabled = False

        remaining_daily = max(0, daily_limit - daily_used)
        remaining_monthly = max(0, monthly_cap - monthly_used)
        over_quota = False
        if cloud_enabled and daily_limit > 0 and monthly_cap > 0:
            over_quota = daily_used >= daily_limit or monthly_used >= monthly_cap

        tier = sub.get("tier", "free")
        status_active = status in ("active", "grace")
        spotify_connect = status_active and tier in ("standard", "pro")
        spotify_control_basic = status_active and tier in ("standard", "pro")
        spotify_control_full = status_active and tier == "pro"
        spotify_allowed_actions = ["pause", "resume", "next", "previous", "volume"]
        if spotify_control_full:
            spotify_allowed_actions = ["play"] + spotify_allowed_actions

        return {
            "tier": tier,
            "status": status,
            "interval": sub.get("interval", "monthly"),
            "payment_provider": sub.get("payment_provider", "none"),
            "price_kwd": sub.get("price_kwd", 0.0),
            "next_renewal_at": sub.get("next_renewal_at", ""),
            "grace_end_at": sub.get("grace_end_at", ""),
            "cloud_enabled": cloud_enabled and (not over_quota),
            "quota_exceeded": over_quota,
            "limits": {
                "daily_token_limit": daily_limit,
                "daily_tokens_used": daily_used,
                "daily_tokens_remaining": remaining_daily,
                "monthly_token_cap": monthly_cap,
                "monthly_tokens_used": monthly_used,
                "monthly_tokens_remaining": remaining_monthly,
                "rate_limit_per_minute": int(plan["rate_limit_per_minute"]),
            },
            "features": {
                "cloud_stt": cloud_enabled and (not over_quota),
                "cloud_chat": cloud_enabled and (not over_quota),
                "cloud_tts": cloud_enabled and (not over_quota),
                "spotify_connect": spotify_connect,
                "spotify_control_basic": spotify_control_basic,
                "spotify_control_full": spotify_control_full,
                "spotify_allowed_actions": spotify_allowed_actions,
            },
        }

    def upsert_app_release(
        self,
        platform: str,
        latest_version: str,
        min_supported_version: str,
        force_update: bool = False,
        rollout_percent: int = 100,
        release_notes: str = "",
    ) -> dict:
        platform_key = (platform or "android").lower().strip()
        release = {
            "platform": platform_key,
            "latest_version": str(latest_version or "").strip(),
            "min_supported_version": str(min_supported_version or "").strip(),
            "force_update": bool(force_update),
            "rollout_percent": max(1, min(100, int(rollout_percent))),
            "release_notes": str(release_notes or "").strip(),
            "updated_at": self._now_iso(),
        }
        found = False
        for idx, row in enumerate(self.db["app_releases"]):
            if row.get("platform") == platform_key:
                self.db["app_releases"][idx] = release
                found = True
                break
        if not found:
            self.db["app_releases"].append(release)
        self.save()
        return release

    def get_app_release(self, platform: str) -> dict:
        platform_key = (platform or "android").lower().strip()
        for row in self.db["app_releases"]:
            if row.get("platform") == platform_key:
                return row
        return {
            "platform": platform_key,
            "latest_version": "1.0.0",
            "min_supported_version": "1.0.0",
            "force_update": False,
            "rollout_percent": 100,
            "release_notes": "",
            "updated_at": "",
        }

    def check_app_update(self, platform: str, current_version: str) -> dict:
        rel = self.get_app_release(platform)
        current_key = self._version_key(current_version)
        latest_key = self._version_key(rel.get("latest_version", "0.0.0"))
        min_key = self._version_key(rel.get("min_supported_version", "0.0.0"))
        required = current_key < min_key
        available = current_key < latest_key
        return {
            "platform": rel.get("platform"),
            "current_version": current_version,
            "latest_version": rel.get("latest_version"),
            "min_supported_version": rel.get("min_supported_version"),
            "update_available": available,
            "update_required": required or bool(rel.get("force_update", False)),
            "release_notes": rel.get("release_notes", ""),
        }

    def upsert_firmware_release(
        self,
        model: str,
        version: str,
        min_supported_version: str,
        rollout_percent: int = 100,
        release_notes: str = "",
        force_update: bool = False,
        download_url: str = "",
        checksum: str = "",
    ) -> dict:
        row = {
            "model": (model or "generic").strip().lower(),
            "version": str(version or "").strip(),
            "min_supported_version": str(min_supported_version or "").strip(),
            "rollout_percent": max(1, min(100, int(rollout_percent))),
            "release_notes": str(release_notes or "").strip(),
            "force_update": bool(force_update),
            "download_url": str(download_url or "").strip(),
            "checksum": str(checksum or "").strip(),
            "updated_at": self._now_iso(),
        }
        found = False
        for idx, cur in enumerate(self.db["firmware_releases"]):
            if cur.get("model") == row["model"]:
                self.db["firmware_releases"][idx] = row
                found = True
                break
        if not found:
            self.db["firmware_releases"].append(row)
        self.save()
        return row

    def get_firmware_release(self, model: str) -> Optional[dict]:
        key = (model or "generic").strip().lower()
        for row in self.db["firmware_releases"]:
            if row.get("model") == key:
                return row
        return None

    def check_device_update(self, device_id: str, current_version: str, model: str = "") -> dict:
        device = self.get_device(device_id)
        if not device:
            raise ValueError("Device not found")
        model_key = (model or device.get("model") or "generic").strip().lower()
        rel = self.get_firmware_release(model_key)
        if not rel:
            return {
                "device_id": device_id,
                "model": model_key,
                "update_available": False,
                "update_required": False,
                "latest_version": current_version,
            }

        current_key = self._version_key(current_version)
        latest_key = self._version_key(rel.get("version", "0.0.0"))
        min_key = self._version_key(rel.get("min_supported_version", "0.0.0"))
        update_available = current_key < latest_key
        update_required = current_key < min_key or bool(rel.get("force_update", False))
        return {
            "device_id": device_id,
            "model": model_key,
            "current_version": current_version,
            "latest_version": rel.get("version", ""),
            "min_supported_version": rel.get("min_supported_version", ""),
            "update_available": update_available,
            "update_required": update_required,
            "rollout_percent": int(rel.get("rollout_percent", 100)),
            "download_url": rel.get("download_url", ""),
            "checksum": rel.get("checksum", ""),
            "release_notes": rel.get("release_notes", ""),
        }

    def record_device_update_report(self, device_id: str, from_version: str, to_version: str, status: str, details: str = "") -> dict:
        row = {
            "report_id": f"upd_{token_urlsafe(10)}",
            "device_id": device_id,
            "from_version": from_version,
            "to_version": to_version,
            "status": status,
            "details": details,
            "created_at": self._now_iso(),
        }
        self.db["device_update_reports"].append(row)
        self.save()
        return row

    def get_admin_user(self, user_id: str) -> Optional[dict]:
        for row in self.db.get("admin_users", []):
            if row.get("user_id") == user_id:
                return row
        return None

    def upsert_admin_user(self, user_id: str, email: str, role: str = "viewer", status: str = "active") -> dict:
        role_key = (role or "viewer").strip().lower()
        # Owner remains a valid stored role, but it should only be assigned by
        # a trusted manual/secure provisioning flow, not public auth paths.
        if role_key not in ("owner", "admin", "support", "ops", "finance", "viewer"):
            role_key = "viewer"
        status_key = "active" if (status or "active").strip().lower() != "disabled" else "disabled"

        row = {
            "admin_id": f"adm_{token_urlsafe(8)}",
            "user_id": user_id,
            "email": (email or "").strip().lower(),
            "role": role_key,
            "status": status_key,
            "updated_at": self._now_iso(),
        }
        found = False
        for idx, cur in enumerate(self.db.get("admin_users", [])):
            if cur.get("user_id") == user_id:
                row["admin_id"] = cur.get("admin_id") or row["admin_id"]
                row["updated_at"] = self._now_iso()
                self.db["admin_users"][idx] = row
                found = True
                break
        if not found:
            self.db["admin_users"].append(row)
        self.save()
        return row

    def ensure_admin_for_login(self, user: dict) -> dict:
        existing = self.get_admin_user(user.get("user_id", ""))
        if existing:
            return existing
        # Bootstrap flow:
        # - Public accounts can appear in admin_users as "viewer" only.
        # - "owner" must be assigned manually or by a dedicated secure setup path,
        #   never inferred from "first admin login".
        return self.upsert_admin_user(
            user_id=user.get("user_id", ""),
            email=user.get("email", ""),
            role="viewer",
            status="active",
        )

    def issue_admin_token(self, user_id: str, role: str, ttl_hours: int = 12) -> dict:
        token = token_urlsafe(36)
        expires_at = to_iso((self._utc_now() + timedelta(hours=ttl_hours)).replace(microsecond=0))
        self.db["admin_sessions"][token] = {
            "user_id": user_id,
            "role": (role or "viewer").strip().lower(),
            "expires_at": expires_at,
            "revoked": False,
        }
        self.save()
        return {"access_token": token, "expires_at": expires_at}

    def validate_admin_token(self, token: str) -> Optional[dict]:
        sess = self.db.get("admin_sessions", {}).get(token)
        if not sess or bool(sess.get("revoked", False)):
            return None
        expires_at = self._parse_datetime_utc(sess.get("expires_at", ""))
        if expires_at is None:
            return None
        if expires_at < self._utc_now():
            return None
        admin_user = self.get_admin_user(sess.get("user_id", ""))
        if not admin_user:
            return None
        if (admin_user.get("status") or "active") != "active":
            return None
        return {
            "user_id": sess.get("user_id", ""),
            "role": (admin_user.get("role") or "viewer").strip().lower(),
            "email": admin_user.get("email", ""),
            "expires_at": sess.get("expires_at", ""),
        }

    def add_admin_audit_log(
        self,
        actor_user_id: str,
        actor_role: str,
        action: str,
        resource: str,
        resource_id: str = "",
        details: Optional[dict] = None,
    ) -> dict:
        row = {
            "event_id": f"audit_{token_urlsafe(10)}",
            "actor_user_id": actor_user_id,
            "actor_role": (actor_role or "viewer").strip().lower(),
            "action": str(action or "").strip(),
            "resource": str(resource or "").strip(),
            "resource_id": str(resource_id or "").strip(),
            "details": details or {},
            "created_at": self._now_iso(),
        }
        self.db["admin_audit_logs"].append(row)
        self.save()
        return row

    def list_admin_audit_logs(self, limit: int = 100) -> list:
        lim = max(1, min(500, int(limit)))
        rows = list(self.db.get("admin_audit_logs", []))
        rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return rows[:lim]

    def list_fleet_devices(self, status: str = "", model: str = "", limit: int = 200) -> list:
        status_key = (status or "").strip().lower()
        model_key = (model or "").strip().lower()
        out = []
        for d in self.db.get("devices", []):
            cur_status = (d.get("status") or "").strip().lower()
            cur_model = (d.get("model") or "").strip().lower()
            if status_key and cur_status != status_key:
                continue
            if model_key and cur_model != model_key:
                continue
            out.append(
                {
                    "device_id": d.get("device_id", ""),
                    "model": d.get("model", ""),
                    "status": d.get("status", ""),
                    "current_user_id": d.get("current_user_id", ""),
                    "linked_at": d.get("linked_at", ""),
                    "replaced_at": d.get("replaced_at", ""),
                    "last_seen_at": d.get("last_seen_at", ""),
                    "created_at": d.get("created_at", ""),
                }
            )
        out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        lim = max(1, min(1000, int(limit)))
        return out[:lim]

    def list_incidents(self, status: str = "", severity: str = "", limit: int = 100) -> list:
        status_key = (status or "").strip().lower()
        severity_key = (severity or "").strip().lower()
        incidents = []

        for row in self.db.get("payment_events", []):
            typ = (row.get("event_type") or "").strip().lower()
            if typ in ("payment.failed", "subscription.past_due"):
                incidents.append(
                    {
                        "incident_id": f"inc_pay_{row.get('event_id', token_urlsafe(6))}",
                        "type": "billing",
                        "severity": "high",
                        "status": "open",
                        "title": f"Billing issue: {typ}",
                        "user_id": row.get("user_id", ""),
                        "source_ref": row.get("event_id", ""),
                        "created_at": row.get("created_at", ""),
                    }
                )

        for row in self.db.get("device_update_reports", []):
            st = (row.get("status") or "").strip().lower()
            if st in ("failed", "error"):
                incidents.append(
                    {
                        "incident_id": f"inc_ota_{row.get('report_id', token_urlsafe(6))}",
                        "type": "ota",
                        "severity": "medium",
                        "status": "open",
                        "title": "Firmware update failed",
                        "device_id": row.get("device_id", ""),
                        "source_ref": row.get("report_id", ""),
                        "created_at": row.get("created_at", ""),
                    }
                )

        for row in self.db.get("incidents", []):
            incidents.append(row)

        filtered = []
        for inc in incidents:
            if status_key and (inc.get("status", "").strip().lower() != status_key):
                continue
            if severity_key and (inc.get("severity", "").strip().lower() != severity_key):
                continue
            filtered.append(inc)

        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        lim = max(1, min(500, int(limit)))
        return filtered[:lim]

    def build_user_timeline(self, user_id: str, limit: int = 100) -> list:
        events = []
        user_key = str(user_id or "").strip()

        user = self.get_user(user_id)
        if user:
            events.append(
                {
                    "ts": user.get("created_at", ""),
                    "category": "auth",
                    "event": "user_created",
                    "data": {
                        "user_id": user.get("user_id", ""),
                        "email": user.get("email", ""),
                    },
                }
            )

        sub = self.get_subscription(user_id)
        if sub:
            events.append(
                {
                    "ts": sub.get("updated_at", ""),
                    "category": "subscription",
                    "event": "subscription_status",
                    "data": {
                        "tier": sub.get("tier", "free"),
                        "status": sub.get("status", "active"),
                        "interval": sub.get("interval", "monthly"),
                    },
                }
            )

        for d in self.db.get("devices", []):
            if self._device_belongs_to_user(d, user_key):
                if d.get("linked_at"):
                    events.append(
                        {
                            "ts": d.get("linked_at", ""),
                            "category": "device",
                            "event": "device_linked",
                            "data": {
                                "device_id": d.get("device_id", ""),
                                "status": d.get("status", ""),
                                "model": d.get("model", ""),
                            },
                        }
                    )
                if d.get("replaced_at"):
                    events.append(
                        {
                            "ts": d.get("replaced_at", ""),
                            "category": "device",
                            "event": "device_replaced",
                            "data": {
                                "device_id": d.get("device_id", ""),
                                "status": d.get("status", ""),
                            },
                        }
                    )

        for row in self.db.get("payment_events", []):
            if row.get("user_id") == user_id:
                events.append(
                    {
                        "ts": row.get("created_at", ""),
                        "category": "billing",
                        "event": row.get("event_type", "payment_event"),
                        "data": {
                            "event_id": row.get("event_id", ""),
                            "tier": row.get("tier", ""),
                            "interval": row.get("interval", "monthly"),
                        },
                    }
                )

        for row in self.db.get("usage_daily", []):
            if row.get("user_id") == user_id:
                events.append(
                    {
                        "ts": row.get("date", "") + "T00:00:00",
                        "category": "usage",
                        "event": "usage_daily",
                        "data": {
                            "tokens_used": int(row.get("tokens_used", 0)),
                            "requests_used": int(row.get("requests_used", 0)),
                            "date": row.get("date", ""),
                        },
                    }
                )

        events.sort(key=lambda x: x.get("ts", ""), reverse=True)
        lim = max(1, min(500, int(limit)))
        return events[:lim]

    def delete_user_data(self, user_id: str) -> dict:
        user_key = str(user_id or "").strip()
        if not user_key:
            raise ValueError("user_id is required")

        deleted = {
            "users": 0,
            "subscriptions": 0,
            "usage_daily": 0,
            "usage_monthly": 0,
            "bed_profiles": 0,
            "checkout_sessions": 0,
            "payment_events": 0,
            "admin_users": 0,
            "user_sessions": 0,
            "admin_sessions": 0,
            "mobile_sessions": 0,
            "mobile_refresh_sessions": 0,
            "device_sessions": 0,
            "device_refresh_sessions": 0,
            "devices_unlinked": 0,
        }

        def _delete_rows(key: str, predicate) -> int:
            rows = self.db.get(key, [])
            if not isinstance(rows, list):
                return 0
            kept = [row for row in rows if not predicate(row if isinstance(row, dict) else {})]
            removed = len(rows) - len(kept)
            if removed:
                self.db[key] = kept
            return removed

        deleted["users"] = _delete_rows("users", lambda row: row.get("user_id") == user_key)
        deleted["subscriptions"] = _delete_rows("subscriptions", lambda row: row.get("user_id") == user_key)
        deleted["usage_daily"] = _delete_rows("usage_daily", lambda row: row.get("user_id") == user_key)
        deleted["usage_monthly"] = _delete_rows("usage_monthly", lambda row: row.get("user_id") == user_key)
        deleted["bed_profiles"] = _delete_rows("bed_profiles", lambda row: row.get("user_id") == user_key)
        deleted["checkout_sessions"] = _delete_rows("checkout_sessions", lambda row: row.get("user_id") == user_key)
        deleted["payment_events"] = _delete_rows("payment_events", lambda row: row.get("user_id") == user_key)
        deleted["admin_users"] = _delete_rows("admin_users", lambda row: row.get("user_id") == user_key)

        for row in self.db.get("devices", []):
            if not isinstance(row, dict):
                continue
            if row.get("current_user_id") == user_key or row.get("owner_user_id") == user_key:
                row["current_user_id"] = ""
                row["owner_user_id"] = ""
                row["status"] = "available"
                row["replaced_at"] = ""
                deleted["devices_unlinked"] += 1

        for token, session in list(self.db.get("user_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["user_sessions"][token]
                deleted["user_sessions"] += 1

        for token, session in list(self.db.get("admin_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["admin_sessions"][token]
                deleted["admin_sessions"] += 1

        for token, session in list(self.db.get("mobile_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["mobile_sessions"][token]
                deleted["mobile_sessions"] += 1

        for token, session in list(self.db.get("mobile_refresh_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["mobile_refresh_sessions"][token]
                deleted["mobile_refresh_sessions"] += 1

        for token, session in list(self.db.get("device_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["device_sessions"][token]
                deleted["device_sessions"] += 1

        for token, session in list(self.db.get("device_refresh_sessions", {}).items()):
            if isinstance(session, dict) and session.get("user_id") == user_key:
                del self.db["device_refresh_sessions"][token]
                deleted["device_refresh_sessions"] += 1

        deleted["total"] = sum(int(v) for v in deleted.values())
        if deleted["total"] > 0:
            self.save()
        return deleted
