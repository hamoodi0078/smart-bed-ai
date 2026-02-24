import hashlib
import re
import shutil
import threading
from urllib.parse import urlencode
from pathlib import Path
from time import time

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
        self._stream_lock = threading.Lock()
        self._active_cache_streams: dict[str, dict] = {}

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

    def _make_speech_url(self, model: str, pace: float) -> str:
        query = {
            "model": model,
            "encoding": "mp3",
            "container": "mp3",
            "speed": f"{pace:.2f}",
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
    ) -> str:
        started = threading.Event()
        done = threading.Event()

        def _run_stream():
            wrote_any = False
            try:
                with requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=(4, self.timeout_seconds),
                ) as response:
                    response.raise_for_status()
                    total = 0
                    with output_path.open("wb") as target:
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                continue
                            target.write(chunk)
                            target.flush()
                            total += len(chunk)
                            wrote_any = True
                            if total >= min_start_bytes and not started.is_set():
                                started.set()
                    if wrote_any:
                        shutil.copyfile(output_path, cache_path)
            except Exception:
                if not wrote_any:
                    self._write_bytes_safely(output_path, b"")
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
        return str(output_path)

    def _write_bytes_safely(self, output_path: Path, content: bytes) -> Path:
        try:
            output_path.write_bytes(content)
            return output_path
        except Exception:
            # Windows can keep an MP3 handle locked briefly after playback stop.
            fallback_path = self.output_dir / f"latest_response_{int(time() * 1000)}.mp3"
            try:
                fallback_path.write_bytes(content)
                return fallback_path
            except Exception:
                # Last-resort path to avoid crashing the runtime loop.
                return output_path

    def synthesize_to_mp3(
        self,
        text: str,
        filename: str = "latest_response.mp3",
        voice_override: str = "",
        pace_override: float = 1.0,
    ) -> str:
        output_path = self.output_dir / filename
        normalized_text = self._normalize_tts_text(text)

        try:
            pace_value = float(pace_override)
        except Exception:
            pace_value = 1.0
        if not (0.5 <= pace_value <= 2.0):
            pace_value = 1.0

        if not self.api_key:
            written_path = self._write_bytes_safely(output_path, b"")
            return str(written_path)

        voice_to_use = (voice_override or "").strip() or self.voice
        deepgram_model = self._resolve_deepgram_model(voice_to_use)
        cache_path = self._cache_path_for(normalized_text, voice_to_use, pace_value)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return str(cache_path)

        cache_key = str(cache_path)
        with self._stream_lock:
            inflight = self._active_cache_streams.get(cache_key)
            if inflight and not inflight["done"].is_set():
                return str(inflight["output_path"])

        url = self._make_speech_url(model=deepgram_model, pace=pace_value)
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": normalized_text,
        }

        return self._stream_speech_to_files(
            url=url,
            headers=headers,
            payload=payload,
            output_path=output_path,
            cache_path=cache_path,
            cache_key=cache_key,
        )
