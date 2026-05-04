"""Shared httpx clients with connection pooling and sensible defaults.

Usage:
    from core.http_client import http, get_client

    # Module-level singleton (sync, connection-pooled)
    resp = http.get("https://example.com", timeout=10)

    # One-off client with custom base_url
    with get_client(base_url="https://api.example.com") as client:
        resp = client.post("/endpoint", json={...})
"""

from __future__ import annotations

import httpx

# Shared sync client — connection-pooled, reused across the process lifetime.
# Close it only on process shutdown (lifespan event in web_server.py).
http: httpx.Client = httpx.Client(
    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    follow_redirects=True,
)


def get_client(**kwargs) -> httpx.Client:
    """Return a new httpx.Client configured with project defaults + overrides.

    Intended for use as a context manager when you need a custom base_url,
    headers, or auth that differ from the shared singleton.
    """
    defaults = dict(
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        follow_redirects=True,
    )
    defaults.update(kwargs)
    return httpx.Client(**defaults)