from typing import Tuple


HIGH_RISK_KEYWORDS = (
    # English
    "suicide",
    "kill myself",
    "end my life",
    "hurt myself",
    "self harm",
    "self-harm",
    "want to die",
    "overdose",
    # Arabic
    "انتحار",
    "اقتل نفسي",
    "اختم حياتي",
    "أؤذي نفسي",
    "أجرح نفسي",
    "أريد الموت",
    "موت",
    "ودي أموت",
    "خنقت",
    "ما ابغى اعيش",
)

MODERATE_RISK_KEYWORDS = (
    # English
    "hopeless",
    "i can't go on",
    "panic attack",
    "severe depression",
    "i am not safe",
    # Arabic
    "يائس",
    "ما قدرت أكمل",
    "ضاق صدري",
    "قلبي انقبض",
    "هلع",
    "اكتئاب شديد",
    "حزين",
    "زعلان",
    "قلقان",
    "محد يحبني",
    "مافي أمل",
    "ما في أمل",
)


def evaluate_safety(user_text: str) -> Tuple[str, str]:
    lower = (user_text or "").lower()

    for kw in HIGH_RISK_KEYWORDS:
        if kw in lower:
            return (
                "high",
                "I am really glad you said this. Your safety matters most right now. "
                "Please contact local emergency services immediately or reach out to a trusted person near you now. "
                "If you want, I can stay with you while you take that first step.",
            )

    for kw in MODERATE_RISK_KEYWORDS:
        if kw in lower:
            return (
                "moderate",
                "I hear that this is very heavy right now. "
                "Let's take one immediate grounding step: slow breathing for 30 seconds. "
                "If this feels unmanageable, please contact a licensed professional or emergency support in your area.",
            )

    return "none", ""
