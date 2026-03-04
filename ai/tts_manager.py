import hashlib
import re
import shutil
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from pathlib import Path

import requests


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
                        print(f"[TTS] Deepgram request URL: {response.url}")
                        if not response.ok:
                            try:
                                error_body = response.text[:300].replace("\n", " ").strip()
                            except Exception:
                                error_body = "<unable to read error body>"
                            print(
                                f"[TTS] Deepgram TTS request failed. "
                                f"status={response.status_code} body={error_body}"
                            )
                            response.raise_for_status()
                        print(f"[TTS] Deepgram response status: {response.status_code}")
                        content_type = str(response.headers.get("Content-Type", "") or "").strip()
                        print(f"[TTS] Model response Content-Type: {content_type or 'unknown'}")

                        audio_buffer = bytearray()
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                continue
                            if isinstance(chunk, str):
                                raise TypeError("TTS stream returned text chunk instead of raw MP3 bytes.")
                            if not isinstance(chunk, (bytes, bytearray)):
                                raise TypeError(f"TTS stream returned unsupported chunk type: {type(chunk)!r}")
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
                    print(
                        f"[TTS][WARN] Deepgram TTS failed ({type(req_err).__name__}): "
                        f"{short_message}. Skipping this utterance."
                    )
                    stream_error["exc"] = None
                    return
            except Exception as e:
                stream_error["exc"] = e
                print(f"[TTS] Stream synthesis failed before playable MP3 was written: {e}")
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
        print(f"[TTS] Audio buffer length before write: {buffer_len} bytes -> {output_path.resolve()}")
        if buffer_len <= 0:
            raise ValueError("TTS audio buffer is empty (0 bytes); refusing to write MP3.")

        writer = threading.current_thread().name
        print(f"[TTS] Waiting for write lock: {output_path.resolve()} (thread={writer})")
        with self._write_lock:
            print(f"[TTS] Write lock acquired: {output_path.resolve()} (thread={writer})")
            try:
                max_attempts = 4
                # We rely on AudioPlaybackController.play_file() stop/unload to release file handles promptly.
                for attempt in range(1, max_attempts + 1):
                    try:
                        output_path.write_bytes(audio_bytes)
                        file_size = output_path.stat().st_size if output_path.exists() else 0
                        print(f"[TTS] Audio file size after write: {file_size} bytes -> {output_path.resolve()}")
                        if file_size <= 0:
                            raise ValueError(f"TTS write produced empty file on disk: {output_path.resolve()}")
                        print(f"[TTS] Finished writing audio file: {output_path.resolve()}")
                        return output_path
                    except PermissionError as e:
                        if attempt >= max_attempts:
                            print(
                                f"[TTS][WARN] Write contention persisted after {attempt} attempts; "
                                f"skipping overwrite for {output_path.resolve()}: {e}"
                            )
                            return output_path
                        wait_seconds = min(0.45, 0.15 * attempt)
                        print(
                            f"[TTS] Write contention (PermissionError). "
                            f"retry={attempt}/{max_attempts} wait={wait_seconds:.2f}s "
                            f"path={output_path.resolve()}"
                        )
                        time.sleep(wait_seconds)
            finally:
                print(f"[TTS] Write lock released: {output_path.resolve()} (thread={writer})")

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
            msg = "[TTS] Missing API key; cannot synthesize MP3."
            print(f"[TTS][WARN] {msg} Creating silent fallback audio.")
            # Create a minimal valid MP3 file as fallback with actual audio data
            # This creates a very short silent MP3 file
            fallback_content = (
                b'\xFF\xFB\x80\x00'  # MP3 frame header (MPEG-1, Layer III, 320kbps, 44.1kHz, stereo)
                + b'\x00' * 417        # Audio data (creates about 0.026 seconds of silence)
                + b'\xFF\xFB\x80\x00'  # Another MP3 frame header
                + b'\x00' * 417        # More audio data
            )
            output_path.write_bytes(fallback_content)
            return str(output_path)

        runtime_profile = self.resolve_audio_profile(
            emotion_state=emotion_state,
            profile_override=profile_override,
        )
        voice_to_use = (voice_override or "").strip() or str(runtime_profile.get("voice", self.voice))
        pace_value = max(0.5, min(2.0, pace_value * float(runtime_profile.get("pace_multiplier", 1.0))))
        deepgram_model = self._resolve_deepgram_model(voice_to_use)
        cache_path = self._cache_path_for(normalized_text, voice_to_use, pace_value)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                self._write_bytes_safely(output_path, cache_path.read_bytes())
            except Exception as e:
                print(f"[TTS] Cache copy failed for {output_path}: {e}")
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
                print("[TTS][WARN] No playable TTS audio produced; creating silent fallback audio.")
                # Create a minimal valid MP3 file as fallback with actual audio data
                # This creates a very short silent MP3 file
                fallback_content = (
                    b'\xFF\xFB\x80\x00'  # MP3 frame header (MPEG-1, Layer III, 320kbps, 44.1kHz, stereo)
                    + b'\x00' * 417        # Audio data (creates about 0.026 seconds of silence)
                    + b'\xFF\xFB\x80\x00'  # Another MP3 frame header
                    + b'\x00' * 417        # More audio data
                )
                output_path.write_bytes(fallback_content)
                return str(output_path)
            return str(result_path)
        except Exception as e:
            print(f"TTS synthesis failed: {str(e)}")
            # Create a minimal valid MP3 file as fallback with actual audio data
            # This creates a very short silent MP3 file
            fallback_content = (
                b'\xFF\xFB\x80\x00'  # MP3 frame header (MPEG-1, Layer III, 320kbps, 44.1kHz, stereo)
                + b'\x00' * 417        # Audio data (creates about 0.026 seconds of silence)
                + b'\xFF\xFB\x80\x00'  # Another MP3 frame header
                + b'\x00' * 417        # More audio
            )
            output_path.write_bytes(fallback_content)
            return str(output_path)
