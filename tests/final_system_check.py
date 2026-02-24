import tempfile
import unittest
from pathlib import Path

from ai.long_term_memory import LongTermMemoryStore
from ai.realtime_voice_pipeline import RealtimeVoicePipeline


class _FakeSTTManager:
    def transcribe_microphone_with_interim(self):
        return "I had a stressful day and want help sleeping", 0.93


class _FakeConversationEngine:
    def generate_response_stream(self, user_text: str):
        _ = user_text
        chunks = [
            "You did well getting through today. ",
            "Let us start a sleep wind down with slow breathing.",
        ]
        for chunk in chunks:
            yield chunk


class _FakeTTSManager:
    def __init__(self):
        self.calls = []

    def synthesize_to_mp3(
        self,
        text,
        filename="",
        voice_override="",
        pace_override=1.0,
        emotion_state="neutral",
        profile_override="",
    ):
        self.calls.append(
            {
                "text": str(text),
                "filename": filename,
                "voice": voice_override,
                "pace": pace_override,
                "emotion": emotion_state,
                "profile": profile_override,
            }
        )
        return f"fake/{filename or 'audio'}.mp3"


class _FakePlaybackController:
    def __init__(self):
        self.played = []
        self.queued = []
        self._playing = False

    def play_file(self, path):
        self.played.append(path)
        self._playing = True
        return True

    def queue_file(self, path):
        self.queued.append(path)
        return True

    def is_playing(self):
        return self._playing


class TestFinalSystemCheck(unittest.TestCase):
    def test_full_conversation_flow_stt_llm_parallel_tts_memory_save(self):
        stt = _FakeSTTManager()
        chat = _FakeConversationEngine()
        tts = _FakeTTSManager()
        player = _FakePlaybackController()
        pipeline = RealtimeVoicePipeline(tts, player)

        with tempfile.TemporaryDirectory() as td:
            memory_path = Path(td) / "long_term_memory.json"
            memory = LongTermMemoryStore(path=str(memory_path))

            user_text, confidence = stt.transcribe_microphone_with_interim()
            self.assertGreaterEqual(confidence, 0.9)

            preload_phases = []
            assistant_text = pipeline.speak_from_text_stream(
                chat.generate_response_stream(user_text),
                emotion_state="low_energy",
                on_preload_start=lambda phase: preload_phases.append(phase),
            )

            memory.record_turn(
                user_text=user_text,
                assistant_text=assistant_text,
                emotion_state="low_energy",
                personality="therapist",
            )

            self.assertIn("stressful day", user_text)
            self.assertIn("wind down", assistant_text.lower())
            self.assertTrue(tts.calls)
            self.assertTrue(player.played)
            self.assertEqual(preload_phases, ["sleep"])

            context_line = memory.latest_memory_context()
            self.assertIn("Last memory turn", context_line)
            self.assertIn("low_energy", context_line)


if __name__ == "__main__":
    unittest.main()
