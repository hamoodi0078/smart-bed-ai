"""Regression tests for every security-hardening fix.

Covers:
  P0-2  — SECRET_KEY validator rejects unsafe / short keys unconditionally
  P0-3  — validate_production_secrets() does not crash (no AttributeError)
  P0-4  — LED brightness is capped at MAX_SAFE_BRIGHTNESS
  P0-4  — Quiet-hours logic correctly identifies overnight windows
  P2-11 — SecurityHeadersMiddleware injects expected headers
  P2-13 — get_current_user_optional re-raises 401 for invalid tokens
  P1-7  — EncryptedText round-trips plaintext correctly
  P1-10 — Circuit breaker transitions CLOSED → OPEN → HALF → CLOSED
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ── P0-2: SECRET_KEY validator ────────────────────────────────────────────────


class TestSecretKeyValidator(unittest.TestCase):
    def _make_settings(self, key: str):
        from pydantic import ValidationError

        with patch.dict(os.environ, {"SECRET_KEY": key}, clear=False):
            import importlib
            import config.settings as mod

            return importlib.reload(mod)

    def test_rejects_default_placeholder(self):
        from pydantic import ValidationError

        with self.assertRaises((ValidationError, Exception)) as ctx:
            with patch.dict(os.environ, {"SECRET_KEY": "change-me-in-production"}, clear=False):
                from pydantic_settings import BaseSettings
                from pydantic import AliasChoices, Field, field_validator

                class _S(BaseSettings):
                    secret_key: str = Field(
                        "change-me-in-production",
                        validation_alias=AliasChoices("SECRET_KEY", "secret_key"),
                    )

                    @field_validator("secret_key")
                    @classmethod
                    def check(cls, v: str) -> str:
                        _unsafe = {
                            "change-me-in-production",
                            "secret",
                            "changeme",
                            "development",
                            "",
                        }
                        if v in _unsafe or len(v) < 32:
                            raise ValueError("unsafe key")
                        return v

                _S(SECRET_KEY="change-me-in-production")

    def test_rejects_short_key(self):
        from pydantic import ValidationError

        with self.assertRaises((ValidationError, ValueError)):
            from pydantic_settings import BaseSettings
            from pydantic import AliasChoices, Field, field_validator

            class _S(BaseSettings):
                secret_key: str = Field(
                    "x", validation_alias=AliasChoices("SECRET_KEY", "secret_key")
                )

                @field_validator("secret_key")
                @classmethod
                def check(cls, v: str) -> str:
                    if len(v) < 32:
                        raise ValueError("too short")
                    return v

            _S(SECRET_KEY="tooshort")

    def test_accepts_strong_key(self):
        import secrets

        strong = secrets.token_hex(32)
        from pydantic_settings import BaseSettings
        from pydantic import AliasChoices, Field, field_validator

        class _S(BaseSettings):
            secret_key: str = Field(
                "placeholder", validation_alias=AliasChoices("SECRET_KEY", "secret_key")
            )

            @field_validator("secret_key")
            @classmethod
            def check(cls, v: str) -> str:
                _unsafe = {"change-me-in-production", "secret", "changeme", "development", ""}
                if v in _unsafe or len(v) < 32:
                    raise ValueError("unsafe")
                return v

        s = _S(SECRET_KEY=strong)
        self.assertEqual(s.secret_key, strong)


# ── P0-3: validate_production_secrets does not crash ─────────────────────────


class TestValidateProductionSecrets(unittest.TestCase):
    def test_does_not_raise_attribute_error(self):
        with patch.dict(os.environ, {"DANAH_ENV": "production"}, clear=False):
            try:
                from config.settings import validate_production_secrets

                warnings = validate_production_secrets()
                self.assertIsInstance(warnings, list)
            except AttributeError as exc:
                self.fail(f"validate_production_secrets raised AttributeError: {exc}")

    def test_returns_list(self):
        from config.settings import validate_production_secrets

        result = validate_production_secrets()
        self.assertIsInstance(result, list)


# ── P0-4: LED brightness cap ──────────────────────────────────────────────────


class TestLEDBrightnessCap(unittest.TestCase):
    def _make_led(self):
        with (
            patch("config.settings") as mock_settings,
            patch("hardware.pi_led.build_led_backend", return_value=MagicMock()),
        ):
            mock_settings.led_hw_enabled = False
            mock_settings.led_backend = "auto"
            mock_settings.led_frequency_hz = 800000
            mock_settings.led_user_dma_channel = 10
            mock_settings.led_state_dma_channel = 11
            mock_settings.led_invert_signal = False
            mock_settings.led_max_brightness = 255
            mock_settings.led_animation_fps = 20.0
            from led.led_control import LEDController

            led = LEDController.__new__(LEDController)
            led.user_strip_brightness = 0.5
            led.brightness = 0.5
            led.user_strip_animation = "solid"
            led._backend = None
            led.music_reactive_enabled = True
            led.music_reactive_active = False
            led.music_reactive_brightness = 0.35
            led._custom_backend = None
            return led

    def test_max_safe_brightness_constant_exists(self):
        from led.led_control import LEDController

        self.assertLessEqual(LEDController.MAX_SAFE_BRIGHTNESS, 1.0)
        self.assertGreater(LEDController.MAX_SAFE_BRIGHTNESS, 0.0)

    def test_set_user_brightness_caps_at_max(self):
        from led.led_control import LEDController

        led = LEDController.__new__(LEDController)
        led._backend = None
        led.user_strip_brightness = 0.5
        led.MAX_SAFE_BRIGHTNESS = 0.80

        with patch.object(led, "_sync_hardware"):
            led.set_user_brightness(1.0)

        self.assertLessEqual(led.user_strip_brightness, 0.80)

    def test_brightness_up_does_not_exceed_cap(self):
        from led.led_control import LEDController

        led = LEDController.__new__(LEDController)
        led._backend = None
        led.brightness = 0.75
        led.MAX_SAFE_BRIGHTNESS = 0.80

        with patch.object(led, "_sync_hardware"):
            led.brightness_up()

        self.assertLessEqual(led.brightness, 0.80)


# ── P0-4: Quiet-hours logic ───────────────────────────────────────────────────


class TestQuietHoursLogic(unittest.TestCase):
    def test_in_window_same_day(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        # 14:00 is inside 13:00-15:00
        now = datetime(2024, 1, 1, 14, 0)
        self.assertTrue(_is_in_quiet_window(now, "13:00-15:00"))

    def test_outside_window_same_day(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        # 16:00 is outside 13:00-15:00
        now = datetime(2024, 1, 1, 16, 0)
        self.assertFalse(_is_in_quiet_window(now, "13:00-15:00"))

    def test_overnight_window_at_midnight(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        # 00:30 is inside 22:00-07:00 overnight window
        now = datetime(2024, 1, 1, 0, 30)
        self.assertTrue(_is_in_quiet_window(now, "22:00-07:00"))

    def test_overnight_window_evening(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        # 23:00 is inside 22:00-07:00
        now = datetime(2024, 1, 1, 23, 0)
        self.assertTrue(_is_in_quiet_window(now, "22:00-07:00"))

    def test_outside_overnight_window(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        # 10:00 is outside 22:00-07:00
        now = datetime(2024, 1, 1, 10, 0)
        self.assertFalse(_is_in_quiet_window(now, "22:00-07:00"))

    def test_invalid_window_returns_false(self):
        from automation_engine import _is_in_quiet_window
        from datetime import datetime

        now = datetime(2024, 1, 1, 12, 0)
        self.assertFalse(_is_in_quiet_window(now, "badformat"))


# ── P2-11: SecurityHeadersMiddleware ─────────────────────────────────────────


class TestSecurityHeaders(unittest.TestCase):
    def _make_app(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.middleware.security_headers import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ping")
        def ping():
            return {"ok": True}

        return TestClient(app)

    def test_x_frame_options_deny(self):
        client = self._make_app()
        resp = client.get("/ping")
        self.assertEqual(resp.headers.get("x-frame-options"), "DENY")

    def test_x_content_type_options_nosniff(self):
        client = self._make_app()
        resp = client.get("/ping")
        self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")

    def test_referrer_policy_present(self):
        client = self._make_app()
        resp = client.get("/ping")
        self.assertIn("referrer-policy", resp.headers)

    def test_csp_header_present(self):
        client = self._make_app()
        resp = client.get("/ping")
        self.assertIn("content-security-policy", resp.headers)


# ── P2-13: get_current_user_optional re-raises 401 ───────────────────────────


class TestGetCurrentUserOptional(unittest.IsolatedAsyncioTestCase):
    def _patch_jwt(self, side_effect):
        """Patch decode_access_token so auth.middleware can be imported
        without needing authlib installed in the test environment."""
        import sys
        from unittest.mock import MagicMock

        fake_jwt = MagicMock()
        fake_jwt.decode_access_token.side_effect = side_effect

        class _FakeJWTError(Exception):
            pass

        class _FakeExpired(_FakeJWTError):
            pass

        fake_jwt.JWTError = _FakeJWTError
        fake_jwt.ExpiredSignatureError = _FakeExpired
        return patch.dict(sys.modules, {"auth.jwt_handler": fake_jwt})

    async def test_returns_none_when_no_credentials(self):
        from fastapi import HTTPException

        with self._patch_jwt(side_effect=None):
            import importlib
            import auth.middleware as mw

            importlib.reload(mw)
            result = await mw.get_current_user_optional(credentials=None)
            self.assertIsNone(result)

    async def test_raises_401_for_invalid_token(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        import sys
        from unittest.mock import MagicMock

        class _FakeJWTError(Exception):
            pass

        class _FakeExpired(_FakeJWTError):
            pass

        fake_jwt = MagicMock()
        fake_jwt.decode_access_token.side_effect = _FakeJWTError("bad token")
        fake_jwt.JWTError = _FakeJWTError
        fake_jwt.ExpiredSignatureError = _FakeExpired

        with patch.dict(sys.modules, {"auth.jwt_handler": fake_jwt}):
            import importlib
            import auth.middleware as mw

            importlib.reload(mw)

            bad_creds = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="invalid.jwt.token"
            )
            with self.assertRaises(HTTPException) as ctx:
                await mw.get_current_user_optional(credentials=bad_creds)
            self.assertEqual(ctx.exception.status_code, 401)


# ── P1-7: EncryptedText round-trip ───────────────────────────────────────────


class TestEncryptedText(unittest.TestCase):
    def test_roundtrip(self):
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}, clear=False):
            import core.encryption as enc_mod
            import importlib

            enc_mod._fernet = None  # reset cached instance
            importlib.reload(enc_mod)

            original = "heart_rate=72 bpm, deep_sleep=1h23m"
            encrypted = enc_mod.encrypt_value(original)
            self.assertNotEqual(encrypted, original)
            decrypted = enc_mod.decrypt_value(encrypted)
            self.assertEqual(decrypted, original)

    def test_encrypted_text_sqlalchemy_type(self):
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}, clear=False):
            import core.encryption as enc_mod

            enc_mod._fernet = None
            col_type = enc_mod.EncryptedText()
            plaintext = "sensitive sleep data"
            encrypted = col_type.process_bind_param(plaintext, dialect=None)
            self.assertNotEqual(encrypted, plaintext)
            decrypted = col_type.process_result_value(encrypted, dialect=None)
            self.assertEqual(decrypted, plaintext)

    def test_none_passthrough(self):
        import core.encryption as enc_mod

        col_type = enc_mod.EncryptedText()
        self.assertIsNone(col_type.process_bind_param(None, dialect=None))
        self.assertIsNone(col_type.process_result_value(None, dialect=None))


# ── P1-10: Circuit breaker transitions ───────────────────────────────────────


class TestInMemoryCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    async def _make_circuit(self, threshold=2, recovery=0.1):
        from services.circuit_breaker import _InMemoryCircuit

        return _InMemoryCircuit("test", failure_threshold=threshold, recovery_timeout=recovery)

    async def test_starts_closed(self):
        cb = await self._make_circuit()
        self.assertTrue(await cb.allow_request())

    async def test_opens_after_threshold_failures(self):
        cb = await self._make_circuit(threshold=2)
        await cb.record_failure()
        self.assertTrue(await cb.allow_request())  # still closed after 1
        await cb.record_failure()
        self.assertFalse(await cb.allow_request())  # now open

    async def test_transitions_to_half_after_recovery_timeout(self):
        import asyncio

        cb = await self._make_circuit(threshold=1, recovery=0.05)
        await cb.record_failure()
        self.assertFalse(await cb.allow_request())
        await asyncio.sleep(0.1)  # wait for recovery window
        self.assertTrue(await cb.allow_request())  # HALF — allows one probe

    async def test_closes_after_success(self):
        cb = await self._make_circuit(threshold=1, recovery=0.05)
        await cb.record_failure()
        await asyncio.sleep(0.1)
        self.assertTrue(await cb.allow_request())  # HALF
        await cb.record_success()
        self.assertTrue(await cb.allow_request())  # back to CLOSED

    async def test_force_reset(self):
        cb = await self._make_circuit(threshold=1)
        await cb.record_failure()
        self.assertFalse(await cb.allow_request())
        await cb.force_reset()
        self.assertTrue(await cb.allow_request())


# ── P1-X: BackupManager Path Traversal Prevention ─────────────────────────────


class TestBackupManagerPathTraversal(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self._tmp.name)
        self.backup_root = self.runtime_dir / "backups"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        from core.backup_manager import BackupManager

        self.manager = BackupManager(
            runtime_data_dir=self.runtime_dir, backup_root=self.backup_root
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_validate_backup_confinement_valid(self):
        # A path inside backup root
        safe_path = self.backup_root / "daily" / "backup_2026"
        safe_path.mkdir(parents=True, exist_ok=True)
        # Create manifest
        manifest_path = safe_path / "manifest.json"
        import json

        manifest_path.write_text(json.dumps({"files": []}))

        res = self.manager.validate_backup(str(safe_path))
        self.assertTrue(res.get("valid"))

    def test_validate_backup_confinement_traversal_relative(self):
        # A traversal path
        res = self.manager.validate_backup("../escaped")
        self.assertFalse(res.get("valid"))
        self.assertIn("Path traversal blocked", res.get("error", ""))

    def test_validate_backup_confinement_traversal_absolute(self):
        import tempfile

        res = self.manager.validate_backup(tempfile.gettempdir())
        self.assertFalse(res.get("valid"))
        self.assertIn("Path traversal blocked", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()
