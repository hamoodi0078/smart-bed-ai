import json
from pathlib import Path

PROFILE_PATH = Path("user_profile.json")
LEGACY_SPOTIFY_TOKENS_PATH = Path("data/spotify_tokens.json")

# These top-level fields are personal state for the active local user profile.
# We remove them during "delete my data" while keeping shared/system-level files intact.
USER_OWNED_PROFILE_KEYS = (
    "name",
    "age",
    "gender",
    "education",
    "preferences",
    "progress",
    "sleep",
    "onboarding",
    "goals",
    "daily_life",
    "goal_compass",
    "goal_strategy",
    "environment",
    "personality_runtime",
    "adaptive_personality",
    "proactive",
    "safety_valve",
    "runtime_flags",
)

# These sections are keyed per-user (usually user_id/email). We only remove the current
# user's entry, leaving other users' records untouched.
USER_SCOPED_PROFILE_MAP_KEYS = (
    "web_settings",
    "web_routines",
    "web_profile_prefs",
    "web_device_controls",
    "web_timeline",
    "web_device_commands",
    "spotify_tokens",
    "spotify_oauth_state",
)


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


def _resolve_current_user_key(profile: dict, preferred_key: str = "") -> str:
    candidate = str(preferred_key or "").strip()
    if candidate:
        return candidate

    direct_user_id = str(profile.get("user_id", "") or "").strip()
    if direct_user_id:
        return direct_user_id

    direct_email = str(profile.get("email", "") or "").strip().lower()
    if direct_email:
        return direct_email

    scoped_keys = set()
    for section_key in USER_SCOPED_PROFILE_MAP_KEYS:
        section = profile.get(section_key, {})
        if not isinstance(section, dict):
            continue
        for key in section.keys():
            scoped = str(key or "").strip()
            if scoped:
                scoped_keys.add(scoped)

    if len(scoped_keys) == 1:
        return next(iter(scoped_keys))

    user_id_keys = sorted(k for k in scoped_keys if k.startswith("usr_"))
    if len(user_id_keys) == 1:
        return user_id_keys[0]

    return ""


def _prune_user_from_scoped_sections(profile: dict, user_key: str) -> None:
    if not user_key:
        return

    lookup = user_key.strip()
    lookup_lower = lookup.lower()
    for section_key in USER_SCOPED_PROFILE_MAP_KEYS:
        section = profile.get(section_key, {})
        if not isinstance(section, dict):
            continue

        matched_keys = []
        for key in section.keys():
            raw_key = str(key or "").strip()
            if not raw_key:
                continue
            if raw_key == lookup or raw_key.lower() == lookup_lower:
                matched_keys.append(key)

        for matched in matched_keys:
            section.pop(matched, None)


def _prune_legacy_spotify_token_file(user_key: str) -> bool:
    # Legacy file: older builds may keep Spotify tokens in a standalone JSON map.
    # We only remove the current user's token row and keep all others.
    if not user_key or not LEGACY_SPOTIFY_TOKENS_PATH.exists():
        return True

    try:
        payload = json.loads(LEGACY_SPOTIFY_TOKENS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(payload, dict):
        return False

    changed = False
    if user_key in payload:
        payload.pop(user_key, None)
        changed = True
    else:
        lookup = user_key.lower()
        for key in list(payload.keys()):
            if str(key).strip().lower() == lookup:
                payload.pop(key, None)
                changed = True

    if changed:
        LEGACY_SPOTIFY_TOKENS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def delete_profile(profile: dict | None = None, user_key: str = "") -> bool:
    # Privacy delete is user-scoped:
    # 1) Remove personal fields from this local profile.
    # 2) Remove this user's rows from user-keyed profile sections.
    # 3) Do NOT delete shared/global databases (e.g. subscription_db.json).
    source_profile = profile if isinstance(profile, dict) else load_profile()
    working = dict(source_profile) if isinstance(source_profile, dict) else {}
    resolved_user_key = _resolve_current_user_key(working, preferred_key=user_key)

    try:
        for key in USER_OWNED_PROFILE_KEYS:
            working.pop(key, None)

        _prune_user_from_scoped_sections(working, resolved_user_key)
        save_profile(working)

        # Legacy cleanup is best-effort and scoped to this user key only.
        _prune_legacy_spotify_token_file(resolved_user_key)
        return True
    except Exception:
        return False
