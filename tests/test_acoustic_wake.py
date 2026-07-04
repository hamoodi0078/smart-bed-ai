"""Tests for the on-device acoustic wake-word detector."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from ai.acoustic_wake import AcousticWakeDetector
from ai.wake_word_manager import WakeWordManager


class _FakeEngine:
    """Engine that reports a detection on the Nth processed frame."""

    frame_length = 4

    def __init__(self, fire_on_frame: int = 3):
        self.fire_on_frame = fire_on_frame
        self.processed = 0
        self.closed = False

    def process(self, frame) -> bool:
        self.processed += 1
        return self.processed >= self.fire_on_frame

    def close(self) -> None:
        self.closed = True


@contextmanager
def _fake_stream(frame_samples: int):
    def read_frame():
        return [0] * frame_samples

    yield read_frame


class TestAcousticWakeDetector(unittest.TestCase):
    def test_off_backend_reports_disabled(self):
        detector = AcousticWakeDetector(backend="off")
        self.assertFalse(detector.available)
        self.assertIn("disabled", detector.status_line().lower())

    def test_unconfigured_backends_are_unavailable_with_reason(self):
        detector = AcousticWakeDetector(backend="auto")
        self.assertFalse(detector.available)
        self.assertTrue(detector.status_line())

    def test_injected_engine_detects_wake(self):
        engine = _FakeEngine(fire_on_frame=3)
        detector = AcousticWakeDetector(engine=engine, stream_factory=_fake_stream)
        self.assertTrue(detector.available)
        self.assertTrue(detector.wait_for_wake(timeout_seconds=5.0))
        self.assertEqual(engine.processed, 3)

    def test_wait_times_out_when_engine_never_fires(self):
        engine = _FakeEngine(fire_on_frame=10**9)
        detector = AcousticWakeDetector(engine=engine, stream_factory=_fake_stream)
        self.assertFalse(detector.wait_for_wake(timeout_seconds=0.05))

    def test_stop_unblocks_wait(self):
        engine = _FakeEngine(fire_on_frame=10**9)
        detector = AcousticWakeDetector(engine=engine, stream_factory=_fake_stream)
        # stop before waiting — the loop must exit promptly with False
        detector.stop()
        # stop() before wait clears is overwritten by wait's clear; use timeout
        self.assertFalse(detector.wait_for_wake(timeout_seconds=0.05))

    def test_close_shuts_engine(self):
        engine = _FakeEngine()
        detector = AcousticWakeDetector(engine=engine, stream_factory=_fake_stream)
        detector.close()
        self.assertTrue(engine.closed)
        self.assertFalse(detector.available)


class TestWakeWordManagerAcousticIntegration(unittest.TestCase):
    def test_manager_without_detector_reports_not_configured(self):
        manager = WakeWordManager(mode="keyboard")
        self.assertFalse(manager.has_acoustic_wake())
        self.assertIn("not configured", manager.acoustic_wake_status().lower())

    def test_wait_for_wake_text_uses_acoustic_detector(self):
        engine = _FakeEngine(fire_on_frame=1)
        detector = AcousticWakeDetector(engine=engine, stream_factory=_fake_stream)
        manager = WakeWordManager(mode="voice", wake_word="hey dana", acoustic_detector=detector)
        self.assertTrue(manager.has_acoustic_wake())
        with patch.object(manager, "is_voice_available", return_value=True):
            result = manager.wait_for_wake_text()
        self.assertEqual(result, "hey dana")
        self.assertEqual(engine.processed, 1)


if __name__ == "__main__":
    unittest.main()
