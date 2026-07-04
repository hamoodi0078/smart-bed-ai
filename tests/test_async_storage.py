"""Async storage helpers tested with pytest-asyncio."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from Storage.io import (
    async_atomic_write_json,
    async_read_json_simple,
    async_read_text,
    async_write_json_simple,
)


@pytest.fixture
async def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_async_read_text_returns_empty_for_missing_file(tmp_dir):
    result = await async_read_text(tmp_dir / "nonexistent.txt")
    assert result == ""


async def test_async_write_then_read_json_simple_round_trip(tmp_dir):
    path = tmp_dir / "cache" / "data.json"
    payload = {"key": "value", "number": 42, "items": [1, 2, 3]}
    await async_write_json_simple(path, payload)
    loaded = await async_read_json_simple(path)
    assert loaded == payload


async def test_async_read_json_simple_returns_empty_for_missing_file(tmp_dir):
    result = await async_read_json_simple(tmp_dir / "missing.json")
    assert result == {}


async def test_async_read_json_simple_returns_empty_for_invalid_json(tmp_dir):
    path = tmp_dir / "broken.json"
    path.write_text("not valid json", encoding="utf-8")
    result = await async_read_json_simple(path)
    assert result == {}


async def test_async_atomic_write_then_read_round_trip(tmp_dir):
    path = tmp_dir / "state.json"
    payload = {"schema_version": 2, "name": "Dana", "active": True}
    await async_atomic_write_json(path, payload)
    raw = path.read_text(encoding="utf-8")
    loaded = json.loads(raw)
    assert loaded == payload


async def test_async_write_json_simple_creates_parent_dirs(tmp_dir):
    nested = tmp_dir / "a" / "b" / "c" / "file.json"
    await async_write_json_simple(nested, {"ok": True})
    assert nested.exists()
    assert json.loads(nested.read_text(encoding="utf-8")) == {"ok": True}
