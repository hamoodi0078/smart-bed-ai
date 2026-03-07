import unittest

from ai.voice_circuit_breaker import STATE_CLOSED, STATE_HALF_OPEN, STATE_OPEN, VoiceCircuitBreaker


class _FakeClock:
    def __init__(self, start: float = 100.0):
        self.now = float(start)

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += float(seconds)


class TestVoiceCircuitBreaker(unittest.TestCase):
    def test_breaker_opens_after_repeated_failures(self):
        clock = _FakeClock()
        breaker = VoiceCircuitBreaker(
            failure_threshold=3,
            backoff_base_seconds=4.0,
            backoff_max_seconds=60.0,
            time_fn=clock.time,
        )

        breaker.record_failure()
        breaker.record_failure()
        snapshot = breaker.record_failure()

        self.assertEqual(snapshot["state"], STATE_OPEN)
        self.assertEqual(snapshot["failure_count"], 3)
        self.assertAlmostEqual(snapshot["next_retry_time"], 104.0, places=4)

    def test_exponential_backoff_is_applied_on_repeated_open_cycles(self):
        clock = _FakeClock()
        breaker = VoiceCircuitBreaker(
            failure_threshold=2,
            backoff_base_seconds=3.0,
            backoff_max_seconds=30.0,
            time_fn=clock.time,
        )

        breaker.record_failure()
        first_open = breaker.record_failure()
        self.assertEqual(first_open["state"], STATE_OPEN)
        self.assertAlmostEqual(first_open["next_retry_time"], 103.0, places=4)

        allowed, gate_state = breaker.before_call()
        self.assertFalse(allowed)
        self.assertEqual(gate_state, STATE_OPEN)

        clock.advance(3.1)
        allowed, gate_state = breaker.before_call()
        self.assertTrue(allowed)
        self.assertEqual(gate_state, STATE_HALF_OPEN)

        second_open = breaker.record_failure()
        self.assertEqual(second_open["state"], STATE_OPEN)
        self.assertEqual(second_open["failure_count"], 3)
        self.assertAlmostEqual(second_open["next_retry_time"], clock.time() + 6.0, places=4)

    def test_manual_reset_restores_closed_state(self):
        clock = _FakeClock()
        breaker = VoiceCircuitBreaker(
            failure_threshold=1,
            backoff_base_seconds=5.0,
            backoff_max_seconds=20.0,
            time_fn=clock.time,
        )

        breaker.record_failure()
        reset = breaker.manual_reset(reason="test")
        self.assertEqual(reset["state"], STATE_CLOSED)
        self.assertEqual(reset["failure_count"], 0)
        self.assertIsNone(reset["last_failure_time"])
        self.assertIsNone(reset["next_retry_time"])

        allowed, gate_state = breaker.before_call()
        self.assertTrue(allowed)
        self.assertEqual(gate_state, STATE_CLOSED)

    def test_fallback_path_is_used_while_open(self):
        clock = _FakeClock()
        breaker = VoiceCircuitBreaker(
            failure_threshold=1,
            backoff_base_seconds=10.0,
            backoff_max_seconds=10.0,
            time_fn=clock.time,
        )
        breaker.record_failure()

        calls = {"op": 0, "fallback": 0}

        def _operation():
            calls["op"] += 1
            return "ok"

        def _fallback(reason: str):
            calls["fallback"] += 1
            return f"fallback:{reason}"

        result, used_fallback, reason, snapshot = breaker.run(operation=_operation, fallback=_fallback)

        self.assertTrue(used_fallback)
        self.assertEqual(reason, "circuit_open")
        self.assertEqual(snapshot["state"], STATE_OPEN)
        self.assertEqual(calls["op"], 0)
        self.assertEqual(calls["fallback"], 1)
        self.assertEqual(result, "fallback:circuit_open")


if __name__ == "__main__":
    unittest.main()
