"""Tests for sounddevice-powered mic capture in STTManager."""

from __future__ import annotations

import queue
import time
import unittest
from unittest.mock import MagicMock, patch


def _make_stt(mode: str = "api"):
    from ai.stt_manager import STTManager

    return STTManager(api_key="test_key", mode=mode)


def _silence_chunk(samples: int = 1024) -> bytes:
    return bytes(samples * 2)  # int16 zeros


class TestSounddeviceAvailability(unittest.TestCase):
    def test_flag_is_bool(self):
        import ai.stt_manager as mod

        self.assertIn("_SOUNDDEVICE_AVAILABLE", dir(mod))
        self.assertIsInstance(mod._SOUNDDEVICE_AVAILABLE, bool)


class TestListAudioDevicesSounddeviceFallback(unittest.TestCase):
    def test_sounddevice_fallback_used_when_pyaudio_and_sr_absent(self):
        import ai.stt_manager as mod

        fake_devices = [
            {"name": "Built-in Mic", "max_input_channels": 2, "default_samplerate": 44100.0},
            {"name": "HDMI Out", "max_input_channels": 0, "default_samplerate": 48000.0},
            {"name": "USB Mic", "max_input_channels": 1, "default_samplerate": 16000.0},
        ]
        fake_default = {"index": 0, "name": "Built-in Mic"}
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = lambda kind=None: (
            fake_default if kind == "input" else fake_devices
        )

        with (
            patch.object(mod, "_pyaudio", None),
            patch.object(mod, "sr", None),
            patch.object(mod, "_sd", mock_sd),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True),
        ):
            devices = mod.STTManager.list_audio_devices()

        # Only input devices (max_input_channels > 0) should be returned
        self.assertEqual(len(devices), 2)
        names = [d["name"] for d in devices]
        self.assertIn("Built-in Mic", names)
        self.assertIn("USB Mic", names)
        self.assertNotIn("HDMI Out", names)

    def test_sounddevice_fallback_sets_default_flag(self):
        import ai.stt_manager as mod

        fake_devices = [
            {"name": "Mic A", "max_input_channels": 1, "default_samplerate": 16000.0},
            {"name": "Mic B", "max_input_channels": 1, "default_samplerate": 44100.0},
        ]
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = lambda kind=None: (
            {"index": 1} if kind == "input" else fake_devices
        )

        with (
            patch.object(mod, "_pyaudio", None),
            patch.object(mod, "sr", None),
            patch.object(mod, "_sd", mock_sd),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True),
        ):
            devices = mod.STTManager.list_audio_devices()

        self.assertFalse(devices[0]["is_default_input"])
        self.assertTrue(devices[1]["is_default_input"])

    def test_sounddevice_skipped_when_pyaudio_present(self):
        """PyAudio takes priority — sounddevice branch must not be reached."""
        import ai.stt_manager as mod

        mock_pa = MagicMock()
        mock_pa.PyAudio.return_value.get_device_count.return_value = 0
        mock_pa.PyAudio.return_value.get_default_input_device_info.side_effect = Exception
        mock_sd = MagicMock()

        with patch.object(mod, "_pyaudio", mock_pa), patch.object(mod, "_sd", mock_sd):
            mod.STTManager.list_audio_devices()

        mock_sd.query_devices.assert_not_called()

    def test_returns_empty_when_all_backends_absent(self):
        import ai.stt_manager as mod

        with (
            patch.object(mod, "_pyaudio", None),
            patch.object(mod, "sr", None),
            patch.object(mod, "_sd", None),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", False),
        ):
            result = mod.STTManager.list_audio_devices()
        self.assertEqual(result, [])


