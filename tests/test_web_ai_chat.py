import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class _FakeChatEngine:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict] = []

    def generate_response(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.reply


class _FakeMemoryStore:
    def __init__(self):
        self.prompt_inputs: list[str] = []
        self.recorded: list[dict] = []

    def memory_prompt_line(self, user_text: str) -> str:
        self.prompt_inputs.append(str(user_text))
        return "Continuity memory: In prior sessions user mentioned -> sleep debt"

    def record_turn(self, user_text: str, assistant_text: str, emotion_state: str, personality: str):
        self.recorded.append(
            {
                "user_text": str(user_text),
                "assistant_text": str(assistant_text),
                "emotion_state": str(emotion_state),
                "personality": str(personality),
            }
        )


class TestWebAiChat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.profile_path = Path(self._tmp.name) / "user_profile.json"
        self.sqlite_path = Path(self._tmp.name) / "web_ai_chat.sqlite3"
        self.database_url = f"sqlite:///{self.sqlite_path.as_posix()}"
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)

        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": self.database_url},
            clear=False,
        )
        self._patch_store = patch.object(web_server, "store", self.store)
        self._patch_profile = patch.object(web_server, "PROFILE_PATH", self.profile_path)
        self._patch_env.start()
        self._patch_store.start()
        self._patch_profile.start()
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        self.client = TestClient(web_server.app)

    def tearDown(self):
        connection = getattr(web_server, "_DB_CONNECTION", None)
        if connection is not None:
            try:
                connection.engine.dispose()
            except Exception:
                pass
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        self._patch_profile.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        self._tmp.cleanup()

    def _register(self, email: str = "chat@example.com", password: str = "secret123", name: str = "Chat User"):
        return self.client.post(
            "/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )

    def test_requires_auth(self):
        response = self.client.post("/v1/ai/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 401)

    def test_chat_uses_engine_with_user_scoped_context(self):
        register = self._register()
        self.assertEqual(register.status_code, 200)

        self.client.post(
            "/v1/mobile/settings",
            json={
                "response_style": "coaching",
                "engagement_level": "medium",
                "wind_down_minutes": 35,
                "partner_mode_enabled": True,
            },
        )
        self.client.post(
            "/v1/mobile/profile",
            json={
                "display_name": "Dana",
                "timezone": "Asia/Karachi",
                "push_enabled": True,
                "email_enabled": False,
            },
        )
        self.client.post(
            "/v1/mobile/routine",
            json={"bedtime": "23:15", "wake": "06:45", "weekends": False},
        )

        fake_engine = _FakeChatEngine("AI response from engine.")
        fake_memory = _FakeMemoryStore()
        with patch("web_server._chat_engine_for_user", return_value=fake_engine), patch(
            "web_server._memory_store_for_user", return_value=fake_memory
        ):
            response = self.client.post("/v1/ai/chat", json={"message": "I feel tired and I need a plan."})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("reply"), "AI response from engine.")
        self.assertEqual(len(fake_engine.calls), 1)
        call = fake_engine.calls[0]
        self.assertEqual(call.get("personality"), "coach")
        self.assertEqual(call.get("cognitive_load_mode"), "reduced")
        self.assertEqual(call.get("emotion_state"), "low_energy")
        self.assertIn("user_timezone=Asia/Karachi", str(call.get("user_context", "")))
        self.assertIn("routine_bedtime=23:15", str(call.get("user_context", "")))
        self.assertIn("Continuity memory:", str(call.get("user_context", "")))

        self.assertEqual(len(fake_memory.recorded), 1)
        self.assertEqual(fake_memory.recorded[0].get("assistant_text"), "AI response from engine.")
        self.assertEqual(fake_memory.recorded[0].get("personality"), "coach")

    def test_chat_falls_back_when_engine_returns_deepgram_fallback(self):
        self._register(email="fallback@example.com", password="secret123", name="Fallback User")

        fake_engine = _FakeChatEngine("(Deepgram fallback - guide) temporary fallback text.")
        fake_memory = _FakeMemoryStore()
        with patch("web_server._chat_engine_for_user", return_value=fake_engine), patch(
            "web_server._memory_store_for_user", return_value=fake_memory
        ):
            response = self.client.post("/v1/ai/chat", json={"message": "show me system status"})

        self.assertEqual(response.status_code, 200)
        reply = response.json().get("reply", "")
        self.assertIn("System looks stable right now", reply)
        self.assertEqual(len(fake_memory.recorded), 1)
        self.assertIn("System looks stable right now", fake_memory.recorded[0].get("assistant_text", ""))


if __name__ == "__main__":
    unittest.main()
