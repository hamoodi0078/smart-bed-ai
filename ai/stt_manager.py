import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode

import numpy as np
import requests

try:
    import audioop
except Exception:  # pragma: no cover - audioop removed in newer Python
    audioop = None

try:
    import pyaudio as _pyaudio
except Exception:  # pragma: no cover - PyAudio requires PortAudio system library
    _pyaudio = None

try:
    from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
except Exception:  # pragma: no cover - optional runtime dependency
    DeepgramClient = None
    LiveTranscriptionEvents = None
    LiveOptions = None

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover - optional runtime dependency
    WhisperModel = None

try:
    import speech_recognition as sr
except Exception:  # pragma: no cover - optional runtime dependency
    sr = None

try:
    import noisereduce as _nr
    _NOISEREDUCE_AVAILABLE = True
except ImportError:
    _nr = None  # type: ignore[assignment]
    _NOISEREDUCE_AVAILABLE = False

try:
    import pyloudnorm as _pyln
    _PYLOUDNORM_AVAILABLE = True
except ImportError:
    _pyln = None  # type: ignore[assignment]
    _PYLOUDNORM_AVAILABLE = False

try:
    import sounddevice as _sd
    _SOUNDDEVICE_AVAILABLE = True
except ImportError:
    _sd = None  # type: ignore[assignment]
    _SOUNDDEVICE_AVAILABLE = False

try:
    from ai.speaker_diarization import SpeakerDiarizer as _SpeakerDiarizer
    from ai.speaker_diarization import PYANNOTE_AVAILABLE as _PYANNOTE_AVAILABLE
except Exception:
    try:
        from speaker_diarization import SpeakerDiarizer as _SpeakerDiarizer  # type: ignore[no-redef]
        from speaker_diarization import PYANNOTE_AVAILABLE as _PYANNOTE_AVAILABLE  # type: ignore[no-redef]
    except Exception:
        _SpeakerDiarizer = None  # type: ignore[assignment,misc]
        _PYANNOTE_AVAILABLE = False

try:
    from ai.vad_filter import VadFilter as _VadFilter
    from ai.vad_filter import VAD_AVAILABLE as _VAD_AVAILABLE
except Exception:  # pragma: no cover - relative import may fail in some entry points
    try:
        from vad_filter import VadFilter as _VadFilter  # type: ignore[no-redef]
        from vad_filter import VAD_AVAILABLE as _VAD_AVAILABLE  # type: ignore[no-redef]
    except Exception:
        _VadFilter = None  # type: ignore[assignment,misc]
        _VAD_AVAILABLE = False


