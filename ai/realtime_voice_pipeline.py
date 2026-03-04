import queue
import re
import threading
import time
from typing import Callable, Iterable


class RealtimeVoicePipeline:
    """Streams sentence fragments to TTS and audio playback with low latency."""

    def __init__(self, tts_manager, playback_controller):
        self.tts = tts_manager
        self.player = playback_controller

    @staticmethod
    def _split_sentences(buffer: str) -> tuple[list[str], str]:
        text = str(buffer or "")
        if not text:
            return [], ""

        sentence_end_pattern = re.compile(r"(.+?[.!?\n])(?:\s+|$)")
        fragments = []
        consumed = 0
        for match in sentence_end_pattern.finditer(text):
            fragment = match.group(1).strip()
            if fragment:
                fragments.append(fragment)
            consumed = match.end()
        remainder = text[consumed:].strip()
        return fragments, remainder

    @staticmethod
    def _phase_key(text: str) -> str:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return ""
        if any(token in normalized for token in ("sleep", "wind down", "wind-down", "bedtime", "night")):
            return "sleep"
        if any(token in normalized for token in ("morning", "wake", "good morning", "sunrise")):
            return "morning"
        return ""

    def speak_from_text_stream(
        self,
        text_chunks: Iterable[str],
        voice_override: str = "",
        pace_override: float = 1.0,
        emotion_state: str = "neutral",
        profile_override: str = "",
        should_stop: Callable[[], bool] | None = None,
        on_preload_start: Callable[[str], None] | None = None,
        source_is_voice_agent: bool = False,
    ) -> str:
        fragment_queue: queue.Queue[str | None] = queue.Queue()
        playback_started = threading.Event()
        full_parts: list[str] = []
        preload_phase_started = ""

        def _stopped() -> bool:
            return bool(should_stop and should_stop())

        def _playback_worker():
            fragment_index = 0
            while True:
                fragment = fragment_queue.get()
                if fragment is None:
                    break
                if _stopped():
                    break

                filename = f"stream_fragment_{int(time.time() * 1000)}_{fragment_index}.mp3"
                fragment_index += 1
                audio_path = self.tts.synthesize_to_mp3(
                    fragment,
                    filename=filename,
                    voice_override=voice_override,
                    pace_override=pace_override,
                    emotion_state=emotion_state,
                    profile_override=profile_override,
                )
                if _stopped():
                    break
                if not audio_path:
                    continue

                if not playback_started.is_set():
                    if self.player.play_file(audio_path):
                        playback_started.set()
                else:
                    queued = self.player.queue_file(audio_path)
                    if not queued and (not self.player.is_playing()):
                        self.player.play_file(audio_path)

        worker = threading.Thread(target=_playback_worker, name="realtime-tts-playback", daemon=True)
        worker.start()

        buffer = ""
        for chunk in text_chunks:
            if _stopped():
                break
            piece = str(chunk or "")
            if not piece:
                continue
            full_parts.append(piece)
            if (not preload_phase_started) and callable(on_preload_start):
                candidate = self._phase_key("".join(full_parts))
                if candidate:
                    preload_phase_started = candidate
                    try:
                        on_preload_start(candidate)
                    except Exception:
                        pass
            if source_is_voice_agent:
                fragment = piece.strip()
                if fragment:
                    fragment_queue.put(fragment)
            else:
                buffer += piece
                ready, buffer = self._split_sentences(buffer)
                for fragment in ready:
                    fragment_queue.put(fragment)

        if (not _stopped()) and buffer.strip():
            fragment_queue.put(buffer.strip())

        fragment_queue.put(None)
        worker.join(timeout=8.0)
        return "".join(full_parts).strip()

    def speak_from_voice_agent_stream(
        self,
        text_chunks: Iterable[str],
        voice_override: str = "",
        pace_override: float = 1.0,
        emotion_state: str = "neutral",
        profile_override: str = "",
        should_stop: Callable[[], bool] | None = None,
        on_preload_start: Callable[[str], None] | None = None,
    ) -> str:
        """
        Compatibility wrapper: open-question routing now uses GPT text generation,
        so we process chunks with the normal sentence splitter path.
        """
        print("[FLOW] Realtime pipeline voice-agent mode disabled; using generic text stream path.")
        return self.speak_from_text_stream(
            text_chunks,
            voice_override=voice_override,
            pace_override=pace_override,
            emotion_state=emotion_state,
            profile_override=profile_override,
            should_stop=should_stop,
            on_preload_start=on_preload_start,
            source_is_voice_agent=False,
        )
