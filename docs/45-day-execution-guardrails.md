# 45-Day Execution Guardrails

## Purpose
Lock delivery boundaries for the first 45 days so the team executes Week 1 roadmap work with high reliability and no scope drift.

## Current Locked Phase
- **Month 1: Foundation & Trust**
- Scope in this phase is stability, clear state visibility, and predictable API behavior.

## Frozen API Decisions (Week 1)
1. **`/v2/bed/state` contract is locked for this phase**
   - Keep and rely on: `schema_version`, `capabilities`, `updated_at`, `stale`, `device_online`, `source`, `state`.
   - No breaking response-shape changes during Month 1.
2. **Standardized error envelope is required**
   - Error responses stay in the `{"ok": false, "error": {"code", "message", "trace_id"}}` format.
3. **Trace ID behavior is required**
   - Every request gets a trace ID.
   - `X-Trace-Id` response header is always set.
   - Error envelopes include the same `trace_id`.
4. **Config/env approach is locked**
   - Runtime configuration is environment-driven (`.env` + `config.py` settings).
   - Avoid hardcoded environment-specific values in feature code.
5. **Metrics endpoint remains available**
   - `/metrics` stays enabled for operational visibility.

## Not Building Now (Explicitly Deferred)
- Web dashboard expansion beyond the current minimum Week 1 surface.
- Full partner negotiation AI.
- 3D visualizations.
- Marketplace payments.
- Multiple proactive automations beyond current minimum behavior.
- Phase B/C roadmap items (advanced premium scenes, immersive audio/visual features, story/journal systems, large integration expansions).

## SLOs (Reliability and Trust)
1. **p95 latency target**
   - p95 for Week 1 trust endpoints (`/healthz`, `/v1/state`, `/v2/bed/state`) should stay under **750 ms** in normal operation.
2. **Error budget target**
   - Keep API success at **>= 99.5%** (5xx error budget <= 0.5% of requests).
3. **Device state freshness expectation**
   - Online: update age `< 30s`
   - Stale: `30s to 5m`
   - Offline: `> 5m`
4. **Reliability-first rule**
   - If SLOs are not met, fix reliability first; defer net-new feature work until SLOs recover.

## Week 1 Definition of Done
- `/v2/bed/state` freshness fields are stable and consumed by the current UI status indicator.
- Error envelope behavior is consistent across HTTP, validation, and unhandled errors.
- Trace ID is present in response headers and error payloads.
- `/metrics` endpoint is reachable.
- Off-scope requests are explicitly deferred.

## Change-Control Rule
- If a task is off-roadmap for the current locked phase, it is **deferred** and not implemented in the current sprint window.
