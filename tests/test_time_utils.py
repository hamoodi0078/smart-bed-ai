import unittest
from datetime import datetime, timezone

from time_utils import ensure_utc, from_iso, to_iso, utcnow


class TestTimeUtils(unittest.TestCase):
    def test_utcnow_returns_aware_utc(self):
        now = utcnow()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.utcoffset().total_seconds(), 0)

    def test_ensure_utc_assumes_naive_input_is_utc(self):
        naive = datetime(2026, 3, 1, 12, 30, 0)
        normalized = ensure_utc(naive)
        self.assertIsNotNone(normalized.tzinfo)
        self.assertEqual(normalized.utcoffset().total_seconds(), 0)
        self.assertEqual(normalized.hour, 12)

    def test_iso_round_trip_keeps_utc(self):
        original = datetime(2026, 3, 1, 8, 45, 0, tzinfo=timezone.utc)
        encoded = to_iso(original)
        decoded = from_iso(encoded)
        self.assertTrue(encoded.endswith("Z"))
        self.assertEqual(decoded, original)


if __name__ == "__main__":
    unittest.main()
