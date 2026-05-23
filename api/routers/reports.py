"""Health report routes — migrated from web_server.py.

Routes:
  GET /v1/report/weekly/pdf      — download PDF
  GET /v1/report/weekly/pdf/url  — generate PDF, upload to S3, return presigned URL
  GET /v1/report/weekly/html     — render HTML preview
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter(prefix="/v1/report", tags=["reports"])


@router.get("/weekly/pdf")
async def weekly_report_pdf(request: Request, renderer: str = "reportlab") -> Response:
    from web_server import weekly_report_pdf as _ws
    return await _ws(request=request, renderer=renderer)


@router.get("/weekly/pdf/url")
async def weekly_report_pdf_url(
    request: Request, renderer: str = "reportlab", expires_in: int = 3600
) -> dict[str, Any]:
    from web_server import weekly_report_pdf_url as _ws
    return await _ws(request=request, renderer=renderer, expires_in=expires_in)


@router.get("/weekly/html")
async def weekly_report_html(request: Request) -> Response:
    from web_server import weekly_report_html as _ws
    return await _ws(request=request)
