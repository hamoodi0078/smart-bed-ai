"""Speaker diarization via pyannote.audio (who-spoke-when).

Wraps pyannote/speaker-diarization-3.1 with lazy model loading, thread safety,
and graceful fallback when the library is not installed or the HF token is absent.

Requirements:
  - pyannote.audio>=3.1.0 installed
  - Hugging Face access token (HF_TOKEN in .env)
  - Model licence accepted at huggingface.co/pyannote/speaker-diarization-3.1
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

try:
    from pyannote.audio import Pipeline as _PyannotePipeline

    PYANNOTE_AVAILABLE = True
except ImportError:
    _PyannotePipeline = None  # type: ignore[assignment,misc]
    PYANNOTE_AVAILABLE = False


@dataclass
class DiarizedSegment:
    """One speaker turn returned by the diarization pipeline."""

    start: float  # seconds from audio start
    end: float  # seconds
    speaker: str  # e.g. "SPEAKER_00"

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end - self.start)


class SpeakerDiarizer:
    """Thread-safe wrapper around pyannote/speaker-diarization-3.1.

    Parameters
    ----------
    hf_token:
        Hugging Face access token.  Required to download the pretrained model.
    model_name:
        HF repo ID for the diarization pipeline.
    device:
        ``"cpu"`` or ``"cuda"`` — forwarded to ``pipeline.to()``.
    """

    DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"

    def __init__(
        self,
        hf_token: str = "",
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        self._hf_token = str(hf_token or "").strip()
        self._model_name = str(model_name or self.DEFAULT_MODEL).strip()
        self._device = str(device or "cpu").strip()
        self._pipeline: Any = None
        self._load_error: str | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Pipeline lifecycle
    # ------------------------------------------------------------------

    def load_pipeline(self) -> bool:
        """Lazily load the pyannote pipeline.  Returns True on success."""
        if not PYANNOTE_AVAILABLE:
            return False
        with self._lock:
            if self._pipeline is not None:
                return True
            if self._load_error is not None:
                return False
            try:
                pipeline = _PyannotePipeline.from_pretrained(
                    self._model_name,
                    use_auth_token=self._hf_token or None,
                )
                try:
                    import torch

                    pipeline.to(torch.device(self._device))
                except Exception:
                    pass  # torch unavailable or device unsupported — run on CPU
                self._pipeline = pipeline
                logger.info("pyannote diarization pipeline loaded ({})", self._model_name)
                return True
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning("pyannote pipeline failed to load: {}", exc)
                return False

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    # ------------------------------------------------------------------
    # Diarization
    # ------------------------------------------------------------------

    def diarize_wav_bytes(
        self,
        wav_bytes: bytes,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> list[DiarizedSegment]:
        """Run diarization on a WAV blob.  Returns ``[]`` on any failure."""
        if not self.load_pipeline():
            return []
        try:
            import io
            import wave

            import numpy as np
            import torch

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())

            if sampwidth != 2:
                logger.debug("diarize_wav_bytes: unsupported sampwidth {}", sampwidth)
                return []

            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            if n_channels > 1:
                # Mix down to mono — pyannote works on single-channel audio
                arr = arr.reshape(-1, n_channels).mean(axis=1)

            # pyannote expects float32 tensor shape (1, samples)
            waveform = torch.from_numpy(arr).unsqueeze(0)

            kwargs: dict[str, int] = {}
            if min_speakers is not None:
                kwargs["min_speakers"] = int(min_speakers)
            if max_speakers is not None:
                kwargs["max_speakers"] = int(max_speakers)

            with self._lock:
                diarization = self._pipeline(
                    {"waveform": waveform, "sample_rate": sample_rate},
                    **kwargs,
                )

            return self._parse_annotation(diarization)
        except Exception as exc:
            logger.debug("diarize_wav_bytes error: {}", exc)
            return []

    def diarize_file(
        self,
        path: str | Path,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> list[DiarizedSegment]:
        """Run diarization on a WAV file path.  Returns ``[]`` on any failure."""
        try:
            p = Path(path)
            if not p.exists():
                return []
            return self.diarize_wav_bytes(
                p.read_bytes(),
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
        except Exception as exc:
            logger.debug("diarize_file error: {}", exc)
            return []

    @staticmethod
    def _parse_annotation(annotation: Any) -> list[DiarizedSegment]:
        segments: list[DiarizedSegment] = []
        try:
            for turn, _, speaker in annotation.itertracks(yield_label=True):
                segments.append(
                    DiarizedSegment(
                        start=float(turn.start),
                        end=float(turn.end),
                        speaker=str(speaker),
                    )
                )
        except Exception as exc:
            logger.debug("_parse_annotation error: {}", exc)
        return segments

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def speaker_summary(segments: list[DiarizedSegment]) -> dict[str, Any]:
        """Return per-speaker activity stats from a diarized segment list."""
        if not segments:
            return {
                "num_speakers": 0,
                "primary_speaker": None,
                "speaker_durations": {},
                "total_speech_seconds": 0.0,
            }

        durations: dict[str, float] = {}
        for seg in segments:
            durations[seg.speaker] = durations.get(seg.speaker, 0.0) + seg.duration_s

        primary = max(durations, key=lambda s: durations[s])
        return {
            "num_speakers": len(durations),
            "primary_speaker": primary,
            "speaker_durations": {k: round(v, 3) for k, v in sorted(durations.items())},
            "total_speech_seconds": round(sum(durations.values()), 3),
        }

    def extract_primary_speaker_wav(
        self,
        wav_bytes: bytes,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> bytes:
        """Return a WAV containing only the most-spoken speaker's frames.

        The non-primary frames are zeroed out so the output has the same
        length and header as the input — downstream processors don't need to
        adjust timestamps.  Falls back to the original WAV when pyannote is
        unavailable or no segments are produced.
        """
        segments = self.diarize_wav_bytes(
            wav_bytes,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        if not segments:
            return wav_bytes

        summary = self.speaker_summary(segments)
        primary = summary["primary_speaker"]
        primary_segs = [s for s in segments if s.speaker == primary]

        try:
            import io
            import wave

            import numpy as np

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())

            if sampwidth != 2:
                return wav_bytes

            arr = np.frombuffer(raw, dtype="<i2").copy()
            samples_per_second = sample_rate * n_channels

            # Zero out every frame, then copy back only primary-speaker windows
            masked = np.zeros_like(arr)
            for seg in primary_segs:
                s = max(0, int(seg.start * samples_per_second))
                e = min(len(arr), int(seg.end * samples_per_second))
                if s < e:
                    masked[s:e] = arr[s:e]

            out = io.BytesIO()
            with wave.open(out, "wb") as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(masked.tobytes())
            return out.getvalue()
        except Exception as exc:
            logger.debug("extract_primary_speaker_wav error: {}", exc)
            return wav_bytes
