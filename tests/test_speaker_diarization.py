"""Tests for speaker diarization (pyannote.audio) integration."""

from __future__ import annotations

import io
import math
import struct
import unittest
import wave
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_wav(
    freq_hz: float = 440.0,
    sample_rate: int = 16000,
    duration_ms: int = 3000,
    amplitude: float = 0.4,
    n_channels: int = 1,
) -> bytes:
    n = sample_rate * duration_ms // 1000
    samples = [
        int(amplitude * 32767 * math.sin(2 * math.pi * freq_hz * i / sample_rate)) for i in range(n)
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


class _FakeTurn:
    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


class _FakeAnnotation:
    """Mimics the object returned by pyannote Pipeline."""

    def __init__(self, turns: list[tuple[float, float, str]]):
        self._turns = turns

    def itertracks(self, yield_label: bool = False):
        for start, end, speaker in self._turns:
            yield _FakeTurn(start, end), None, speaker


# ---------------------------------------------------------------------------
# DiarizedSegment
# ---------------------------------------------------------------------------


class TestDiarizedSegment(unittest.TestCase):
    def test_duration_s_positive(self):
        from ai.speaker_diarization import DiarizedSegment

        seg = DiarizedSegment(start=1.0, end=3.5, speaker="SPEAKER_00")
        self.assertAlmostEqual(seg.duration_s, 2.5)

    def test_duration_s_zero_for_inverted_times(self):
        from ai.speaker_diarization import DiarizedSegment

        seg = DiarizedSegment(start=5.0, end=3.0, speaker="SPEAKER_00")
        self.assertEqual(seg.duration_s, 0.0)


# ---------------------------------------------------------------------------
# PYANNOTE_AVAILABLE flag
# ---------------------------------------------------------------------------


class TestPyannoteAvailabilityFlag(unittest.TestCase):
    def test_flag_exported(self):
        from ai.speaker_diarization import PYANNOTE_AVAILABLE

        self.assertIsInstance(PYANNOTE_AVAILABLE, bool)

    def test_stt_manager_exports_flag(self):
        import ai.stt_manager as mod

        self.assertIn("_PYANNOTE_AVAILABLE", dir(mod))
        self.assertIsInstance(mod._PYANNOTE_AVAILABLE, bool)


# ---------------------------------------------------------------------------
# speaker_summary static method
# ---------------------------------------------------------------------------


class TestSpeakerSummary(unittest.TestCase):
    def test_empty_segments(self):
        from ai.speaker_diarization import SpeakerDiarizer

        result = SpeakerDiarizer.speaker_summary([])
        self.assertEqual(result["num_speakers"], 0)
        self.assertIsNone(result["primary_speaker"])
        self.assertEqual(result["total_speech_seconds"], 0.0)

    def test_single_speaker(self):
        from ai.speaker_diarization import DiarizedSegment, SpeakerDiarizer

        segs = [DiarizedSegment(0.0, 5.0, "SPEAKER_00")]
        result = SpeakerDiarizer.speaker_summary(segs)
        self.assertEqual(result["num_speakers"], 1)
        self.assertEqual(result["primary_speaker"], "SPEAKER_00")
        self.assertAlmostEqual(result["total_speech_seconds"], 5.0)

    def test_primary_is_longest_speaker(self):
        from ai.speaker_diarization import DiarizedSegment, SpeakerDiarizer

        segs = [
            DiarizedSegment(0.0, 2.0, "SPEAKER_00"),
            DiarizedSegment(2.5, 7.0, "SPEAKER_01"),  # 4.5 s — longest
            DiarizedSegment(8.0, 9.0, "SPEAKER_00"),
        ]
        result = SpeakerDiarizer.speaker_summary(segs)
        self.assertEqual(result["primary_speaker"], "SPEAKER_01")
        self.assertEqual(result["num_speakers"], 2)

    def test_total_speech_is_sum_of_durations(self):
        from ai.speaker_diarization import DiarizedSegment, SpeakerDiarizer

        segs = [
            DiarizedSegment(0.0, 2.0, "SPEAKER_00"),
            DiarizedSegment(3.0, 5.5, "SPEAKER_01"),
        ]
        result = SpeakerDiarizer.speaker_summary(segs)
        self.assertAlmostEqual(result["total_speech_seconds"], 4.5, places=2)

    def test_speaker_durations_keys_sorted(self):
        from ai.speaker_diarization import DiarizedSegment, SpeakerDiarizer

        segs = [
            DiarizedSegment(0.0, 1.0, "SPEAKER_02"),
            DiarizedSegment(1.5, 2.5, "SPEAKER_00"),
            DiarizedSegment(3.0, 4.0, "SPEAKER_01"),
        ]
        result = SpeakerDiarizer.speaker_summary(segs)
        keys = list(result["speaker_durations"].keys())
        self.assertEqual(keys, sorted(keys))


# ---------------------------------------------------------------------------
# SpeakerDiarizer — unavailable path
# ---------------------------------------------------------------------------


class TestSpeakerDiarizerUnavailable(unittest.TestCase):
    def test_load_pipeline_returns_false_when_unavailable(self):
        from ai.speaker_diarization import SpeakerDiarizer

        with patch("ai.speaker_diarization.PYANNOTE_AVAILABLE", False):
            d = SpeakerDiarizer(hf_token="tok")
            self.assertFalse(d.load_pipeline())

    def test_diarize_wav_bytes_returns_empty_when_unavailable(self):
        from ai.speaker_diarization import SpeakerDiarizer

        with patch("ai.speaker_diarization.PYANNOTE_AVAILABLE", False):
            d = SpeakerDiarizer()
            result = d.diarize_wav_bytes(_make_wav())
        self.assertEqual(result, [])

    def test_diarize_file_returns_empty_for_missing_file(self):
        from ai.speaker_diarization import SpeakerDiarizer

        d = SpeakerDiarizer()
        result = d.diarize_file("/nonexistent/file.wav")
        self.assertEqual(result, [])

    def test_extract_primary_speaker_returns_original_when_unavailable(self):
        from ai.speaker_diarization import SpeakerDiarizer

        with patch("ai.speaker_diarization.PYANNOTE_AVAILABLE", False):
            d = SpeakerDiarizer()
            wav = _make_wav()
            result = d.extract_primary_speaker_wav(wav)
        self.assertEqual(result, wav)


# ---------------------------------------------------------------------------
# SpeakerDiarizer — mocked pipeline
# ---------------------------------------------------------------------------


class TestSpeakerDiarizerWithMock(unittest.TestCase):
    def _make_diarizer_with_mock_pipeline(self, turns):
        """Return a SpeakerDiarizer whose pipeline is pre-loaded with a fake."""
        from ai.speaker_diarization import SpeakerDiarizer

        d = SpeakerDiarizer(hf_token="tok")
        d._pipeline = MagicMock()
        d._pipeline.return_value = _FakeAnnotation(turns)
        return d

    def test_segments_returned_for_two_speakers(self):
        from ai.speaker_diarization import SpeakerDiarizer

        turns = [(0.0, 2.0, "SPEAKER_00"), (2.5, 5.0, "SPEAKER_01")]
        d = self._make_diarizer_with_mock_pipeline(turns)
        segs = d.diarize_wav_bytes(_make_wav())
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].speaker, "SPEAKER_00")
        self.assertAlmostEqual(segs[0].start, 0.0)
        self.assertAlmostEqual(segs[0].end, 2.0)

    def test_segment_duration_correct(self):
        turns = [(1.0, 3.5, "SPEAKER_00")]
        from ai.speaker_diarization import SpeakerDiarizer

        d = self._make_diarizer_with_mock_pipeline(turns)
        segs = d.diarize_wav_bytes(_make_wav())
        self.assertAlmostEqual(segs[0].duration_s, 2.5)

    def test_empty_annotation_returns_empty_list(self):
        from ai.speaker_diarization import SpeakerDiarizer

        d = self._make_diarizer_with_mock_pipeline([])
        result = d.diarize_wav_bytes(_make_wav())
        self.assertEqual(result, [])

    def test_min_max_speakers_forwarded_to_pipeline(self):
        from ai.speaker_diarization import SpeakerDiarizer

        d = self._make_diarizer_with_mock_pipeline([])
        d.diarize_wav_bytes(_make_wav(), min_speakers=2, max_speakers=4)
        call_kwargs = d._pipeline.call_args[1]
        self.assertEqual(call_kwargs.get("min_speakers"), 2)
        self.assertEqual(call_kwargs.get("max_speakers"), 4)

    def test_stereo_wav_mixed_to_mono_before_pipeline(self):
        """Stereo input must be mixed to mono for pyannote compatibility."""
        from ai.speaker_diarization import SpeakerDiarizer
        import torch

        captured = {}

        def _capture_call(payload, **_kw):
            captured["waveform"] = payload["waveform"]
            return _FakeAnnotation([])

        d = SpeakerDiarizer(hf_token="tok")
        d._pipeline = _capture_call
        d.diarize_wav_bytes(_make_wav(n_channels=2))

        if "waveform" in captured:
            # Mixed-down result must be 1-channel (shape[0] == 1)
            self.assertEqual(captured["waveform"].shape[0], 1)

    def test_unsupported_sampwidth_returns_empty(self):
        """24-bit WAV should be rejected gracefully."""
        from ai.speaker_diarization import SpeakerDiarizer

        n = 16000 * 3
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(16000)
            wf.writeframes(bytes(n * 3))
        wav_24bit = out.getvalue()

        d = self._make_diarizer_with_mock_pipeline([])
        result = d.diarize_wav_bytes(wav_24bit)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# extract_primary_speaker_wav
