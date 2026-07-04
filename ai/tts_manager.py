import hashlib
from loguru import logger as _log
import re
import shutil
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

try:
    import sounddevice as _sd
except Exception:  # pragma: no cover - optional runtime dependency
    _sd = None

_STREAM_PCM_SAMPLE_RATE = 24_000  # Deepgram Aura linear16 output rate


def _write_bytes_to_path(path: Path, data: bytes) -> None:
    path.write_bytes(data)


_write_bytes_with_retry = retry(
    stop=stop_after_attempt(4),
    wait=wait_fixed(0.15),
    retry=retry_if_exception_type(PermissionError),
    reraise=False,
    before_sleep=lambda rs: _log.warning(
        "TTS write contention PermissionError attempt {}/4 — retrying",
        rs.attempt_number,
    ),
)(_write_bytes_to_path)


class TTSManager:
    def __init__(
        self,
        api_key: str,
        model: str = "aura-2-thalia-en",
        voice: str = "aura-2-thalia-en",
        timeout_seconds: int = 20,
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.timeout_seconds = timeout_seconds
        self.output_dir = Path("output_audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Serialize writes to the shared latest_response.mp3 path across threads.
        self._write_lock = threading.Lock()
        self._stream_lock = threading.Lock()
        self._active_cache_streams: dict[str, dict] = {}

    @staticmethod
    def _is_whisper_window(now: datetime | None = None) -> bool:
        now = now or datetime.now()
        return now.hour >= 23 or now.hour < 6

    def resolve_audio_profile(
        self,
        *,
        emotion_state: str = "neutral",
        profile_override: str = "",
        now: datetime | None = None,
    ) -> dict:
        now = now or datetime.now()
        emotion = str(emotion_state or "neutral").strip().lower()
        override = str(profile_override or "").strip().lower()

        profile = {
            "name": "default",
            "voice": self.voice,
            "pace_multiplier": 1.0,
            "playback_volume": 1.0,
        }

        if self._is_whisper_window(now) or override == "whisper":
            profile.update(
                {
                    "name": "whisper_night",
                    "voice": "aura-2-asteria-en",
                    "pace_multiplier": 0.9,
                    "playback_volume": 0.58,
                }
            )

        if emotion in ("distressed", "anxious", "dream_negative"):
            profile["pace_multiplier"] *= 0.92
            profile["playback_volume"] *= 0.9
        elif emotion in ("motivated", "excited", "dream_positive"):
            profile["pace_multiplier"] *= 1.04

        profile["playback_volume"] = max(0.2, min(1.0, float(profile["playback_volume"])))
        return profile

    def _resolve_deepgram_model(self, voice_name: str) -> str:
        value = str(voice_name or "").strip().lower()
        if value.startswith("aura-"):
            return value

        legacy_voice_map = {
            "alloy": "aura-2-asteria-en",
            "nova": "aura-2-thalia-en",
            "onyx": "aura-2-orion-en",
        }
        if value in legacy_voice_map:
            return legacy_voice_map[value]

        default_model = str(self.model or "").strip().lower()
        if default_model.startswith("aura-"):
            return default_model
        return "aura-2-thalia-en"

    def _normalize_tts_text(self, text: str) -> str:
        raw = str(text or "")
        normalized = re.sub(r"\s+", " ", raw).strip()
        normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
        return normalized

    def _cache_path_for(self, normalized_text: str, voice: str, pace: float) -> Path:
        cache_key = f"{self.model}|{voice}|{pace:.2f}|{normalized_text}"
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return self.output_dir / f"tts_cache_{digest}.mp3"

    def _make_speech_url(self, model: str) -> str:
        query = {
            "model": model,
            "encoding": "mp3",
        }
        return f"https://api.deepgram.com/v1/speak?{urlencode(query)}"

    def _stream_speech_to_files(
        self,
        *,
        url: str,
        headers: dict,
        payload: dict,
        output_path: Path,
        cache_path: Path,
        cache_key: str,
        min_start_bytes: int = 12288,
        start_wait_seconds: float = 0.28,
    ) -> str | None:
        started = threading.Event()
        done = threading.Event()
        stream_error: dict[str, Exception | None] = {"exc": None}

        def _run_stream():
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        stream=True,
                        timeout=(4, self.timeout_seconds),
                    ) as response:
                        _log.debug("Deepgram request URL: %s", response.url)
                        if not response.ok:
                            try:
                                error_body = response.text[:300].replace("\n", " ").strip()
                            except Exception:
                                error_body = "<unable to read error body>"
                            _log.warning(
                                "Deepgram TTS request failed. status=%s body=%s",
                                response.status_code,
                                error_body,
                            )
                            response.raise_for_status()
                        _log.debug("Deepgram response status: %s", response.status_code)
                        content_type = str(response.headers.get("Content-Type", "") or "").strip()
                        _log.debug("Model response Content-Type: %s", content_type or "unknown")

                        audio_buffer = bytearray()
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                continue
                            if isinstance(chunk, str):
                                raise TypeError(
                                    "TTS stream returned text chunk instead of raw MP3 bytes."
                                )
                            if not isinstance(chunk, (bytes, bytearray)):
                                raise TypeError(
                                    f"TTS stream returned unsupported chunk type: {type(chunk)!r}"
                                )
                            audio_buffer.extend(chunk)
                            if len(audio_buffer) >= min_start_bytes and not started.is_set():
                                started.set()

                        audio_bytes = bytes(audio_buffer)
                        self._write_bytes_safely(output_path, audio_bytes)
                        shutil.copyfile(output_path, cache_path)
                except (
                    requests.exceptions.Timeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.RequestException,
                ) as req_err:
                    short_message = str(req_err).replace("\n", " ").strip()
                    if len(short_message) > 220:
                        short_message = short_message[:217] + "..."
                    _log.warning(
                        "Deepgram TTS failed (%s): %s. Skipping this utterance.",
                        type(req_err).__name__,
                        short_message,
                    )
                    stream_error["exc"] = None
                    return
            except Exception as e:
                stream_error["exc"] = e
                _log.error("Stream synthesis failed before playable MP3 was written: %s", e)
            finally:
                started.set()
                done.set()
                with self._stream_lock:
                    self._active_cache_streams.pop(cache_key, None)

        worker = threading.Thread(target=_run_stream, name="tts-deepgram-stream", daemon=True)
        with self._stream_lock:
            self._active_cache_streams[cache_key] = {
                "done": done,
                "output_path": str(output_path),
            }
        worker.start()
        started.wait(timeout=max(0.05, float(start_wait_seconds)))
        # Wait for full audio generation to complete before returning control to main loop.
        # This prevents microphone from hearing the bed's own TTS voice.
        done.wait(timeout=self.timeout_seconds)
        if stream_error["exc"] is not None:
            return None
        if output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path)
        return None

    def _write_bytes_safely(self, output_path: Path, content: bytes) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            raise ValueError("TTS audio buffer is None; refusing to write empty audio file.")
        if isinstance(content, str):
            raise TypeError("TTS audio buffer is text; expected raw MP3 bytes.")
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError(f"TTS audio buffer has unsupported type: {type(content)!r}")

        audio_bytes = bytes(content)
        buffer_len = len(audio_bytes)
        _log.debug(
            "Audio buffer length before write: %d bytes -> %s", buffer_len, output_path.resolve()
        )
        if buffer_len <= 0:
            raise ValueError("TTS audio buffer is empty (0 bytes); refusing to write MP3.")

        writer = threading.current_thread().name
        _log.debug("Waiting for write lock: {} (thread={})", output_path.resolve(), writer)
        with self._write_lock:
            _log.debug("Write lock acquired: {} (thread={})", output_path.resolve(), writer)
            try:
                # PermissionError retry handled by tenacity (_write_bytes_with_retry).
                # AudioPlaybackController.play_file() must stop/unload before this returns.
                _write_bytes_with_retry(output_path, audio_bytes)
                file_size = output_path.stat().st_size if output_path.exists() else 0
                _log.debug(
                    "Audio file size after write: {} bytes -> {}", file_size, output_path.resolve()
                )
                if file_size <= 0:
                    raise ValueError(
                        f"TTS write produced empty file on disk: {output_path.resolve()}"
                    )
                _log.debug("Finished writing audio file: {}", output_path.resolve())
                return output_path
            finally:
                _log.debug("Write lock released: {} (thread={})", output_path.resolve(), writer)

    def supports_streaming_playback(self) -> bool:
        return _sd is not None and bool(self.api_key)

    def speak_streaming(
        self,
        text: str,
        voice_override: str = "",
        pace_override: float = 1.0,
        emotion_state: str = "neutral",
        profile_override: str = "",
        chunk_size: int = 4096,
    ) -> bool:
        """Speak *text* with chunked PCM playback — first audio at network TTFB.

        Streams linear16 straight from Deepgram Aura into the sound card
        instead of buffering a full MP3 to disk first (~200-400ms to first
        sound vs full-synthesis latency). Blocks until playback finishes so
        fragment ordering in the realtime pipeline is preserved.

        Returns False on any failure so callers can fall back to
        synthesize_to_mp3 + file playback.
        """
        if not self.supports_streaming_playback():
            return False
        normalized = self._normalize_tts_text(text)
        if not normalized:
            return False

        voice = str(voice_override or self.voice or "").strip() or self.voice
        model = self._resolve_deepgram_model(voice)
        query = {
            "model": model,
            "encoding": "linear16",
            "sample_rate": str(_STREAM_PCM_SAMPLE_RATE),
            "container": "none",
        }
        url = f"https://api.deepgram.com/v1/speak?{urlencode(query)}"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        stream = None
        try:
            with requests.post(
                url,
                headers=headers,
                json={"text": normalized},
                stream=True,
                timeout=(4, self.timeout_seconds),
            ) as response:
                if not response.ok:
                    _log.warning("Deepgram streaming TTS failed. status=%s", response.status_code)
                    return False
                stream = _sd.RawOutputStream(
                    samplerate=_STREAM_PCM_SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                )
                stream.start()
                got_audio = False
                leftover = b""
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    data = leftover + chunk
                    # int16 frames must be written in whole samples
                    usable = len(data) - (len(data) % 2)
                    if usable:
                        stream.write(data[:usable])
                        got_audio = True
                    leftover = data[usable:]
                return got_audio
        except Exception as exc:
            _log.warning("Streaming TTS playback failed: %s", exc)
            return False
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def synthesize_to_mp3(
        self,
        text: str,
        filename: str = "latest_response.mp3",
        voice_override: str = "",
        pace_override: float = 1.0,
        emotion_state: str = "neutral",
        profile_override: str = "",
    ) -> str | None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / "latest_response.mp3"
        normalized_text = self._normalize_tts_text(text)

        try:
            pace_value = float(pace_override)
        except Exception:
            pace_value = 1.0
        if not (0.5 <= pace_value <= 2.0):
            pace_value = 1.0

        if not self.api_key:
            msg = "Missing API key; cannot synthesize MP3."
            _log.warning("%s Creating silent fallback audio.", msg)
            fallback_content = (
                b"\xff\xfb\x80\x00" + b"\x00" * 417 + b"\xff\xfb\x80\x00" + b"\x00" * 417
            )
            output_path.write_bytes(fallback_content)
            return str(output_path)

        runtime_profile = self.resolve_audio_profile(
            emotion_state=emotion_state,
            profile_override=profile_override,
        )
        voice_to_use = (voice_override or "").strip() or str(
            runtime_profile.get("voice", self.voice)
        )
        pace_value = max(
            0.5, min(2.0, pace_value * float(runtime_profile.get("pace_multiplier", 1.0)))
        )
        deepgram_model = self._resolve_deepgram_model(voice_to_use)
        cache_path = self._cache_path_for(normalized_text, voice_to_use, pace_value)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                self._write_bytes_safely(output_path, cache_path.read_bytes())
            except Exception as e:
                _log.warning("Cache copy failed for %s: %s", output_path, e)
                return None
            return str(cache_path)

        cache_key = str(cache_path)
        with self._stream_lock:
            inflight = self._active_cache_streams.get(cache_key)
            if inflight and not inflight["done"].is_set():
                return str(inflight["output_path"])

        url = self._make_speech_url(model=deepgram_model)
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": normalized_text,
        }

        try:
            result_path = self._stream_speech_to_files(
                url=url,
                headers=headers,
                payload=payload,
                output_path=output_path,
                cache_path=cache_path,
                cache_key=cache_key,
            )
            if result_path is None:
                _log.warning("No playable TTS audio produced; creating silent fallback audio.")
                fallback_content = (
                    b"\xff\xfb\x80\x00" + b"\x00" * 417 + b"\xff\xfb\x80\x00" + b"\x00" * 417
                )
                output_path.write_bytes(fallback_content)
                return str(output_path)
            return str(result_path)
        except Exception as e:
            _log.error("TTS synthesis failed: %s", e)
            fallback_content = (
                b"\xff\xfb\x80\x00" + b"\x00" * 417 + b"\xff\xfb\x80\x00" + b"\x00" * 417
            )
            output_path.write_bytes(fallback_content)
            return str(output_path)
