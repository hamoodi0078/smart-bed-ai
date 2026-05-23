"""WebRTC VAD wrapper with ring-buffer smoothing for speech detection.

webrtcvad requires exact 10 / 20 / 30 ms PCM frames at 8 / 16 / 32 / 48 kHz.
VadFilter buffers arbitrary incoming chunks, slices them into conformant frames,
and applies onset / offset hysteresis via a ring buffer so noisy bursts don't
flip the speaking state on every frame.
"""

from __future__ import annotations

import collections
from typing import Iterable, Iterator

try:
    import webrtcvad as _webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    _webrtcvad = None  # type: ignore[assignment]
    VAD_AVAILABLE = False

_VALID_SAMPLE_RATES = frozenset({8000, 16000, 32000, 48000})
_VALID_FRAME_MS = frozenset({10, 20, 30})


class VadFilter:
    """Stateful WebRTC VAD wrapper with ring-buffer onset/offset hysteresis.

    Parameters
    ----------
    sample_rate:
        PCM sample rate in Hz — must be 8000 / 16000 / 32000 / 48000.
    aggressiveness:
        VAD aggressiveness 0-3; higher = more aggressive noise filtering.
    frame_ms:
        Frame duration in ms — must be 10, 20, or 30.
    ring_size:
        Number of recent frames kept for hysteresis voting.
    onset_ratio:
        Fraction of ring frames that must be speech to enter speaking state.
    offset_ratio:
        Fraction of ring frames that must be silence to leave speaking state.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
        frame_ms: int = 20,
        ring_size: int = 15,
        onset_ratio: float = 0.70,
        offset_ratio: float = 0.80,
    ) -> None:
        if sample_rate not in _VALID_SAMPLE_RATES:
            raise ValueError(
                f"sample_rate must be one of {sorted(_VALID_SAMPLE_RATES)}, got {sample_rate}"
            )
        if frame_ms not in _VALID_FRAME_MS:
            raise ValueError(
                f"frame_ms must be one of {sorted(_VALID_FRAME_MS)}, got {frame_ms}"
            )

        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._ring_size = max(1, int(ring_size))
        self._onset_ratio = max(0.0, min(1.0, float(onset_ratio)))
        self._offset_ratio = max(0.0, min(1.0, float(offset_ratio)))

        # 16-bit PCM → 2 bytes per sample
        self._frame_bytes: int = sample_rate * frame_ms // 1000 * 2

        self._vad = _webrtcvad.Vad(max(0, min(3, int(aggressiveness)))) if VAD_AVAILABLE else None

        self._buffer = bytearray()
        self._ring: collections.deque[bool] = collections.deque(maxlen=self._ring_size)
        self._is_speaking = False

    # ------------------------------------------------------------------
    # Single-frame classification
    # ------------------------------------------------------------------

    def is_speech_frame(self, frame: bytes) -> bool:
        """Classify one exact-length PCM frame. Returns False when VAD unavailable."""
        if not VAD_AVAILABLE or self._vad is None:
            return False
        if len(frame) != self._frame_bytes:
            return False
        try:
            return bool(self._vad.is_speech(frame, self._sample_rate))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Stateful chunk processing
    # ------------------------------------------------------------------

    def process_chunk(self, raw: bytes) -> bool:
        """Accept an arbitrary-size PCM chunk; return current speaking state.

        Buffers incoming bytes, slices into exact frames, classifies each,
        and updates the ring-buffer state machine.
        """
        if not VAD_AVAILABLE:
            return False

        self._buffer.extend(raw)

        while len(self._buffer) >= self._frame_bytes:
            frame = bytes(self._buffer[: self._frame_bytes])
            del self._buffer[: self._frame_bytes]
            self._ring.append(self.is_speech_frame(frame))

        if not self._ring:
            return self._is_speaking

        speech_ratio = sum(self._ring) / len(self._ring)

        if not self._is_speaking and speech_ratio >= self._onset_ratio:
            self._is_speaking = True
        elif self._is_speaking and (1.0 - speech_ratio) >= self._offset_ratio:
            self._is_speaking = False

        return self._is_speaking

    def reset(self) -> None:
        """Clear buffer and ring state between utterances."""
        self._buffer.clear()
        self._ring.clear()
        self._is_speaking = False

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @classmethod
    def has_enough_speech(
        cls,
        pcm: bytes,
        sample_rate: int,
        *,
        aggressiveness: int = 2,
        frame_ms: int = 20,
        min_speech_frames: int = 5,
    ) -> bool:
        """Return True if *pcm* contains at least *min_speech_frames* speech frames.

        Useful for pre-screening recorded audio before sending to STT.
        Returns False when VAD is unavailable.
        """
        if not VAD_AVAILABLE:
            return False

        try:
            instance = cls(
                sample_rate=sample_rate,
                aggressiveness=aggressiveness,
                frame_ms=frame_ms,
                ring_size=1,
            )
        except ValueError:
            return False

        frame_size = sample_rate * frame_ms // 1000 * 2
        speech_count = 0
        offset = 0
        while offset + frame_size <= len(pcm):
            if instance.is_speech_frame(pcm[offset : offset + frame_size]):
                speech_count += 1
                if speech_count >= min_speech_frames:
                    return True
            offset += frame_size

        return False

    def filter_chunks(
        self,
        chunks: Iterable[bytes],
    ) -> Iterator[tuple[bytes, bool]]:
        """Yield ``(chunk, is_speaking)`` pairs for each input chunk."""
        for chunk in chunks:
            yield chunk, self.process_chunk(chunk)