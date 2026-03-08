import io
import json
import logging
import unittest

from core.structured_logging import build_log_record, emit_json_log, hash_user_id


class TestStructuredLogging(unittest.TestCase):
    def test_sample_record_has_required_structure(self):
        record = build_log_record(
            level="info",
            event_type="voice_pipeline_success",
            trace_id="req_abc12345",
            user_id="user-42",
            metadata={"breaker_state": "closed", "audio_played": True},
        )

        self.assertIn("timestamp", record)
        self.assertEqual(record.get("level"), "INFO")
        self.assertEqual(record.get("trace_id"), "req_abc12345")
        self.assertEqual(record.get("event_type"), "voice_pipeline_success")
        self.assertEqual(record.get("metadata", {}).get("breaker_state"), "closed")
        self.assertEqual(record.get("metadata", {}).get("audio_played"), True)

    def test_sensitive_fields_are_removed(self):
        record = build_log_record(
            level="warning",
            event_type="voice_pipeline_failure",
            trace_id="req_sensitive01",
            user_id="user-7",
            metadata={
                "transcript": "turn on the lights",
                "message": "raw user message",
                "api_key": "secret-key",
                "email": "user@example.com",
                "user_id": "raw-user",
                "error_type": "RuntimeError",
            },
        )

        metadata = record.get("metadata", {})
        self.assertNotIn("transcript", metadata)
        self.assertNotIn("message", metadata)
        self.assertNotIn("api_key", metadata)
        self.assertNotIn("email", metadata)
        self.assertNotIn("user_id", metadata)
        self.assertEqual(metadata.get("error_type"), "RuntimeError")

    def test_trace_and_hashed_user_id_present_in_emitted_json(self):
        stream = io.StringIO()
        logger = logging.getLogger("tests.structured_logging")
        logger.handlers = []
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)

        emit_json_log(
            logger,
            level="info",
            event_type="quiet_hours_decision",
            trace_id="req_trace99",
            user_id="u1",
            metadata={"quiet_active": True},
        )
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload.get("trace_id"), "req_trace99")
        self.assertEqual(payload.get("event_type"), "quiet_hours_decision")
        self.assertEqual(payload.get("metadata", {}).get("quiet_active"), True)
        self.assertEqual(payload.get("user_id"), hash_user_id("u1"))
        self.assertNotEqual(payload.get("user_id"), "u1")


if __name__ == "__main__":
    unittest.main()
