from __future__ import annotations

import argparse
import sys
import time
import uuid
from typing import Any

import requests


class SmokeFailure(RuntimeError):
    pass


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> tuple[requests.Response, dict[str, Any], float]:
    started = time.perf_counter()
    response = session.request(method=method, url=url, timeout=25, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            payload = {"payload": payload}
    except Exception:
        payload = {"raw": response.text}
    return response, payload, elapsed_ms


def _expect_status(
    response: requests.Response,
    payload: dict[str, Any],
    expected: int,
    step_name: str,
) -> None:
    if response.status_code == expected:
        return
    trace_id = str(response.headers.get("X-Trace-Id", "") or "")
    detail = str(payload.get("detail", "") or "")
    error = payload.get("error", {}) if isinstance(payload.get("error", {}), dict) else {}
    code = str(error.get("code", "") or "")
    message = str(error.get("message", "") or "")
    raise SmokeFailure(
        f"{step_name} failed: expected {expected}, got {response.status_code} "
        f"(code={code or '-'}, message={message or detail or '-'}, trace={trace_id or '-'})"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _print_step(step: str, elapsed_ms: float, trace_id: str, extra: str = "") -> None:
    suffix = f" | trace={trace_id}" if trace_id else ""
    extra_suffix = f" | {extra}" if extra else ""
    print(f"[PASS] {step} ({elapsed_ms:.0f}ms){suffix}{extra_suffix}")


def run_smoke(
    *,
    base_url: str,
    email: str,
    password: str,
    action: str,
    scene_key: str,
) -> None:
    normalized_base = base_url.rstrip("/")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    register_response, register_body, elapsed = _request_json(
        session,
        "POST",
        f"{normalized_base}/v1/mobile/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Smoke User",
            "client_name": "mobile_smoke_script",
        },
    )
    _expect_status(register_response, register_body, 200, "register")
    _require(bool(register_body.get("ok")), "register returned missing ok=true")
    access_token = str(register_body.get("access_token", "") or "")
    _require(bool(access_token), "register returned empty access_token")
    _print_step(
        "signup/register",
        elapsed,
        str(register_response.headers.get("X-Trace-Id", "") or ""),
        extra=f"user={email}",
    )

    auth_headers = {"Authorization": f"Bearer {access_token}"}
    dashboard_response, dashboard_body, elapsed = _request_json(
        session,
        "GET",
        f"{normalized_base}/v1/mobile/dashboard",
        headers=auth_headers,
    )
    _expect_status(dashboard_response, dashboard_body, 200, "dashboard")
    _require("weekly_insight" in dashboard_body, "dashboard missing weekly_insight")
    _require("nightly_summary" in dashboard_body, "dashboard missing nightly_summary")
    _print_step(
        "dashboard",
        elapsed,
        str(dashboard_response.headers.get("X-Trace-Id", "") or ""),
    )

    command_response, command_body, elapsed = _request_json(
        session,
        "POST",
        f"{normalized_base}/v1/mobile/device-commands",
        headers=auth_headers,
        json={"action": action},
    )
    _expect_status(command_response, command_body, 200, "quick action")
    _require(bool(command_body.get("ok")), "quick action returned missing ok=true")
    command_id = str(command_body.get("command_id", "") or "")
    _require(bool(command_id), "quick action returned empty command_id")
    _print_step(
        "quick action",
        elapsed,
        str(command_response.headers.get("X-Trace-Id", "") or ""),
        extra=f"command_id={command_id}",
    )

    preview_response, preview_body, elapsed = _request_json(
        session,
        "POST",
        f"{normalized_base}/v1/mobile/scenes/preview",
        headers=auth_headers,
        json={"scene_key": scene_key},
    )
    _expect_status(preview_response, preview_body, 200, "scene preview")
    _require(bool(preview_body.get("ok")), "scene preview returned missing ok=true")
    _require(
        str(preview_body.get("scene_key", "") or "") == scene_key,
        "scene preview returned unexpected scene_key",
    )
    _print_step(
        "scene preview",
        elapsed,
        str(preview_response.headers.get("X-Trace-Id", "") or ""),
    )

    timeline_response, timeline_body, elapsed = _request_json(
        session,
        "GET",
        f"{normalized_base}/v1/mobile/timeline",
        headers=auth_headers,
    )
    _expect_status(timeline_response, timeline_body, 200, "timeline")
    _require(bool(timeline_body.get("ok")), "timeline returned missing ok=true")
    items = timeline_body.get("items", [])
    _require(isinstance(items, list), "timeline items is not a list")
    found_command = any(
        isinstance(row, dict)
        and str(row.get("command_id", "") or "") == command_id
        for row in items
    )
    _require(found_command, "timeline did not include the command created in this smoke run")
    _print_step(
        "timeline update",
        elapsed,
        str(timeline_response.headers.get("X-Trace-Id", "") or ""),
        extra=f"items={len(items)}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manual smoke helper for Smart Bed mobile vertical flow.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Web runtime base URL (default: http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Optional registration email. If omitted, a random email is generated.",
    )
    parser.add_argument(
        "--password",
        default="secret123",
        help="Registration password (must satisfy backend policy).",
    )
    parser.add_argument(
        "--action",
        default="winddown",
        help="Quick action key for /v1/mobile/device-commands (default: winddown).",
    )
    parser.add_argument(
        "--scene-key",
        default="calm_recovery",
        help="Scene key for preview step (default: calm_recovery).",
    )
    args = parser.parse_args()

    email = str(args.email or "").strip().lower()
    if not email:
        email = f"smoke_{uuid.uuid4().hex[:10]}@example.com"

    print("Running mobile smoke flow:")
    print(f"- base_url: {args.base_url}")
    print(f"- email: {email}")
    print(f"- action: {args.action}")
    print(f"- scene_key: {args.scene_key}")

    try:
        run_smoke(
            base_url=str(args.base_url),
            email=email,
            password=str(args.password),
            action=str(args.action),
            scene_key=str(args.scene_key),
        )
    except requests.RequestException as exc:
        print(f"[FAIL] network error: {exc}")
        return 2
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        return 2
    except Exception as exc:
        print(f"[FAIL] unexpected error: {type(exc).__name__}: {exc}")
        return 1

    print("[PASS] mobile smoke flow completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
