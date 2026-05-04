# ADR-0001: Use Deepgram for Voice (STT/TTS)

**Status:** Accepted  
**Date:** 2024-12-01  
**Deciders:** Core team

## Context

The Smart Bed AI needs reliable speech-to-text (STT) and text-to-speech (TTS) for its voice assistant pipeline. Options considered:

1. **Local Whisper** — Full offline, high latency on Raspberry Pi, no ongoing cost
2. **Deepgram API** — Cloud-based, low latency, per-minute billing
3. **Google Cloud Speech** — Cloud-based, well-documented, higher cost

## Decision

Use **Deepgram** as the primary STT/TTS provider with local Whisper as a fallback for offline mode.

## Consequences

- **Positive:** Sub-500ms latency, high accuracy, simple SDK integration
- **Positive:** Fallback to local `faster-whisper` when offline (`STT_MODE=local`)
- **Negative:** Requires internet connection for primary path
- **Negative:** Ongoing API costs (~$0.0059/min STT, ~$0.015/min TTS)
- **Mitigation:** Voice circuit breaker prevents runaway costs on failures
