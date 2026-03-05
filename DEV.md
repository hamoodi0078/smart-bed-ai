# DEV Notes

## Stable API Boundary (v1)

These endpoints are intended as a stable boundary for future web/mobile clients.

### GET `/v1/state`

Returns a stable snapshot payload suitable for clients.

**Auth:** user or admin session cookie required.

**Response shape:**

```json
{
  "ok": true,
  "generated_at": "2026-03-05T17:24:00Z",
  "snapshot": {
    "emotion_state": "neutral",
    "active_personality": "guide",
    "biometric_summary": {
      "recovery_mode": false,
      "challenge_level": 1,
      "night_wake_count": 0,
      "bedtime_samples": 0,
      "wake_samples": 0,
      "partner_mode_enabled": false,
      "last_bedtime_drift_alert_date": ""
    },
    "device_health_status": {
      "deepgram_configured": false,
      "spotify_connected_users": 0,
      "led": {
        "user_strip_pin": 18,
        "state_strip_pin": 13,
        "user_strip_led_count": 120,
        "state_strip_led_count": 60
      },
      "last_scene_key": "",
      "last_preload_phase": "",
      "sensor_pressure_active": false,
      "sensor_motion_active": false
    }
  }
}
```

**Security guarantee:** `/v1/state` is redacted and must never expose secret fields such as:
- `access_token`
- `refresh_token`
- `password_hash`
- oauth token fields (any oauth token key)

---

### POST `/v1/command`

Accepts a normalized command payload and returns a stable command response for clients.

**Auth:** user or admin session cookie required.

**Request shape:**

```json
{
  "text": "start wind down",
  "source": "web"
}
```

`source` currently accepts: `web`, `mobile`, `api` (unknown values fall back to `web`).

**Response shape:**

```json
{
  "reply_text": "Sure. I can help with that.",
  "effects_summary": {
    "source": "web",
    "executed_actions": [],
    "assistant_fallback_used": false,
    "note": "No direct device action executed; assistant generated a guidance reply."
  }
}
```

---

## Backward Compatibility

- Existing endpoints (for example `/v1/bed/state` and `/v1/ai/chat`) remain available.
- New clients should prefer `/v1/state` and `/v1/command` as the versioned boundary.
