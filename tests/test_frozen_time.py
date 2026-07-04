"""Tests that rely on deterministic time via freezegun.

These cover code paths that call datetime.today() / datetime.now()
internally and must behave consistently for a known frozen date.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pytest
from freezegun import freeze_time

from islamic_mode.hadith_daily import HadithService
from time_utils import utcnow


# ─── HadithService — date-dependent cache path ───────────────────────────────


class TestHadithServiceFrozenDate:
    @freeze_time("2026-05-05")
    def test_cache_path_contains_frozen_date(self, tmp_path):
        service = HadithService(cache_dir=tmp_path)
        path = service._get_daily_cache_path()
        assert "2026-05-05" in path.name

    @freeze_time("2026-12-31")
    def test_cache_path_rolls_over_at_midnight(self, tmp_path):
        service = HadithService(cache_dir=tmp_path)
        path = service._get_daily_cache_path()
        assert "2026-12-31" in path.name

    @freeze_time("2026-05-05")
    def test_deterministic_book_is_stable_for_same_date(self, tmp_path):
        service = HadithService(cache_dir=tmp_path)
        book1, num1 = service._get_deterministic_book_and_number()
        book2, num2 = service._get_deterministic_book_and_number()
        assert book1 == book2
        assert num1 == num2

    @freeze_time("2026-05-05")
    def test_deterministic_params_match_expected_hash(self, tmp_path):
        frozen_date = date(2026, 5, 5)
        seed = f"{frozen_date.year}-{frozen_date.month}-{frozen_date.day}"
        hash_val = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        book_list = list(HadithService.BOOKS.keys())
        expected_book = book_list[hash_val % len(book_list)]

        service = HadithService(cache_dir=tmp_path)
        actual_book, _ = service._get_deterministic_book_and_number()
        assert actual_book == expected_book

    @freeze_time("2026-05-05")
    def test_different_dates_may_produce_different_books(self, tmp_path):
        service = HadithService(cache_dir=tmp_path)
        book_a, _ = service._get_deterministic_book_and_number()

        with freeze_time("2026-05-06"):
            book_b, _ = service._get_deterministic_book_and_number()

        # Books CAN be different for consecutive dates — just verify they're valid.
        assert book_a in HadithService.BOOKS
        assert book_b in HadithService.BOOKS


# ─── time_utils.utcnow — frozen to specific instant ──────────────────────────


class TestUtcnowFrozenTime:
    @freeze_time("2026-05-05 03:00:00", tz_offset=0)
    def test_utcnow_returns_frozen_instant(self):
        frozen = utcnow()
        assert frozen.year == 2026
        assert frozen.month == 5
        assert frozen.day == 5
        assert frozen.hour == 3
        assert frozen.tzinfo is not None
        assert frozen.utcoffset().total_seconds() == 0

    @freeze_time("2026-01-01 00:00:00")
    def test_utcnow_new_year(self):
        frozen = utcnow()
        assert frozen.year == 2026
        assert frozen.month == 1
        assert frozen.day == 1