class TestTranscribeMicSounddeviceMethod(unittest.TestCase):
    def test_returns_empty_when_sd_none(self):
        import ai.stt_manager as mod

        with patch.object(mod, "_sd", None), patch.object(mod, "_SOUNDDEVICE_AVAILABLE", False):
            stt = _make_stt()
            result = stt._transcribe_microphone_sounddevice_with_interim()
        self.assertEqual(result, ("", 0.0))

    def test_returns_empty_when_not_api_mode(self):
        import ai.stt_manager as mod

        mock_sd = MagicMock()
        with patch.object(mod, "_sd", mock_sd), patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True):
            stt = _make_stt(mode="local")
            result = stt._transcribe_microphone_sounddevice_with_interim()
        self.assertEqual(result, ("", 0.0))
        mock_sd.RawInputStream.assert_not_called()

    def test_raw_input_stream_opened_with_correct_params(self):
        import ai.stt_manager as mod

        captured_kwargs: dict = {}

        class _FakeStream:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        def _fake_raw_input_stream(**kwargs):
            captured_kwargs.update(kwargs)
            return _FakeStream()

        mock_sd = MagicMock()
        mock_sd.RawInputStream.side_effect = _fake_raw_input_stream

        with (
            patch.object(mod, "_sd", mock_sd),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True),
            patch.object(mod.STTManager, "transcribe_stream_with_interim", return_value=("", 0.0)),
        ):
            stt = _make_stt()
            stt._transcribe_microphone_sounddevice_with_interim(
                mic_device_index=2,
                sample_rate=16000,
            )

        self.assertEqual(captured_kwargs.get("samplerate"), 16000)
        self.assertEqual(captured_kwargs.get("channels"), 1)
        self.assertEqual(captured_kwargs.get("dtype"), "int16")
        self.assertEqual(captured_kwargs.get("device"), 2)

    def test_transcribe_stream_called_with_correct_sample_rate(self):
        import ai.stt_manager as mod

        class _FakeStream:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        mock_sd = MagicMock()
        mock_sd.RawInputStream.return_value = _FakeStream()
        captured = {}

        def _fake_stream(audio_chunks, interim_callback=None, sample_rate_hz=16000):
            captured["sample_rate_hz"] = sample_rate_hz
            return "hello", 0.9

        with (
            patch.object(mod, "_sd", mock_sd),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True),
            patch.object(
                mod.STTManager, "transcribe_stream_with_interim", side_effect=_fake_stream
            ),
        ):
            stt = _make_stt()
            text, confidence = stt._transcribe_microphone_sounddevice_with_interim(
                sample_rate=48000,
            )

        self.assertEqual(captured.get("sample_rate_hz"), 48000)
        self.assertEqual(text, "hello")
        self.assertAlmostEqual(confidence, 0.9)

    def test_exception_in_stream_returns_empty(self):
        import ai.stt_manager as mod

        mock_sd = MagicMock()
        mock_sd.RawInputStream.side_effect = OSError("no device")

        with patch.object(mod, "_sd", mock_sd), patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True):
            stt = _make_stt()
            result = stt._transcribe_microphone_sounddevice_with_interim()

        self.assertEqual(result, ("", 0.0))


class TestTranscribeMicWithInterimDelegatesToSounddevice(unittest.TestCase):
    def test_delegates_to_sounddevice_when_sr_absent(self):
        import ai.stt_manager as mod

        called_with: dict = {}

        def _fake_sd_method(**kwargs):
            called_with.update(kwargs)
            return "delegated", 0.85

        with patch.object(mod, "sr", None):
            stt = _make_stt()
            stt._transcribe_microphone_sounddevice_with_interim = lambda **kw: _fake_sd_method(**kw)
            text, conf = stt.transcribe_microphone_with_interim(
                mic_device_index=1,
                timeout_seconds=3,
            )

        self.assertEqual(text, "delegated")
        self.assertAlmostEqual(conf, 0.85)

    def test_returns_empty_when_both_sr_and_sd_absent(self):
        import ai.stt_manager as mod

        with (
            patch.object(mod, "sr", None),
            patch.object(mod, "_sd", None),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", False),
        ):
            stt = _make_stt()
            result = stt.transcribe_microphone_with_interim()
        self.assertEqual(result, ("", 0.0))

    def test_local_mode_returns_empty_regardless_of_backends(self):
        import ai.stt_manager as mod

        mock_sd = MagicMock()
        with (
            patch.object(mod, "sr", None),
            patch.object(mod, "_sd", mock_sd),
            patch.object(mod, "_SOUNDDEVICE_AVAILABLE", True),
        ):
            stt = _make_stt(mode="local")
            result = stt.transcribe_microphone_with_interim()
        self.assertEqual(result, ("", 0.0))
        mock_sd.RawInputStream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
