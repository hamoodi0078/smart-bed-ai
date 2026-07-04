"""Security tests for cookie-flow same-origin (CSRF) enforcement."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

import auth.cookie as cookie


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def _request(origin: str = "", referer: str = "") -> _FakeRequest:
    headers: dict[str, str] = {}
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer
    return _FakeRequest(headers)


class TestEnforceSameOrigin(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict("os.environ", {"DANAH_ENV": "production"}, clear=False)
        self._env.start()
        self._settings = patch.object(
            cookie.settings, "web_allowed_origins_raw", "https://danah.app"
        )
        self._settings.start()

    def tearDown(self):
        self._settings.stop()
        self._env.stop()

    def test_no_origin_is_allowed(self):
        # server-to-server / curl / Postman
        cookie.enforce_same_origin(_request())

    def test_exact_allowed_origin_passes(self):
        cookie.enforce_same_origin(_request(origin="https://danah.app"))

    def test_suffix_attack_origin_is_blocked(self):
        # The core fix: a prefix match would have let this through.
        with self.assertRaises(HTTPException):
            cookie.enforce_same_origin(_request(origin="https://danah.app.evil.com"))

    def test_unrelated_origin_is_blocked(self):
        with self.assertRaises(HTTPException):
            cookie.enforce_same_origin(_request(origin="https://evil.com"))

    def test_scheme_downgrade_is_blocked(self):
        with self.assertRaises(HTTPException):
            cookie.enforce_same_origin(_request(origin="http://danah.app"))

    def test_referer_origin_is_matched_without_path(self):
        cookie.enforce_same_origin(_request(referer="https://danah.app/some/page?x=1"))
        with self.assertRaises(HTTPException):
            cookie.enforce_same_origin(_request(referer="https://evil.com/danah.app"))

    def test_localhost_allowed_only_outside_production(self):
        with patch.dict("os.environ", {"DANAH_ENV": "development"}, clear=False):
            cookie.enforce_same_origin(_request(origin="http://localhost:8000"))
        with self.assertRaises(HTTPException):
            cookie.enforce_same_origin(_request(origin="http://localhost:8000"))


if __name__ == "__main__":
    unittest.main()
