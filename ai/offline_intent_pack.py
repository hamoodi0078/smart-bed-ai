import re
from datetime import datetime


class OfflineIntentPack:
    def handle(self, user_text: str):
        lower = user_text.lower().strip()

        if lower in ("hi", "hello", "hey"):
            return "Hello. I am here and ready to help.", True

        if "how are you" in lower:
            return "I am running well. How can I help right now?", True

        if "what can you do" in lower or "help" == lower:
            return (
                "I can handle alarms, time queries, routines, lights, and local music commands even in offline mode.",
                True,
            )

        if lower.startswith("calculate "):
            expr = lower.replace("calculate", "", 1).strip()
            if re.fullmatch(r"[0-9\s\+\-\*\/\(\)\.]+", expr):
                try:
                    value = eval(expr, {"__builtins__": {}}, {})
                    return f"The result is {value}.", True
                except Exception:
                    return "I could not calculate that expression.", True

        if "time" in lower and "now" in lower:
            return f"Local time is {datetime.now().strftime('%I:%M %p')}.", True

        return "", False
