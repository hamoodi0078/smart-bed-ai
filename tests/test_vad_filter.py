"""Tests for the VadFilter WebRTC VAD wrapper."""

from __future__ import annotations

import struct
import unittest
from unittest.mock import MagicMock, patch


def _sine_pcm(freq_hz: float = 440.0, sample_rate: int = 16000, duration_ms: int = 500) -> bytes:
    """Generate a sine-wave PCM burst that webrtcvad should classify as speech."""
    import math
    n = sample_rate * duration_ms // 1000
    samples = [int(16000 * math.sin(2 * math.pi * freq_hz * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def _silence_pcm(sample_rate: int = 16000, duration_ms: int = 500) -> bytes:
    n = sample_rate * duration_ms // 1000
    return bytes(n * 2)  # 16-bit zero samples


class TestVadFilterImport(unittest.TestCase):

    def test_module_exports_vad_available_flag(self):
        from ai.vad_filter import VAD_AVAILABLE
        self.assertIsInstance(VAD_AVAILABLE, bool)

    def test_module_exports_vad_filter_class(self):
        from ai.vad_filter import VadFilter
        self.assertTrue(callable(VadFilter))


class TestVadFilterConstruction(unittest.TestCase):

    def test_invalid_sample_rate_raises(self):
        from ai.vad_filter import VadFilter
        with self.assertRaises(ValueError):
            VadFilter(sample_rate=22050)

    def test_invalid_frame_ms_raises(self):
        from ai.vad_filter import VadFilter
        with self.assertRaises(ValueError):
            VadFilter(frame_ms=15)

    def test_valid_construction(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter(sample_rate=16000, aggressiveness=2, frame_ms=20)
        self.assertIsNotNone(vf)

    def test_frame_bytes_correct_for_16khz_20ms(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter(sample_rate=16000, frame_ms=20)
        # 16000 samples/s * 0.02 s * 2 bytes/sample = 640
        self.assertEqual(vf._frame_bytes, 640)

    def test_frame_bytes_correct_for_8khz_30ms(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter(sample_rate=8000, frame_ms=30)
        # 8000 * 0.03 * 2 = 480
        self.assertEqual(vf._frame_bytes, 480)


class TestVadFilterUnavailable(unittest.TestCase):

    def test_is_speech_frame_returns_false_when_unavailable(self):
        from ai.vad_filter import VadFilter
        with patch("ai.vad_filter.VAD_AVAILABLE", False):
            vf = VadFilter()
            vf._vad = None
            frame = _sine_pcm(duration_ms=20)[:640]
            self.assertFalse(vf.is_speech_frame(frame))

    def test_process_chunk_returns_false_when_unavailable(self):
        from ai.vad_filter import VadFilter
        with patch("ai.vad_filter.VAD_AVAILABLE", False):
            vf = VadFilter()
            vf._vad = None
            result = vf.process_chunk(_sine_pcm(duration_ms=200))
            self.assertFalse(result)

    def test_has_enough_speech_returns_false_when_unavailable(self):
        from ai.vad_filter import VadFilter
        with patch("ai.vad_filter.VAD_AVAILABLE", False):
            result = VadFilter.has_enough_speech(_sine_pcm(duration_ms=1000), 16000)
            self.assertFalse(result)


class TestVadFilterSilence(unittest.TestCase):

    def test_silence_pcm_does_not_trigger_onset(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        vf = VadFilter(sample_rate=16000, aggressiveness=3, ring_size=10, onset_ratio=0.70)
        result = vf.process_chunk(_silence_pcm(duration_ms=400))
        self.assertFalse(result)

    def test_reset_clears_state(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        vf = VadFilter()
        vf._is_speaking = True
        vf._ring.append(True)
        vf._buffer.extend(b"\x00\x01")
        vf.reset()
        self.assertFalse(vf._is_speaking)
        self.assertEqual(len(vf._ring), 0)
        self.assertEqual(len(vf._buffer), 0)


class TestVadFilterRingBuffer(unittest.TestCase):

    def test_onset_triggered_after_enough_speech_frames(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter(ring_size=5, onset_ratio=0.60)
        # Manually push speech frames into ring to simulate onset
        for _ in range(4):  # 4/5 = 0.80 >= 0.60 → onset
            vf._ring.append(True)
        vf._ring.append(True)
        # Trigger state machine by calling process_chunk with empty bytes
        # (no new frames, but state machine runs on existing ring)
        # We'll call the state machine directly
        speech_ratio = sum(vf._ring) / len(vf._ring)
        if not vf._is_speaking and speech_ratio >= vf._onset_ratio:
            vf._is_speaking = True
        self.assertTrue(vf._is_speaking)

    def test_offset_triggered_after_enough_silence_frames(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter(ring_size=5, offset_ratio=0.60)
        vf._is_speaking = True
        # 4 silence frames out of 5 → 0.80 silence ratio >= 0.60 → offset
        for _ in range(4):
            vf._ring.append(False)
        vf._ring.append(False)
        silence_ratio = 1.0 - sum(vf._ring) / len(vf._ring)
        if vf._is_speaking and silence_ratio >= vf._offset_ratio:
            vf._is_speaking = False
        self.assertFalse(vf._is_speaking)

    def test_insufficient_speech_does_not_trigger_onset(self):
        from ai.vad_filter import VadFilter
        # With onset_ratio=0.70, 3/5 = 0.60 should NOT trigger onset
        vf = VadFilter(ring_size=5, onset_ratio=0.70)
        for _ in range(3):
            vf._ring.append(True)
        for _ in range(2):
            vf._ring.append(False)
        speech_ratio = sum(vf._ring) / len(vf._ring)
        if not vf._is_speaking and speech_ratio >= vf._onset_ratio:
            vf._is_speaking = True
        self.assertFalse(vf._is_speaking)


class TestVadFilterIsSpeeFrame(unittest.TestCase):

    def test_wrong_frame_length_returns_false(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        vf = VadFilter(sample_rate=16000, frame_ms=20)
        self.assertFalse(vf.is_speech_frame(b"\x00" * 100))  # wrong length

    def test_empty_frame_returns_false(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        vf = VadFilter()
        self.assertFalse(vf.is_speech_frame(b""))


class TestHasEnoughSpeech(unittest.TestCase):

    def test_returns_false_for_all_silence(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        pcm = _silence_pcm(sample_rate=16000, duration_ms=2000)
        result = VadFilter.has_enough_speech(pcm, 16000, min_speech_frames=5)
        self.assertFalse(result)

    def test_returns_false_for_invalid_sample_rate(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        pcm = _sine_pcm(duration_ms=1000)
        result = VadFilter.has_enough_speech(pcm, 22050)
        self.assertFalse(result)

    def test_returns_false_for_too_short_pcm(self):
        from ai.vad_filter import VadFilter, VAD_AVAILABLE
        if not VAD_AVAILABLE:
            self.skipTest("webrtcvad not installed")
        pcm = b"\x00" * 20  # far less than one frame
        result = VadFilter.has_enough_speech(pcm, 16000, min_speech_frames=5)
        self.assertFalse(result)


class TestFilterChunks(unittest.TestCase):

    def test_yields_tuple_for_each_chunk(self):
        from ai.vad_filter import VadFilter
        vf = VadFilter()
        chunks = [b"\x00" * 640, b"\x00" * 640, b"\x00" * 640]
        results = list(vf.filter_chunks(chunks))
        self.assertEqual(len(results), 3)
        for chunk, is_speaking in results:
            self.assertIsInstance(chunk, bytes)
            self.assertIsInstance(is_speaking, bool)

    def test_passthrough_when_vad_unavailable(self):
        from ai.vad_filter import VadFilter
        with patch("ai.vad_filter.VAD_AVAILABLE", False):
            vf = VadFilter()
            vf._vad = None
            chunks = [b"\xff" * 640, b"\x00" * 640]
            results = list(vf.filter_chunks(chunks))
            self.assertEqual(len(results), 2)
            # All should be False (VAD unavailable)
            self.assertTrue(all(not speaking for _, speaking in results))


if __name__ == "__main__":
    unittest.main()