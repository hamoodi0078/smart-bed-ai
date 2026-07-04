"""Tests for noisereduce-powered WAV denoising in STTManager."""

from __future__ import annotations

import io
import math
import struct
import unittest
import wave
from unittest.mock import patch


def _make_wav(
    freq_hz: float = 440.0,
    sample_rate: int = 16000,
    duration_ms: int = 300,
    noise_amplitude: float = 0.05,
    n_channels: int = 1,
) -> bytes:
    """Build an in-memory WAV with a sine wave plus low-level noise."""
    import random

    rng = random.Random(42)
    n = sample_rate * duration_ms // 1000
    samples: list[int] = []
    for i in range(n):
        signal = math.sin(2 * math.pi * freq_hz * i / sample_rate)
        noise = rng.gauss(0, noise_amplitude)
        raw = int((signal + noise) * 16000)
        samples.append(max(-32768, min(32767, raw)))

    frame_data = struct.pack(f"<{n}h", *samples)
    if n_channels == 2:
        stereo = bytearray()
        for s in struct.unpack(f"<{n}h", frame_data):
            stereo += struct.pack("<hh", s, s)
        frame_data = bytes(stereo)

    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frame_data)
    return out.getvalue()


def _make_stt() -> object:
    from ai.stt_manager import STTManager

    return STTManager(api_key="test_key")


class TestNoiseReduceAvailability(unittest.TestCase):
    def test_module_flag_is_bool(self):
        import ai.stt_manager as mod

        self.assertIn("_NOISEREDUCE_AVAILABLE", dir(mod))
        self.assertIsInstance(mod._NOISEREDUCE_AVAILABLE, bool)


class TestDenoiseWavBytesUnavailable(unittest.TestCase):
    def test_returns_original_bytes_when_unavailable(self):
        import ai.stt_manager as mod

        with patch.object(mod, "_NOISEREDUCE_AVAILABLE", False):
            stt = _make_stt()
            wav = _make_wav()
            result = stt._denoise_wav_bytes(wav)
            self.assertEqual(result, wav)

    def test_returns_original_bytes_when_nr_none(self):
        import ai.stt_manager as mod

        with patch.object(mod, "_NOISEREDUCE_AVAILABLE", False), patch.object(mod, "_nr", None):
            stt = _make_stt()
            wav = _make_wav()
            result = stt._denoise_wav_bytes(wav)
            self.assertEqual(result, wav)


class TestDenoiseWavBytesAvailable(unittest.TestCase):
    def test_returns_bytes(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        result = stt._denoise_wav_bytes(_make_wav())
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    def test_output_is_valid_wav(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        denoised = stt._denoise_wav_bytes(_make_wav())
        with wave.open(io.BytesIO(denoised), "rb") as wf:
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertGreater(wf.getnframes(), 0)

    def test_preserves_sample_rate(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        for rate in (8000, 16000):
            wav = _make_wav(sample_rate=rate)
            denoised = stt._denoise_wav_bytes(wav)
            with wave.open(io.BytesIO(denoised), "rb") as wf:
                self.assertEqual(wf.getframerate(), rate)

    def test_preserves_channel_count_stereo(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        wav = _make_wav(n_channels=2)
        denoised = stt._denoise_wav_bytes(wav)
        with wave.open(io.BytesIO(denoised), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 2)

    def test_output_length_similar_to_input(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        wav = _make_wav(duration_ms=500)
        denoised = stt._denoise_wav_bytes(wav)
        # Denoised WAV should be within 20% of original size (same frames, same header)
        self.assertAlmostEqual(len(denoised), len(wav), delta=len(wav) * 0.2)


class TestDenoiseWavBytesFallback(unittest.TestCase):
    def test_returns_original_on_corrupt_bytes(self):
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        stt = _make_stt()
        garbage = b"NOTAWAV\x00" * 64
        result = stt._denoise_wav_bytes(garbage)
        self.assertEqual(result, garbage)

    def test_returns_original_on_24bit_wav(self):
        """24-bit PCM (sampwidth=3) is unsupported — should fall back unchanged."""
        import ai.stt_manager as mod

        if not mod._NOISEREDUCE_AVAILABLE:
            self.skipTest("noisereduce not installed")
        # Build a minimal 24-bit WAV header manually
        n_frames = 160
        frame_data = bytes(n_frames * 3)  # 3 bytes per sample, all zeros
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(16000)
            wf.writeframes(frame_data)
        wav_24bit = out.getvalue()
        stt = _make_stt()
        result = stt._denoise_wav_bytes(wav_24bit)
        self.assertEqual(result, wav_24bit)


class TestDenoiseIntegratedInTranscribePaths(unittest.TestCase):
    """Verify _denoise_wav_bytes is called in the two API paths."""

    def test_denoise_called_in_microphone_once_via_api(self):
        import ai.stt_manager as mod

        stt = _make_stt()
        calls = []

        original_denoise = stt._denoise_wav_bytes

        def _spy(b):
            calls.append(len(b))
            return original_denoise(b)

        stt._denoise_wav_bytes = _spy

        wav = _make_wav()

        class _FakeAudio:
            def get_wav_data(self):
                return wav

        class _FakeRecognizer:
            energy_threshold = 180.0

            def adjust_for_ambient_noise(self, *a, **kw):
                pass

            def listen(self, *a, **kw):
                return _FakeAudio()

        class _FakeMic:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        import unittest.mock as mock

        with mock.patch.object(mod, "sr") as mock_sr, mock.patch("requests.post") as mock_post:
            mock_sr.Recognizer.return_value = _FakeRecognizer()
            mock_sr.Microphone.return_value = _FakeMic()
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {}
            stt._transcribe_microphone_once_via_api()

        self.assertTrue(len(calls) >= 1, "Expected _denoise_wav_bytes to be called")

    def test_denoise_called_in_transcribe_api_with_confidence(self):
        import ai.stt_manager as mod
        import tempfile
        import pathlib

        stt = _make_stt()
        calls = []

        original_denoise = stt._denoise_wav_bytes

        def _spy(b):
            calls.append(len(b))
            return original_denoise(b)

        stt._denoise_wav_bytes = _spy

        wav = _make_wav()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            tmp_path = pathlib.Path(f.name)

        try:
            import unittest.mock as mock

            with mock.patch("requests.post") as mock_post:
                mock_post.return_value.raise_for_status = lambda: None
                mock_post.return_value.json.return_value = {}
                stt._transcribe_api_with_confidence(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertTrue(len(calls) >= 1, "Expected _denoise_wav_bytes to be called")


if __name__ == "__main__":
    unittest.main()
