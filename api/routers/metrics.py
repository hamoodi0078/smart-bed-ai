"""Prometheus metrics endpoint — extracted from web_server.py.

Secured: only accessible from localhost or IP allowlist via METRICS_ALLOWED_IPS.
Set METRICS_ALLOWED_IPS=127.0.0.1,10.0.0.0/8 in .env to restrict access.
"""

from __future__ import annotations

import ipaddress
import os

from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["observability"])

_METRICS_ALLOWED_NETS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []


def _load_allowed_nets() -> None:
    raw = os.getenv("METRICS_ALLOWED_IPS", "127.0.0.1,::1")
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            _METRICS_ALLOWED_NETS.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            pass


_load_allowed_nets()


def _is_metrics_allowed(request: Request) -> bool:
    if not _METRICS_ALLOWED_NETS:
        return True
    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in net for net in _METRICS_ALLOWED_NETS)
    except ValueError:
        return False


@router.get("/metrics")
def metrics(request: Request) -> Response:
    if not _is_metrics_allowed(request):
        return Response(status_code=403, content="Forbidden")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
