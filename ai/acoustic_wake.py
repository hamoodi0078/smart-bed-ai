"""On-device acoustic wake-word detection — no cloud, no transcription.

Replaces the record→cloud-STT→text-match wake loop with a continuous local
keyword spotter. The microphone audio never leaves the device until the wake
phrase has been heard, and detection latency is tens of milliseconds instead
of seconds.

Backends (selected via WAKE_ACOUSTIC_BACKEND=auto|porcupine|openwakeword|off):

porcupine (Picovoice)
    pip install pvporcupine
    Needs PORCUPINE_ACCESS_KEY (free at console.picovoice.ai) and a custom
    keyword file for the wake phrase (e.g. "Hey Dana") exported from the
    console as .ppn — path in PORCUPINE_KEYWORD_PATH.

openwakeword
    pip install openwakeword
    Needs a model file (.onnx or .tflite) for the wake phrase — train once
    via openWakeWord's Colab notebook — path in OPENWAKEWORD_MODEL_PATH.

Both consume 16 kHz mono int16 frames from the default (or configured)
input device via sounddevice. When neither backend is configured the
detector reports unavailable and callers fall back to the legacy text-match
wake loop, so this module is always safe to construct.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from loguru import logger

try:
    import sounddevice as _sd
except Exception:  # pragma: no cover - optional runtime dependency
    _sd = None

try:
    import pvporcupine as _pvporcupine
except Exception:  # pragma: no cover - optional runtime dependency
    _pvporcupine = None

try:
    from openwakeword.model import Model as _OwwModel
except Exception:  # pragma: no cover - optional runtime dependency
    _OwwModel = None


_SAMPLE_RATE = 16_000
_OWW_FRAME_SAMPLES = 1_280  # 80 ms — openWakeWord's recommended chunk


class AcousticWakeDetector:
    """Continuous local keyword spotting with a blocking wait_for_wake()."""

    def __init__(
        self,
        *,
        backend: str = "auto",
        porcupine_access_key: str = "",
        porcupine_keyword_path: str = "",
        openwakeword_model_path: str = "",
        sensitivity: float = 0.6,
        mic_device_index: Optional[int] = None,
        engine=None,
        stream_factory: Optional[Callable] = None,
    ):
        self._backend_name = str(backend or "auto").strip().lower()
        self._sensitivity = max(0.05, min(0.95, float(sensitivity)))
        self._mic_device_index = mic_device_index
        self._stream_factory = stream_factory
        self._stop_event = threading.Event()
        self._engine = None
        self._engine_kind = ""
        self._frame_samples = _OWW_FRAME_SAMPLES
        self._status = "Acoustic wake disabled."

        if self._backend_name == "off":
            self._status = "Acoustic wake disabled (WAKE_ACOUSTIC_BACKEND=off)."
            return

        if engine is not None:
            # Test / advanced injection path: engine must expose process(frame)->bool
            self._engine = engine
            self._engine_kind = "injected"
            self._frame_samples = int(getattr(engine, "frame_length", _OWW_FRAME_SAMPLES))
            self._status = "Acoustic wake active (injected engine)."
            return

        if self._backend_name in ("auto", "porcupine"):
            self._try_init_porcupine(porcupine_access_key, porcupine_keyword_path)
        if self._engine is None and self._backend_name in ("auto", "openwakeword"):
            self._try_init_openwakeword(openwakeword_model_path)

        if self._engine is None and self._backend_name != "auto":
            logger.warning("Acoustic wake backend '{}' unavailable: {}", backend, self._status)

    # ── Backend init ──────────────────────────────────────────────────────────

    def _try_init_porcupine(self, access_key: str, keyword_path: str) -> None:
        access_key = str(access_key or "").strip()
        keyword_path = str(keyword_path or "").strip()
        if _pvporcupine is None:
            self._status = "Acoustic wake unavailable: pvporcupine not installed."
            return
        if not access_key or not keyword_path:
            self._status = (
                "Acoustic wake unavailable: set PORCUPINE_ACCESS_KEY and "
                "PORCUPINE_KEYWORD_PATH for the porcupine backend."
            )
            return
        try:
            porcupine = _pvporcupine.create(
                access_key=access_key,
                keyword_paths=[keyword_path],
                sensitivities=[self._sensitivity],
            )
        except Exception as exc:
            self._status = f"Acoustic wake unavailable (porcupine init failed): {exc}"
            logger.warning("Porcupine init failed: {}", exc)
            return

        class _PorcupineEngine:
            frame_length = int(porcupine.frame_length)

            @staticmethod
            def process(frame) -> bool:
                return porcupine.process(frame) >= 0

            @staticmethod
            def close() -> None:
                porcupine.delete()

        self._engine = _PorcupineEngine()
        self._engine_kind = "porcupine"
        self._frame_samples = _PorcupineEngine.frame_length
        self._status = "Acoustic wake active: porcupine keyword spotting on-device."

    def _try_init_openwakeword(self, model_path: str) -> None:
        model_path = str(model_path or "").strip()
        if _OwwModel is None:
            self._status = "Acoustic wake unavailable: openwakeword not installed."
            return
        if not model_path:
            self._status = (
                "Acoustic wake unavailable: set OPENWAKEWORD_MODEL_PATH for the "
                "openwakeword backend."
            )
            return
        try:
            model = _OwwModel(wakeword_models=[model_path])
        except Exception as exc:
            self._status = f"Acoustic wake unavailable (openwakeword init failed): {exc}"
            logger.warning("openWakeWord init failed: {}", exc)
            return

        threshold = self._sensitivity

        class _OwwEngine:
            frame_length = _OWW_FRAME_SAMPLES

            @staticmethod
            def process(frame) -> bool:
                scores = model.predict(frame)
                return any(float(score) >= threshold for score in scores.values())

            @staticmethod
            def close() -> None:
                return

        self._engine = _OwwEngine()
        self._engine_kind = "openwakeword"
        self._status = "Acoustic wake active: openWakeWord spotting on-device."

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._engine is not None and (self._stream_factory is not None or _sd is not None)

    def status_line(self) -> str:
        return self._status

    def wait_for_wake(self, timeout_seconds: Optional[float] = None) -> bool:
        """Block until the wake phrase is heard. Returns False on timeout/stop.

        Audio is processed frame-by-frame on-device; nothing is transcribed
        or uploaded.
        """
        if not self.available:
            return False

        self._stop_event.clear()
        deadline = (time.monotonic() + float(timeout_seconds)) if timeout_seconds else None

        stream_factory = self._stream_factory or self._default_stream_factory
        try:
            with stream_factory(self._frame_samples) as read_frame:
                while not self._stop_event.is_set():
                    if deadline is not None and time.monotonic() >= deadline:
                        return False
                    frame = read_frame()
                    if frame is None:
                        continue
                    try:
                        if self._engine.process(frame):
                            return True
                    except Exception as exc:
                        logger.warning("Acoustic wake engine error: {}", exc)
                        return False
        except Exception as exc:
            self._status = f"Acoustic wake stream error: {exc}"
            logger.warning("Acoustic wake stream error: {}", exc)
            return False
        return False

    def stop(self) -> None:
        self._stop_event.set()

    def close(self) -> None:
        self.stop()
        engine = self._engine
        self._engine = None
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

    # ── Default sounddevice capture ───────────────────────────────────────────

    def _default_stream_factory(self, frame_samples: int):
        """Context manager yielding a read_frame() -> list[int] callable."""
        detector = self

        class _SdStream:
            def __enter__(self):
                self._stream = _sd.InputStream(
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=frame_samples,
                    device=detector._mic_device_index,
                )
                self._stream.start()

                def read_frame():
                    data, overflowed = self._stream.read(frame_samples)
                    if overflowed:
                        logger.debug("Acoustic wake: input overflow, frame dropped")
                    # numpy int16 (n,1) -> flat int16 sequence for both engines
                    return data[:, 0]

                return read_frame

            def __exit__(self, *exc_info):
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                return False

        return _SdStream()


def build_acoustic_wake_detector(settings) -> AcousticWakeDetector:
    """Construct the detector from application settings (never raises)."""
    try:
        mic_index = int(getattr(settings, "wake_word_mic_index", -1))
    except Exception:
        mic_index = -1
    return AcousticWakeDetector(
        backend=str(getattr(settings, "wake_acoustic_backend", "auto") or "auto"),
        porcupine_access_key=str(getattr(settings, "porcupine_access_key", "") or ""),
        porcupine_keyword_path=str(getattr(settings, "porcupine_keyword_path", "") or ""),
        openwakeword_model_path=str(getattr(settings, "openwakeword_model_path", "") or ""),
        sensitivity=float(getattr(settings, "wake_acoustic_sensitivity", 0.6) or 0.6),
        mic_device_index=mic_index if mic_index >= 0 else None,
    )