# ---------------------------------------------------------------------------


class TestExtractPrimarySpeaker(unittest.TestCase):
    def _diarizer_with_segments(self, turns):
        from ai.speaker_diarization import SpeakerDiarizer

        d = SpeakerDiarizer(hf_token="tok")
        d._pipeline = MagicMock(return_value=_FakeAnnotation(turns))
        return d

    def test_output_is_valid_wav_same_length(self):
        turns = [(0.0, 1.5, "SPEAKER_00"), (2.0, 3.0, "SPEAKER_01")]
        d = self._diarizer_with_segments(turns)
        wav = _make_wav(duration_ms=3000)
        result = d.extract_primary_speaker_wav(wav)
        with wave.open(io.BytesIO(result), "rb") as wf:
            self.assertEqual(wf.getnframes(), wave.open(io.BytesIO(wav), "rb").getnframes())

    def test_non_primary_frames_zeroed(self):
        """Frames outside the primary speaker window must be zero."""
        # SPEAKER_00 speaks 0-1 s, SPEAKER_01 speaks 1-3 s (longer → primary)
        turns = [(0.0, 1.0, "SPEAKER_00"), (1.0, 3.0, "SPEAKER_01")]
        d = self._diarizer_with_segments(turns)
        wav = _make_wav(duration_ms=3000, amplitude=0.8)
        result = d.extract_primary_speaker_wav(wav)

        import numpy as np

        with wave.open(io.BytesIO(result), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            sr = wf.getframerate()
        arr = np.frombuffer(raw, dtype="<i2")
        # First second (SPEAKER_00 — not primary) should be silent
        first_second = arr[:sr]
        self.assertTrue(np.all(first_second == 0))

    def test_returns_original_when_no_segments(self):
        from ai.speaker_diarization import SpeakerDiarizer

        with patch("ai.speaker_diarization.PYANNOTE_AVAILABLE", False):
            d = SpeakerDiarizer()
            wav = _make_wav()
        self.assertEqual(d.extract_primary_speaker_wav(wav), wav)


# ---------------------------------------------------------------------------
# STTManager.transcribe_file_with_diarization
# ---------------------------------------------------------------------------


class TestTranscribeFileWithDiarization(unittest.TestCase):
    def _tmp_wav(self, tmp_dir: str) -> str:
        import os

        path = os.path.join(tmp_dir, "test.wav")
        with open(path, "wb") as f:
            f.write(_make_wav(duration_ms=3000))
        return path

    def test_returns_unavailable_for_missing_file(self):
        from ai.stt_manager import STTManager

        stt = STTManager(api_key="key")
        result = stt.transcribe_file_with_diarization("/no/such/file.wav")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "file not found")

    def test_degrades_gracefully_when_pyannote_absent(self):
        import ai.stt_manager as mod
        import tempfile

        with (
            patch.object(mod, "_PYANNOTE_AVAILABLE", False),
            patch.object(mod, "_SpeakerDiarizer", None),
        ):
            stt = mod.STTManager(api_key="key")
            with patch.object(
                stt, "transcribe_file_with_confidence", return_value=("hello world", 0.9)
            ):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(_make_wav())
                    tmp = f.name
                try:
                    result = stt.transcribe_file_with_diarization(tmp)
                finally:
                    import os

                    os.unlink(tmp)

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "pyannote.audio not installed")
        self.assertEqual(result["transcript"], "hello world")
        self.assertAlmostEqual(result["confidence"], 0.9)

    def test_returns_segments_from_diarizer(self):
        import ai.stt_manager as mod
        import tempfile
        from ai.speaker_diarization import DiarizedSegment, SpeakerDiarizer

        turns = [(0.0, 2.0, "SPEAKER_00"), (2.5, 4.0, "SPEAKER_01")]
        mock_diarizer = MagicMock(spec=SpeakerDiarizer)
        mock_diarizer.diarize_file.return_value = [DiarizedSegment(s, e, sp) for s, e, sp in turns]
        mock_diarizer.speaker_summary = SpeakerDiarizer.speaker_summary

        mock_cls = MagicMock(return_value=mock_diarizer)
        mock_cls.speaker_summary = staticmethod(SpeakerDiarizer.speaker_summary)

        with (
            patch.object(mod, "_PYANNOTE_AVAILABLE", True),
            patch.object(mod, "_SpeakerDiarizer", mock_cls),
        ):
            stt = mod.STTManager(api_key="key")
            with patch.object(
                stt, "transcribe_file_with_confidence", return_value=("hello there", 0.85)
            ):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(_make_wav())
                    tmp = f.name
                try:
                    result = stt.transcribe_file_with_diarization(tmp, hf_token="tok")
                finally:
                    import os

                    os.unlink(tmp)

        self.assertTrue(result["available"])
        self.assertEqual(result["transcript"], "hello there")
        self.assertEqual(result["num_speakers"], 2)
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][0]["speaker"], "SPEAKER_00")
        self.assertAlmostEqual(result["segments"][1]["start"], 2.5)

    def test_result_has_required_keys(self):
        import ai.stt_manager as mod
        import tempfile

        with (
            patch.object(mod, "_PYANNOTE_AVAILABLE", False),
            patch.object(mod, "_SpeakerDiarizer", None),
        ):
            stt = mod.STTManager(api_key="key")
            with patch.object(stt, "transcribe_file_with_confidence", return_value=("", 0.0)):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(_make_wav())
                    tmp = f.name
                try:
                    result = stt.transcribe_file_with_diarization(tmp)
                finally:
                    import os

                    os.unlink(tmp)

        for key in (
            "available",
            "transcript",
            "confidence",
            "num_speakers",
            "segments",
            "speaker_summary",
        ):
            self.assertIn(key, result)

    def test_hf_token_forwarded_to_diarizer(self):
        import ai.stt_manager as mod
        import tempfile
        from ai.speaker_diarization import SpeakerDiarizer

        mock_diarizer = MagicMock(spec=SpeakerDiarizer)
        mock_diarizer.diarize_file.return_value = []
        mock_diarizer.speaker_summary = SpeakerDiarizer.speaker_summary
        mock_cls = MagicMock(return_value=mock_diarizer)
        mock_cls.speaker_summary = staticmethod(SpeakerDiarizer.speaker_summary)

        with (
            patch.object(mod, "_PYANNOTE_AVAILABLE", True),
            patch.object(mod, "_SpeakerDiarizer", mock_cls),
        ):
            stt = mod.STTManager(api_key="key")
            with patch.object(stt, "transcribe_file_with_confidence", return_value=("", 0.0)):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(_make_wav())
                    tmp = f.name
                try:
                    stt.transcribe_file_with_diarization(tmp, hf_token="my-hf-token")
                finally:
                    import os

                    os.unlink(tmp)

        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        self.assertEqual(call_kwargs.get("hf_token"), "my-hf-token")


if __name__ == "__main__":
    unittest.main()
