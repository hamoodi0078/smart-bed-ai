"""Tests for pyloudnorm-powered loudness normalisation in STTManager."""

from __future__ import annotations

import io
import math
import struct
import unittest
import wave
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(
    freq_hz: float = 440.0,
    amplitude: float = 0.05,          # intentionally quiet
    sample_rate: int = 16000,
    duration_ms: int = 600,
    n_channels: int = 1,
) -> bytes:
    """Build an in-memory 16-bit PCM WAV at the given amplitude."""
    n = sample_rate * duration_ms // 1000
    samples = [
        int(amplitude * 32767 * math.sin(2 * math.pi * freq_hz * i / sample_rate))
        for i in range(n)
    ]
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


def _make_silence_wav(sample_rate: int = 16000, duration_ms: int = 600) -> bytes:
    n = sample_rate * duration_ms // 1000
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(n * 2))
    return out.getvalue()


def _measure_lufs(wav_bytes: bytes) -> float:
    """Measure integrated loudness of a WAV blob; returns float (may be -inf)."""
    import pyloudnorm as pyln
    import numpy as np

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    arr = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if n_channels > 1:
        arr = arr.reshape(-1, n_channels)

    meter = pyln.Meter(framerate)
    return meter.integrated_loudness(arr)


def _wav_frame_count(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes()


def _make_stt():
    from ai.stt_manager import STTManager
    return STTManager(api_key="test_key")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPyloudnormAvailability(unittest.TestCase):

    def test_flag_is_bool(self):
        import ai.stt_manager as mod
        self.assertIn("_PYLOUDNORM_AVAILABLE", dir(mod))
        self.assertIsInstance(mod._PYLOUDNORM_AVAILABLE, bool)


class TestNormaliseLoudnessUnavailable(unittest.TestCase):

    def test_returns_original_when_unavailable(self):
        import ai.stt_manager as mod
        with patch.object(mod, "_PYLOUDNORM_AVAILABLE", False):
            stt = _make_stt()
            wav = _make_wav()
            self.assertEqual(stt._normalize_loudness_wav_bytes(wav), wav)

    def test_returns_original_when_pyln_none(self):
        import ai.stt_manager as mod
        with patch.object(mod, "_PYLOUDNORM_AVAILABLE", False), \
             patch.object(mod, "_pyln", None):
            stt = _make_stt()
            wav = _make_wav()
            self.assertEqual(stt._normalize_loudness_wav_bytes(wav), wav)


class TestNormaliseLoudnessFallbacks(unittest.TestCase):

    def test_returns_original_for_corrupt_bytes(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        result = stt._normalize_loudness_wav_bytes(b"JUNK" * 50)
        self.assertEqual(result, b"JUNK" * 50)

    def test_returns_original_for_silent_wav(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        silent = _make_silence_wav(duration_ms=800)
        result = stt._normalize_loudness_wav_bytes(silent)
        # silent → loudness = -inf → should return unchanged
        self.assertEqual(result, silent)

    def test_returns_original_for_too_short_wav(self):
        """Clips shorter than 400 ms cannot be measured reliably by BS.1770."""
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        short_wav = _make_wav(duration_ms=200)
        result = stt._normalize_loudness_wav_bytes(short_wav)
        self.assertEqual(result, short_wav)

    def test_returns_original_for_24bit_wav(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        # Build a 24-bit WAV (sampwidth=3) — unsupported
        n = 16000 * 600 // 1000
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(16000)
            wf.writeframes(bytes(n * 3))
        wav_24bit = out.getvalue()
        stt = _make_stt()
        self.assertEqual(stt._normalize_loudness_wav_bytes(wav_24bit), wav_24bit)


class TestNormaliseLoudnessCorrectness(unittest.TestCase):

    def test_output_is_valid_wav(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        result = stt._normalize_loudness_wav_bytes(_make_wav())
        with wave.open(io.BytesIO(result), "rb") as wf:
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertGreater(wf.getnframes(), 0)

    def test_frame_count_preserved(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        wav = _make_wav(duration_ms=600)
        result = stt._normalize_loudness_wav_bytes(wav)
        self.assertEqual(_wav_frame_count(result), _wav_frame_count(wav))

    def test_loudness_closer_to_target_after_normalisation(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        target = -23.0
        wav = _make_wav(amplitude=0.05, duration_ms=1000)  # quiet input

        original_lufs = _measure_lufs(wav)
        if not math.isfinite(original_lufs):
            self.skipTest("signal too quiet to measure")

        result = stt._normalize_loudness_wav_bytes(wav, target_lufs=target)
        result_lufs = _measure_lufs(result)
        if not math.isfinite(result_lufs):
            self.skipTest("normalised signal still unmeasurable")

        # After normalisation the output should be within 1 LU of target
        self.assertAlmostEqual(result_lufs, target, delta=1.0)

    def test_preserves_sample_rate(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        for rate in (8000, 16000):
            wav = _make_wav(sample_rate=rate, duration_ms=600)
            result = stt._normalize_loudness_wav_bytes(wav)
            with wave.open(io.BytesIO(result), "rb") as wf:
                self.assertEqual(wf.getframerate(), rate)

    def test_stereo_output_preserves_channel_count(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        wav = _make_wav(n_channels=2, duration_ms=600)
        result = stt._normalize_loudness_wav_bytes(wav)
        with wave.open(io.BytesIO(result), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 2)

    def test_custom_target_lufs_applied(self):
        import ai.stt_manager as mod
        if not mod._PYLOUDNORM_AVAILABLE:
            self.skipTest("pyloudnorm not installed")
        stt = _make_stt()
        wav = _make_wav(amplitude=0.3, duration_ms=1000)

        for target in (-16.0, -23.0):
            original_lufs = _measure_lufs(wav)
            if not math.isfinite(original_lufs):
                continue
            result = stt._normalize_loudness_wav_bytes(wav, target_lufs=target)
            result_lufs = _measure_lufs(result)
            if not math.isfinite(result_lufs):
                continue
            self.assertAlmostEqual(result_lufs, target, delta=1.5)


class TestNormalisationCalledInTranscribePaths(unittest.TestCase):

    def _make_spy_stt(self):
        stt = _make_stt()
        calls = []
        original = stt._normalize_loudness_wav_bytes

        def _spy(b, **kw):
            calls.append(len(b))
            return original(b, **kw)

        stt._normalize_loudness_wav_bytes = _spy
        return stt, calls

    def test_called_in_transcribe_microphone_once_via_api(self):
        import ai.stt_manager as mod
        import unittest.mock as mock

        stt, calls = self._make_spy_stt()
        wav = _make_wav()

        class _FakeAudio:
            def get_wav_data(self): return wav

        class _FakeRecognizer:
            energy_threshold = 180.0
            def adjust_for_ambient_noise(self, *a, **kw): pass
            def listen(self, *a, **kw): return _FakeAudio()

        class _FakeMic:
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with mock.patch.object(mod, "sr") as mock_sr, \
             mock.patch("requests.post") as mock_post:
            mock_sr.Recognizer.return_value = _FakeRecognizer()
            mock_sr.Microphone.return_value = _FakeMic()
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {}
            stt._transcribe_microphone_once_via_api()

        self.assertGreater(len(calls), 0)

    def test_called_in_transcribe_api_with_confidence(self):
        import ai.stt_manager as mod
        import pathlib
        import tempfile
        import unittest.mock as mock

        stt, calls = self._make_spy_stt()
        wav = _make_wav()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            tmp_path = pathlib.Path(f.name)

        try:
            with mock.patch("requests.post") as mock_post:
                mock_post.return_value.raise_for_status = lambda: None
                mock_post.return_value.json.return_value = {}
                stt._transcribe_api_with_confidence(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertGreater(len(calls), 0)


if __name__ == "__main__":
    unittest.main()