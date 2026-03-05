from datetime import datetime, timedelta, timezone

from commands.reflection import detect_reflection_intent, process_reflection_turn


def test_detect_reflection_intent():
    assert detect_reflection_intent("Can we do a daily reflection?")
    assert detect_reflection_intent("Give me a daily summary")
    assert detect_reflection_intent("How was my day?")
    assert detect_reflection_intent("End of day thoughts")
    assert not detect_reflection_intent("What's the weather?")


def test_trigger_sets_reflection_state():
    profile = {"runtime_flags": {}}

    reply, handled, changed = process_reflection_turn("daily reflection", profile)

    assert handled is True
    assert changed is True
    assert "tawakkul" in reply.lower()
    reflection = profile.get("reflection", {})
    assert reflection.get("active") is True
    assert reflection.get("step") == "ASKED"
    assert isinstance(reflection.get("started_at_utc"), str)


def test_negative_followup_clears_state_and_returns_message():
    profile = {
        "reflection": {
            "active": True,
            "step": "ASKED",
            "started_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "runtime_flags": {},
    }

    reply, handled, changed = process_reflection_turn("I wasted time today", profile)

    assert handled is True
    assert changed is True
    assert "small task" in reply.lower()
    assert "allahumma" in reply.lower()
    reflection = profile.get("reflection", {})
    assert reflection.get("active") is False
    assert reflection.get("step") == ""


def test_positive_followup_clears_state_and_returns_message():
    profile = {
        "reflection": {
            "active": True,
            "step": "ASKED",
            "started_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "runtime_flags": {},
    }

    reply, handled, changed = process_reflection_turn("Yes, I did well today", profile)

    assert handled is True
    assert changed is True
    assert "alhamdulillah" in reply.lower()
    assert "tomorrow" in reply.lower()
    reflection = profile.get("reflection", {})
    assert reflection.get("active") is False
    assert reflection.get("step") == ""


def test_timeout_clears_state_after_hours():
    started = datetime.now(timezone.utc) - timedelta(hours=13)
    profile = {
        "reflection": {
            "active": True,
            "step": "ASKED",
            "started_at_utc": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "runtime_flags": {},
    }

    reply, handled, changed = process_reflection_turn(
        "hello",
        profile,
        timeout_hours=12,
        now_provider=lambda: datetime.now(timezone.utc),
    )

    assert reply == ""
    assert handled is False
    assert changed is True
    reflection = profile.get("reflection", {})
    assert reflection.get("active") is False
    assert reflection.get("step") == ""