class STTManager:
    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        timeout_seconds: int = 20,
        language_hint: str = "auto",
        mode: str = "api",
        local_model_size: str = "small",
        local_device: str = "cpu",
        local_compute_type: str = "int8",
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.language_hint = language_hint
        self.mode = (mode or "local").strip().lower()
        self.local_model_size = local_model_size
        self.local_device = local_device
        self.local_compute_type = local_compute_type
        self._local_model = None
        self._deepgram_client = None

    def _clamp_confidence(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _pcm_rms(self, raw: bytes, sample_width: int) -> float:
        if not raw:
            return 0.0
        if audioop is not None:
            try:
                return float(audioop.rms(raw, sample_width))
            except Exception:
                pass

        if sample_width != 2:
            return 0.0

        samples = np.frombuffer(raw, dtype="<i2")
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

    def _estimate_text_confidence(self, text: str, base: float = 0.58) -> float:
        words = [w for w in str(text or "").strip().split() if w]
        if not words:
            return 0.0

        bonus = min(0.24, len(words) * 0.03)
        penalty = 0.0
        if len(words) == 1 and len(words[0]) <= 3:
            penalty = 0.14
        return self._clamp_confidence(base + bonus - penalty)

    def _denoise_wav_bytes(self, wav_bytes: bytes) -> bytes:
        """Apply spectral-gate noise reduction to a WAV blob.

        Parses the WAV header, denoises the int16 PCM with noisereduce, and
        re-encodes as a standard WAV.  Falls back to the original bytes on any
        error so STT is never blocked by a denoising failure.
        """
        if not _NOISEREDUCE_AVAILABLE or _nr is None:
            return wav_bytes
        try:
            import io
            import wave

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())

            if sampwidth != 2:
                return wav_bytes  # only 16-bit PCM supported

            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

            if n_channels > 1:
                # noisereduce expects (channels, samples) for multi-channel audio
                arr = arr.reshape(-1, n_channels).T

            denoised = _nr.reduce_noise(y=arr, sr=framerate)

            if n_channels > 1:
                denoised = denoised.T.flatten()

            int16 = np.clip(denoised * 32768.0, -32768, 32767).astype("<i2")

            out = io.BytesIO()
            with wave.open(out, "wb") as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(2)
                wf.setframerate(framerate)
                wf.writeframes(int16.tobytes())
            return out.getvalue()
        except Exception:
            return wav_bytes

    def _normalize_loudness_wav_bytes(
        self, wav_bytes: bytes, target_lufs: float = -23.0
    ) -> bytes:
        """Normalize integrated loudness of a WAV blob to *target_lufs* LUFS (EBU R128).

        Measures loudness with a BS.1770 meter then rescales so the clip lands at
        *target_lufs*.  Falls back to the original bytes when:
        - pyloudnorm is not installed
        - the clip is shorter than 400 ms (BS.1770 minimum gate window)
        - the signal is silent (integrated loudness = -inf)
        - any parsing or processing error occurs
        """
        if not _PYLOUDNORM_AVAILABLE or _pyln is None:
            return wav_bytes
        try:
            import io
            import math
            import wave

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            if sampwidth != 2:
                return wav_bytes  # only 16-bit PCM supported

            # BS.1770 requires at least ~400 ms to measure integrated loudness
            if n_frames / max(1, framerate) < 0.4:
                return wav_bytes

            # pyloudnorm expects float64 in [-1, 1], shape (samples,) mono
            # or (samples, channels) for multi-channel
            arr = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
            if n_channels > 1:
                arr = arr.reshape(-1, n_channels)

            meter = _pyln.Meter(framerate)
            loudness = meter.integrated_loudness(arr)

            if not math.isfinite(loudness):
                return wav_bytes  # silence — nothing to normalize

            normalized = _pyln.normalize.loudness(arr, loudness, float(target_lufs))

            if n_channels > 1:
                normalized = normalized.reshape(-1)  # back to interleaved

            int16 = np.clip(normalized * 32768.0, -32768, 32767).astype("<i2")

            out = io.BytesIO()
            with wave.open(out, "wb") as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(2)
                wf.setframerate(framerate)
                wf.writeframes(int16.tobytes())
            return out.getvalue()
        except Exception:
            return wav_bytes

    def _normalized_language_hint(self, text_context: str = "") -> str | None:
        hint = str(self.language_hint or "").strip().lower()
        if hint not in ("", "auto", "any", "all"):
            return hint
        # Auto-detect: if user typed Arabic before pressing the mic, use ar
        if text_context:
            try:
                from core.arabic_utils import detect_language
                detected = detect_language(text_context)
                if detected == "ar":
                    return "ar"
            except Exception:
                pass
        return None

    def _is_local_mode(self) -> bool:
        return self.mode in ("local", "hybrid")

    def _is_api_mode(self) -> bool:
        return self.mode in ("api", "hybrid")

    @staticmethod
    def list_audio_devices() -> list[dict]:
        """Return detailed info for every audio input device.

        Tries three backends in order: PyAudio (most detailed), sounddevice
        (nearly as detailed, no teardown required), SpeechRecognition (names only).
        Each dict: {index, name, max_input_channels, default_sample_rate, is_default_input}
        """
        if _pyaudio is not None:
            pa = _pyaudio.PyAudio()
            try:
                default_index = -1
                try:
                    default_index = pa.get_default_input_device_info()["index"]
                except Exception:
                    pass
                devices = []
                for i in range(pa.get_device_count()):
                    try:
                        info = pa.get_device_info_by_index(i)
                        if int(info.get("maxInputChannels", 0)) > 0:
                            devices.append({
                                "index": i,
                                "name": str(info.get("name", "")),
                                "max_input_channels": int(info.get("maxInputChannels", 1)),
                                "default_sample_rate": int(info.get("defaultSampleRate", 44100)),
                                "is_default_input": i == default_index,
                            })
                    except Exception:
                        continue
                return devices
            finally:
                pa.terminate()

        # Fallback: sounddevice (same PortAudio backend, no manual teardown needed)
        if _sd is not None:
            try:
                default_index = -1
                try:
                    default_info = _sd.query_devices(kind="input")
                    if isinstance(default_info, dict):
                        default_index = int(default_info.get("index", -1))
                except Exception:
                    pass
                all_devices = _sd.query_devices()
                devices = []
                for i, d in enumerate(all_devices):
                    if int(d.get("max_input_channels", 0)) > 0:
                        devices.append({
                            "index": i,
                            "name": str(d.get("name", "")),
                            "max_input_channels": int(d.get("max_input_channels", 1)),
                            "default_sample_rate": int(d.get("default_samplerate", 44100)),
                            "is_default_input": i == default_index,
                        })
                if devices:
                    return devices
            except Exception:
                pass

        # Last resort: SpeechRecognition names only
        if sr is not None:
            return [
                {"index": i, "name": name, "max_input_channels": 1,
                 "default_sample_rate": 44100, "is_default_input": False}
                for i, name in enumerate(sr.Microphone.list_microphone_names())
            ]
        return []

    @staticmethod
    def find_best_mic_index(preferred_rate: int = 16000) -> int | None:
        """Return the index of the best available input device for the given sample rate.

        Prefers the system default input; falls back to the first device that
        supports the preferred_rate (or any input device if none matches exactly).
        """
        devices = STTManager.list_audio_devices()
        if not devices:
            return None
        for d in devices:
            if d.get("is_default_input"):
                return int(d["index"])
        for d in devices:
            if int(d.get("default_sample_rate", 0)) == preferred_rate:
                return int(d["index"])
        return int(devices[0]["index"])

    def _load_local_model(self):
        if self._local_model is not None:
            return self._local_model
        if WhisperModel is None:
            return None

        try:
            self._local_model = WhisperModel(
                self.local_model_size,
                device=self.local_device,
                compute_type=self.local_compute_type,
            )
            return self._local_model
        except Exception:
            return None

    def _transcribe_local_with_confidence(self, path: Path) -> tuple[str, float]:
        model = self._load_local_model()
        if model is None:
            return "", 0.0

        try:
            language_hint = self._normalized_language_hint()
            segments, _ = model.transcribe(
                str(path),
                language=language_hint,
                vad_filter=True,
                beam_size=1,
            )
            collected = []
            confidence_samples = []
            for seg in segments:
                seg_text = str(getattr(seg, "text", "") or "").strip()
                if seg_text:
                    collected.append(seg_text)

                no_speech_prob = getattr(seg, "no_speech_prob", None)
                if isinstance(no_speech_prob, (int, float)):
                    confidence_samples.append(self._clamp_confidence(1.0 - float(no_speech_prob)))

            text = " ".join(collected).strip()
            if not text:
                return "", 0.0

            if confidence_samples:
                confidence = sum(confidence_samples) / len(confidence_samples)
            else:
                confidence = self._estimate_text_confidence(text, base=0.6)

            return text, self._clamp_confidence(confidence)
        except Exception:
            return "", 0.0

    def _transcribe_local(self, path: Path) -> str:
        text, _ = self._transcribe_local_with_confidence(path)
        return text

    def _build_deepgram_listen_url(self) -> str:
        params = {
            "model": str(self.model or "nova-2").strip() or "nova-2",
            "smart_format": "true",
            "punctuate": "true",
        }
        language_hint = self._normalized_language_hint()
        if language_hint:
            params["language"] = language_hint
        else:
            params["detect_language"] = "true"
        return f"https://api.deepgram.com/v1/listen?{urlencode(params)}"

    def _extract_deepgram_result(self, body: dict) -> tuple[str, float]:
        try:
            channels = body.get("results", {}).get("channels", [])
            if not channels:
                return "", 0.0
            alternatives = channels[0].get("alternatives", [])
            if not alternatives:
                return "", 0.0
            top = alternatives[0] if isinstance(alternatives[0], dict) else {}
            text = str(top.get("transcript", "") or "").strip()
            if not text:
                return "", 0.0

            confidence = top.get("confidence")
            if isinstance(confidence, (int, float)):
                score = self._clamp_confidence(float(confidence))
            else:
                score = self._estimate_text_confidence(text, base=0.68)
            return text, score
        except Exception:
            return "", 0.0

    def _transcribe_api_with_confidence(self, path: Path) -> tuple[str, float]:
        if not self.api_key:
            return "", 0.0

        url = self._build_deepgram_listen_url()
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
        }

        try:
            wav_bytes = path.read_bytes()
            wav_bytes = self._denoise_wav_bytes(wav_bytes)
            wav_bytes = self._normalize_loudness_wav_bytes(wav_bytes)
            response = requests.post(
                url,
                headers=headers,
                data=wav_bytes,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            return self._extract_deepgram_result(body)
        except Exception:
            return "", 0.0

    def _transcribe_api(self, path: Path) -> str:
        text, _ = self._transcribe_api_with_confidence(path)
        return text

    def _load_deepgram_client(self):
        if self._deepgram_client is not None:
            return self._deepgram_client
        if not self.api_key or DeepgramClient is None:
            return None
        try:
            self._deepgram_client = DeepgramClient(self.api_key)
            return self._deepgram_client
        except Exception:
            return None

    def transcribe_stream_with_interim(
        self,
        audio_chunks: Iterable[bytes],
        interim_callback: Callable[[str, float], None] | None = None,
        sample_rate_hz: int = 16000,
    ) -> tuple[str, float]:
        """
        Streams PCM chunks to Deepgram Nova-2 with interim results.
        This enables upstream callers to start intent handling before the speaker finishes.
        """
        client = self._load_deepgram_client()
        if client is None or LiveTranscriptionEvents is None or LiveOptions is None:
            return "", 0.0

        try:
            connection = client.listen.websocket.v("1")
        except Exception:
            return "", 0.0

        state = {
            "latest_interim": "",
            "latest_interim_confidence": 0.0,
            "final_text": "",
            "final_confidence": 0.0,
        }

        def _on_transcript(_self, result, **_kwargs):
            channel = getattr(result, "channel", None)
            alternatives = getattr(channel, "alternatives", []) if channel is not None else []
            if not alternatives:
                return

            top = alternatives[0]
            transcript = str(getattr(top, "transcript", "") or "").strip()
            if not transcript:
                return

            confidence = getattr(top, "confidence", None)
            if isinstance(confidence, (int, float)):
                score = self._clamp_confidence(float(confidence))
            else:
                score = self._estimate_text_confidence(transcript, base=0.66)

            is_final = bool(getattr(result, "is_final", False))
            if is_final:
                state["final_text"] = transcript
                state["final_confidence"] = score
                return

            state["latest_interim"] = transcript
            state["latest_interim_confidence"] = score
            if interim_callback is not None:
                try:
                    interim_callback(transcript, score)
                except Exception as _cb_exc:
                    from loguru import logger as _log
                    _log.warning("interim_callback raised: {}", _cb_exc)

        try:
            connection.on(LiveTranscriptionEvents.Transcript, _on_transcript)
            options_payload = {
                "model": str(self.model or "nova-2").strip() or "nova-2",
                "interim_results": True,
                "punctuate": True,
                "smart_format": True,
                "sample_rate": max(8000, int(sample_rate_hz)),
                "encoding": "linear16",
                "channels": 1,
            }
            language_hint = self._normalized_language_hint()
            if language_hint:
                options_payload["language"] = language_hint
            options = LiveOptions(**options_payload)
            if not connection.start(options):
                return "", 0.0

            for chunk in audio_chunks:
                if chunk:
                    connection.send(chunk)

            connection.finish()
        except Exception:
            try:
                connection.finish()
            except Exception:
                pass
            return "", 0.0

        if state["final_text"]:
            return state["final_text"], state["final_confidence"]
        if state["latest_interim"]:
            return state["latest_interim"], state["latest_interim_confidence"]
        return "", 0.0

    def _transcribe_microphone_once_via_api(
        self,
        mic_device_index: int | None = None,
        timeout_seconds: int = 5,
        max_phrase_seconds: float = 16.0,
    ) -> tuple[str, float]:
        if sr is None or not self.api_key:
            return "", 0.0

        try:
            recognizer = sr.Recognizer()
            with sr.Microphone(device_index=mic_device_index) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = recognizer.listen(
                    source,
                    timeout=max(1.0, float(timeout_seconds)),
                    phrase_time_limit=max(1.0, float(max_phrase_seconds)),
                )
            wav_bytes = audio.get_wav_data()
            if not wav_bytes:
                return "", 0.0

            wav_bytes = self._denoise_wav_bytes(wav_bytes)
            wav_bytes = self._normalize_loudness_wav_bytes(wav_bytes)

            url = self._build_deepgram_listen_url()
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "audio/wav",
            }
            response = requests.post(
                url,
                headers=headers,
                data=wav_bytes,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return self._extract_deepgram_result(response.json())
        except Exception:
            return "", 0.0

    def _transcribe_microphone_sounddevice_with_interim(
        self,
        mic_device_index: int | None = None,
        timeout_seconds: int = 5,
        max_phrase_seconds: float = 16.0,
        silence_end_seconds: float = 0.8,
        interim_callback: Callable[[str, float], None] | None = None,
        sample_rate: int = 16000,
    ) -> tuple[str, float]:
        """Capture mic audio via sounddevice and stream to Deepgram with interim results.

        Used as a drop-in replacement for the PyAudio/SpeechRecognition path when
        those libraries are unavailable.  Uses a callback-driven RawInputStream that
        pushes int16 PCM chunks into a queue consumed by the _chunks() generator,
        then feeds the same transcribe_stream_with_interim pipeline.
        """
        if _sd is None or not self._is_api_mode():
            return "", 0.0

        import queue as _queue

        chunk_size = 1024
        sample_width = 2  # int16 → 2 bytes per sample
        frame_duration = chunk_size / max(1, sample_rate)
        speech_threshold = 80.0

        audio_queue: _queue.Queue[bytes | None] = _queue.Queue()

        def _sd_callback(indata, _frames, _time, _status):
            audio_queue.put(bytes(indata))

        _vad_instance = None
        if _VAD_AVAILABLE and _VadFilter is not None:
            try:
                _vad_instance = _VadFilter(
                    sample_rate=sample_rate,
                    aggressiveness=2,
                    frame_ms=20,
                )
            except Exception:
                pass

        hard_start = time.monotonic() + max(1.0, float(timeout_seconds))
        hard_deadline = hard_start + max(3.0, float(max_phrase_seconds))
        speaking_started = False
        silence_duration = 0.0

        def _chunks():
            nonlocal speaking_started, silence_duration
            while True:
                now = time.monotonic()
                if now >= hard_deadline:
                    break
                try:
                    raw = audio_queue.get(timeout=0.1)
                except _queue.Empty:
                    continue
                if raw is None:
                    break

                if _vad_instance is not None:
                    is_speech = _vad_instance.process_chunk(raw)
                else:
                    is_speech = self._pcm_rms(raw, sample_width) >= speech_threshold

                if is_speech:
                    speaking_started = True
                    silence_duration = 0.0
                elif speaking_started:
                    silence_duration += frame_duration

                if not speaking_started and now >= hard_start:
                    break

                yield raw

                if speaking_started and silence_duration >= max(0.25, float(silence_end_seconds)):
                    break

        try:
            with _sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=chunk_size,
                device=mic_device_index,
                channels=1,
                dtype="int16",
                callback=_sd_callback,
            ):
                text, confidence = self.transcribe_stream_with_interim(
                    audio_chunks=_chunks(),
                    interim_callback=interim_callback,
                    sample_rate_hz=sample_rate,
                )
            if text:
                return text, confidence
        except Exception:
            pass

        return "", 0.0

    def transcribe_microphone_with_interim(
        self,
        mic_device_index: int | None = None,
        timeout_seconds: int = 5,
        max_phrase_seconds: float = 16.0,
        silence_end_seconds: float = 0.8,
        interim_callback: Callable[[str, float], None] | None = None,
    ) -> tuple[str, float]:
        """
        Captures microphone PCM frames and streams them to Deepgram with interim results.
        The stream ends after trailing silence or the max phrase budget.

        Capture priority: SpeechRecognition/PyAudio → sounddevice RawInputStream.
        """
        if not self._is_api_mode():
            return "", 0.0

        if sr is None:
            # SpeechRecognition / PyAudio unavailable — delegate to sounddevice path.
            return self._transcribe_microphone_sounddevice_with_interim(
                mic_device_index=mic_device_index,
                timeout_seconds=timeout_seconds,
                max_phrase_seconds=max_phrase_seconds,
                silence_end_seconds=silence_end_seconds,
                interim_callback=interim_callback,
            )

        for attempt in range(2):
            try:
                recognizer = sr.Recognizer()
                with sr.Microphone(device_index=mic_device_index, sample_rate=16000) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    chunk_size = int(getattr(source, "CHUNK", 1024) or 1024)
                    sample_rate = int(getattr(source, "SAMPLE_RATE", 16000) or 16000)
                    sample_width = int(getattr(source, "SAMPLE_WIDTH", 2) or 2)
                    frame_duration = max(0.01, float(chunk_size) / float(max(1, sample_rate)))
                    ambient_threshold = float(getattr(recognizer, "energy_threshold", 180.0) or 180.0)
                    speech_threshold = max(80.0, ambient_threshold * 1.25)

                    hard_start = time.monotonic() + max(1.0, float(timeout_seconds))
                    hard_deadline = hard_start + max(3.0, float(max_phrase_seconds))
                    speaking_started = False
                    silence_duration = 0.0

                    # Prefer WebRTC VAD; fall back to RMS threshold when unavailable.
                    _vad_instance = None
                    if _VAD_AVAILABLE and _VadFilter is not None:
                        try:
                            _vad_instance = _VadFilter(
                                sample_rate=sample_rate,
                                aggressiveness=2,
                                frame_ms=20,
                            )
                        except Exception:
                            _vad_instance = None

                    def _chunks():
                        nonlocal speaking_started, silence_duration
                        while True:
                            now = time.monotonic()
                            if now >= hard_deadline:
                                break

                            raw = source.stream.read(chunk_size, exception_on_overflow=False)
                            if not raw:
                                continue

                            if _vad_instance is not None:
                                is_speech = _vad_instance.process_chunk(raw)
                            else:
                                is_speech = self._pcm_rms(raw, sample_width) >= speech_threshold

                            if is_speech:
                                speaking_started = True
                                silence_duration = 0.0
                            elif speaking_started:
                                silence_duration += frame_duration

                            if not speaking_started and now >= hard_start:
                                break

                            yield raw

                            if speaking_started and silence_duration >= max(0.25, float(silence_end_seconds)):
                                break

                    text, confidence = self.transcribe_stream_with_interim(
                        audio_chunks=_chunks(),
                        interim_callback=interim_callback,
                        sample_rate_hz=sample_rate,
                    )
                    if text:
                        return text, confidence
            except Exception:
                pass

            # Keep strict API mode reliable even when websocket stream setup fails.
            text, confidence = self._transcribe_microphone_once_via_api(
                mic_device_index=mic_device_index,
                timeout_seconds=timeout_seconds,
                max_phrase_seconds=max_phrase_seconds,
            )
            if text:
                return text, confidence

            if attempt == 0:
                time.sleep(0.12)

        return "", 0.0

    def transcribe_file_with_confidence(self, audio_path: str) -> tuple[str, float]:
        path = Path(audio_path)
        if not path.exists():
            return "", 0.0

        if self._is_local_mode():
            text, confidence = self._transcribe_local_with_confidence(path)
            if text:
                return text, confidence

        if self._is_api_mode():
            text, confidence = self._transcribe_api_with_confidence(path)
            if text:
                return text, confidence

        return "", 0.0

    def warm_up(self) -> bool:
        if not self._is_local_mode():
            return False
        return self._load_local_model() is not None

    def transcribe_file(self, audio_path: str) -> str:
        text, _ = self.transcribe_file_with_confidence(audio_path)
        return text

    def transcribe_file_with_diarization(
        self,
        audio_path: str,
        hf_token: str = "",
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> dict:
        """Transcribe an audio file and annotate it with speaker turn information.

        Runs pyannote diarization to detect who-spoke-when, then transcribes the
        full file for the most accurate text.  When pyannote is unavailable the
        method degrades gracefully: it still returns a transcript with a single
        placeholder speaker and ``available=False``.

        Returns a dict::

            {
                "available": bool,          # True when diarization ran successfully
                "transcript": str,
                "confidence": float,
                "num_speakers": int,
                "segments": [               # one entry per speaker turn
                    {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.5, "duration_s": 2.5},
                    ...
                ],
                "speaker_summary": {
                    "primary_speaker": "SPEAKER_00",
                    "speaker_durations": {"SPEAKER_00": 4.1, ...},
                    "total_speech_seconds": 6.3,
                },
            }
        """
        path = Path(audio_path)
        if not path.exists():
            return {
                "available": False,
                "reason": "file not found",
                "transcript": "",
                "confidence": 0.0,
                "num_speakers": 0,
                "segments": [],
                "speaker_summary": _SpeakerDiarizer.speaker_summary([]) if _SpeakerDiarizer else {},
            }

        # Always transcribe the full file first — full-context is more accurate than
        # per-segment transcription with clipped audio.
        transcript, confidence = self.transcribe_file_with_confidence(audio_path)

        if not _PYANNOTE_AVAILABLE or _SpeakerDiarizer is None:
            return {
                "available": False,
                "reason": "pyannote.audio not installed",
                "transcript": transcript,
                "confidence": confidence,
                "num_speakers": 1 if transcript else 0,
                "segments": (
                    [{"speaker": "SPEAKER_00", "start": 0.0, "end": None, "duration_s": None}]
                    if transcript else []
                ),
                "speaker_summary": {
                    "num_speakers": 1 if transcript else 0,
                    "primary_speaker": "SPEAKER_00" if transcript else None,
                    "speaker_durations": {},
                    "total_speech_seconds": 0.0,
                },
            }

        diarizer = _SpeakerDiarizer(
            hf_token=hf_token or "",
            device="cpu",
        )
        segments = diarizer.diarize_file(
            path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        summary = _SpeakerDiarizer.speaker_summary(segments)

        return {
            "available": True,
            "transcript": transcript,
            "confidence": confidence,
            "num_speakers": summary["num_speakers"],
            "segments": [
                {
                    "speaker": seg.speaker,
                    "start": seg.start,
                    "end": seg.end,
                    "duration_s": seg.duration_s,
                }
                for seg in segments
            ],
            "speaker_summary": summary,
        }
