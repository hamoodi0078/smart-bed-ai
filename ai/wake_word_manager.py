import re
from typing import Optional

from ai.local_wake_word import LocalWakeWordDetector

try:
    import speech_recognition as sr
except Exception:  # pragma: no cover - optional runtime dependency
    sr = None

try:
    from ai.acoustic_wake import AcousticWakeDetector
except Exception:  # pragma: no cover - optional runtime dependency
    AcousticWakeDetector = None


class WakeWordManager:
    def __init__(
        self,
        mode: str = "keyboard",
        wake_word: str = "hey smart bed",
        wake_aliases: Optional[list[str]] = None,
        enforce_local_wake: bool = True,
        voice_timeout_seconds: int = 5,
        voice_phrase_limit_seconds: int = 4,
        barge_in_timeout_seconds: int = 3,
        barge_in_phrase_limit_seconds: int = 3,
        mic_device_index: Optional[int] = None,
        acoustic_detector: Optional["AcousticWakeDetector"] = None,
    ):
        self.mode = (mode or "keyboard").strip().lower()
        self.wake_word = (wake_word or "hey smart bed").strip().lower()
        self.enforce_local_wake = bool(enforce_local_wake)
        self.wake_aliases = []
        self.set_wake_aliases(wake_aliases or [])
        self.voice_timeout_seconds = max(2, int(voice_timeout_seconds))
        self.voice_phrase_limit_seconds = self._normalize_phrase_limit_seconds(
            voice_phrase_limit_seconds
        )
        self.barge_in_timeout_seconds = max(1, int(barge_in_timeout_seconds))
        self.barge_in_phrase_limit_seconds = self._normalize_phrase_limit_seconds(
            barge_in_phrase_limit_seconds
        )
        self._preferred_mic_index = (
            mic_device_index
            if isinstance(mic_device_index, int) and mic_device_index >= 0
            else None
        )

        self._recognizer = sr.Recognizer() if sr is not None else None
        self._active_mic_index = self._preferred_mic_index
        self._local_detector = LocalWakeWordDetector(primary_phrase=self.wake_word)
        self._acoustic_detector = acoustic_detector
        self._voice_available = self._detect_voice_capability()

    def _detect_voice_capability(self) -> bool:
        if not self.is_voice_mode() or self._recognizer is None:
            return False

        candidate_indices: list[Optional[int]] = []
        if self._preferred_mic_index is not None:
            candidate_indices.append(self._preferred_mic_index)
        candidate_indices.append(None)

        names: list[str] = []
        try:
            names = sr.Microphone.list_microphone_names() or []
        except Exception:
            names = []

        for idx, name in enumerate(names):
            lower_name = str(name or "").lower()
            if any(
                token in lower_name for token in ("mic", "microphone", "array", "capture", "input")
            ):
                candidate_indices.append(idx)
        for idx in range(len(names)):
            candidate_indices.append(idx)

        deduped_candidates: list[Optional[int]] = []
        seen = set()
        for idx in candidate_indices:
            if idx in seen:
                continue
            seen.add(idx)
            deduped_candidates.append(idx)

        for idx in deduped_candidates:
            try:
                with sr.Microphone(device_index=idx) as _:
                    self._active_mic_index = idx
                    return True
            except Exception:
                continue

        try:
            with sr.Microphone() as _:
                self._active_mic_index = None
                return True
        except Exception:
            return False

    def is_voice_mode(self) -> bool:
        return self.mode in ("voice", "voice_local")

    def is_voice_available(self) -> bool:
        return self.is_voice_mode() and self._voice_available

    def get_active_mic_index(self) -> Optional[int]:
        return self._active_mic_index

    def get_voice_phrase_limit_seconds(self) -> Optional[int]:
        return self.voice_phrase_limit_seconds

    def set_wake_aliases(self, aliases: list[str]):
        cleaned = []
        for alias in aliases:
            item = (alias or "").strip().lower()
            if not item:
                continue
            if item == self.wake_word:
                continue
            if item in cleaned:
                continue
            cleaned.append(item)
        self.wake_aliases = cleaned[:8]
        self._local_detector = LocalWakeWordDetector(
            primary_phrase=self.wake_word,
            aliases=self.wake_aliases,
        )

    def get_wake_phrases(self) -> list[str]:
        return [self.wake_word] + list(self.wake_aliases)

    def matches_wake_text(self, text: str) -> bool:
        lower = (text or "").lower().strip()
        if lower in {"wake", "hello"}:
            return True
        if self.enforce_local_wake and self._local_detector.detect_in_text(lower):
            return True
        for phrase in self.get_wake_phrases():
            if phrase and phrase in lower:
                return True
        return False

    def requires_local_wake(self) -> bool:
        return bool(self.enforce_local_wake)

    def _clamp_confidence(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _estimate_text_confidence(self, text: str) -> float:
        words = [w for w in str(text or "").strip().split() if w]
        if not words:
            return 0.0

        base = 0.52
        bonus = min(0.3, len(words) * 0.035)
        penalty = 0.0
        if len(words) == 1 and len(words[0]) <= 3:
            penalty = 0.16
        return self._clamp_confidence(base + bonus - penalty)

    def _normalize_phrase_limit_seconds(self, raw_value) -> Optional[int]:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return None
        return max(2, value)

    def has_acoustic_wake(self) -> bool:
        return self._acoustic_detector is not None and bool(
            getattr(self._acoustic_detector, "available", False)
        )

    def acoustic_wake_status(self) -> str:
        if self._acoustic_detector is None:
            return "Acoustic wake not configured."
        return str(self._acoustic_detector.status_line())

    def wait_for_wake_text(self) -> str:
        if not self.is_voice_available():
            return input("You (wake): ").strip().lower()

        # Preferred path: on-device keyword spotting — continuous, ~ms latency,
        # zero cloud calls. Audio only goes to STT after the phrase is heard.
        if self.has_acoustic_wake():
            print(f"Bed: Listening for '{self.wake_word}' (on-device).")
            if self._acoustic_detector.wait_for_wake():
                return self.wake_word
            # Detector stopped or errored — fall through to the legacy loop.

        # Legacy path: record a phrase, transcribe it, fuzzy-match the text.
        print(f"Bed: Voice wake mode active. Say '{self.wake_word}'.")
        while True:
            text = self._listen_once(local_only=self.enforce_local_wake)
            if not text:
                continue
            lower = text.lower().strip()
            print(f"Bed (heard): {text}")
            if lower in ("exit", "quit", "bye"):
                return lower
            if self.matches_wake_text(lower):
                return lower

    def get_user_text(self) -> str:
        if not self.is_voice_available():
            return ""
        print("Bed: Listening for your command...")
        text = self._listen_once()
        if text:
            print(f"Bed (voice): {text}")
        return text.strip()

    def get_user_text_with_confidence(self) -> tuple[str, float]:
        if not self.is_voice_available():
            return "", 0.0
        print("Bed: Listening for your command...")
        text, confidence = self._listen_once_with_confidence()
        if text:
            print(f"Bed (voice): {text}")
        return text.strip(), self._clamp_confidence(confidence)

    def capture_barge_in_text(self) -> str:
        text, _confidence = self.capture_barge_in_text_with_confidence()
        return self._sanitize_barge_in_text(text, _confidence)

    def _sanitize_barge_in_text(self, text: str, confidence: float) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        words = [w for w in cleaned.lower().split() if w]
        if not words:
            return ""

        low_confidence = float(confidence or 0.0) < 0.56
        if len(words) == 1:
            token = re.sub(r"[^a-z0-9\u0600-\u06ff#]+", "", words[0])
            if len(token) <= 2:
                return ""
            if low_confidence and len(token) <= 4:
                return ""

        if low_confidence and len(words) < 2:
            return ""
        return cleaned

    def capture_barge_in_text_with_confidence(self) -> tuple[str, float]:
        if not self.is_voice_available():
            typed = input(
                "You (interrupt now with a new question, or press Enter to continue): "
            ).strip()
            return typed, 1.0 if typed else 0.0

        print("Bed: Say anything now to interrupt, or stay silent to continue...")
        text, confidence = self._listen_once_with_confidence(
            timeout_seconds=self.barge_in_timeout_seconds,
            phrase_limit_seconds=self.barge_in_phrase_limit_seconds,
        )
        return text.strip(), self._clamp_confidence(confidence)

    def _listen_once(
        self,
        timeout_seconds: Optional[int] = None,
        phrase_limit_seconds: Optional[int] = None,
        local_only: bool = False,
    ) -> str:
        text, _ = self._listen_once_with_confidence(
            timeout_seconds=timeout_seconds,
            phrase_limit_seconds=phrase_limit_seconds,
            local_only=local_only,
        )
        return text

    def _listen_once_with_confidence(
        self,
        timeout_seconds: Optional[int] = None,
        phrase_limit_seconds: Optional[int] = None,
        local_only: bool = False,
    ) -> tuple[str, float]:
        if self._recognizer is None:
            return "", 0.0

        timeout_seconds = timeout_seconds or self.voice_timeout_seconds
        phrase_limit_seconds = (
            self.voice_phrase_limit_seconds
            if phrase_limit_seconds is None
            else self._normalize_phrase_limit_seconds(phrase_limit_seconds)
        )

        try:
            with sr.Microphone(device_index=self._active_mic_index) as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self._recognizer.energy_threshold = 300
                self._recognizer.dynamic_energy_threshold = True
                audio = self._recognizer.listen(
                    source,
                    timeout=timeout_seconds,
                    phrase_time_limit=phrase_limit_seconds,
                )
            result = None
            # Skip Sphinx - it requires full PocketSphinx install which often fails silently.
            # Use Google Speech Recognition directly for reliability.

            try:
                result = self._recognizer.recognize_google(audio, show_all=True)
            except Exception:
                result = None

            if isinstance(result, dict):
                alternatives = result.get("alternative") or []
                if alternatives:
                    top = alternatives[0]
                    transcript = str(top.get("transcript", "") or "").strip()
                    confidence = top.get("confidence")
                    if isinstance(confidence, (int, float)):
                        return transcript, self._clamp_confidence(float(confidence))
                    return transcript, self._estimate_text_confidence(transcript)

            if isinstance(result, str):
                text = result.strip()
            else:
                text = ""

            if text:
                return text, self._estimate_text_confidence(text)
            return "", 0.0
        except Exception:
            return "", 0.0
