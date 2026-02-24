import json
from pathlib import Path

PROFILE_PATH = Path("user_profile.json")
LOCAL_DATA_PATHS = (
    PROFILE_PATH,
    Path("data/alarms.json"),
    Path("data/cache.db"),
    Path("data/cache.db-shm"),
    Path("data/cache.db-wal"),
    Path("data/subscription_db.json"),
    Path("data/spotify_tokens.json"),
)
OUTPUT_AUDIO_DIR = Path("output_audio")
OUTPUT_AUDIO_PATTERNS = ("*.mp3", "*.wav", "*.ogg")


def load_profile():
    if not PROFILE_PATH.exists():
        return None

    try:
        with PROFILE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_profile(profile: dict):
    with PROFILE_PATH.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def delete_profile() -> bool:
    return delete_local_data()


def delete_local_data() -> bool:
    try:
        for path in LOCAL_DATA_PATHS:
            if path.exists():
                path.unlink()

        if OUTPUT_AUDIO_DIR.exists() and OUTPUT_AUDIO_DIR.is_dir():
            for pattern in OUTPUT_AUDIO_PATTERNS:
                for audio_file in OUTPUT_AUDIO_DIR.glob(pattern):
                    if audio_file.is_file():
                        audio_file.unlink()
        return True
    except Exception:
        return False
