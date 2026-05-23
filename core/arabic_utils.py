"""Arabic text utilities powered by pyarabic + arabic-reshaper.

Public API
----------
is_arabic_text(text)                    -> bool       — True when text contains Arabic characters
strip_diacritics(text)                  -> str        — remove harakat / tashkeel
normalize_arabic(text)                  -> str        — normalize hamza + ligature + strip tatweel
clean_arabic(text)                      -> str        — full pipeline: normalize → strip diacritics
arabic_word_count(text)                 -> int        — count Arabic words in mixed text
tokenize_arabic(text)                   -> list[str]  — split Arabic text into word tokens
tts_arabic(text)                        -> str        — prepare Arabic text for TTS
detect_language(text)                   -> str        — 'ar' or 'en'
reshape_arabic(text)                    -> str        — reshape for PIL/image rendering
render_arabic_on_image(img, text, xy, font, fill) -> None  — draw Arabic onto a PIL image
"""

from __future__ import annotations

import re
import unicodedata

try:
    import pyarabic.araby as _araby
    _PYARABIC_AVAILABLE = True
except ImportError:
    _araby = None  # type: ignore[assignment]
    _PYARABIC_AVAILABLE = False

try:
    import arabic_reshaper as _arabic_reshaper
    _RESHAPER_AVAILABLE = True
except ImportError:
    _arabic_reshaper = None  # type: ignore[assignment]
    _RESHAPER_AVAILABLE = False

# Arabic Unicode block range
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def is_arabic_text(text: str) -> bool:
    """Return True when *text* contains at least one Arabic character."""
    return bool(_ARABIC_RE.search(str(text or "")))


def strip_diacritics(text: str) -> str:
    """Remove Arabic diacritical marks (harakat / tashkeel) from *text*.

    These are the short vowel marks (fatha, damma, kasra, sukun, shadda, …)
    that appear in Quran and classical texts but are absent in modern writing.
    Stripping them makes text cleaner for TTS and display.
    """
    if not text:
        return text
    if _PYARABIC_AVAILABLE:
        return _araby.strip_tashkeel(str(text))
    # Fallback: strip via Unicode category (Mn = non-spacing mark)
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text: hamza forms → canonical form, strip tatweel (ـ), normalize lam-alef ligatures."""
    if not text:
        return text
    if _PYARABIC_AVAILABLE:
        text = _araby.strip_tatweel(str(text))
        text = _araby.normalize_hamza(text)
        text = _araby.normalize_ligature(text)
        return text
    # Minimal fallback: remove tatweel
    return str(text).replace("ـ", "")


def clean_arabic(text: str) -> str:
    """Full pipeline: normalize → strip diacritics → collapse whitespace."""
    if not text:
        return text
    text = normalize_arabic(text)
    text = strip_diacritics(text)
    return re.sub(r"\s+", " ", text).strip()


def arabic_word_count(text: str) -> int:
    """Count Arabic words in *text* (works on mixed-language strings)."""
    if not text:
        return 0
    if _PYARABIC_AVAILABLE:
        tokens = _araby.tokenize(str(text))
        return sum(1 for t in tokens if _araby.is_arabicword(t))
    # Fallback: count space-separated tokens that contain Arabic characters
    return sum(1 for token in str(text).split() if _ARABIC_RE.search(token))


def tokenize_arabic(text: str) -> list[str]:
    """Return a list of Arabic word tokens from *text*."""
    if not text:
        return []
    if _PYARABIC_AVAILABLE:
        return [t for t in _araby.tokenize(str(text)) if t.strip()]
    return [t for t in str(text).split() if _ARABIC_RE.search(t)]


def tts_arabic(text: str) -> str:
    """Prepare Arabic text for text-to-speech.

    Strips diacritics and normalizes the text so TTS engines produce
    natural output without stumbling on harakat.
    """
    if not text:
        return text
    text = clean_arabic(text)
    return text


def detect_language(text: str) -> str:
    """Return 'ar' when text is predominantly Arabic, else 'en'.

    Used by STTManager to auto-select the transcription language.
    """
    if not text:
        return "en"
    total_words = len(str(text).split())
    if total_words == 0:
        return "en"
    arabic_words = arabic_word_count(text)
    return "ar" if (arabic_words / total_words) >= 0.5 else "en"


# ---------------------------------------------------------------------------
# Rendering helpers (arabic-reshaper)
# ---------------------------------------------------------------------------

def reshape_arabic(text: str) -> str:
    """Reshape Arabic text for correct rendering in PIL/image contexts.

    Arabic letters change shape depending on their position in a word
    (initial, medial, final, isolated).  Most image-drawing backends
    (PIL ImageDraw, matplotlib) treat every character independently and
    therefore render Arabic broken and unjoined.  arabic-reshaper pre-joins
    the characters so the backend just draws ready-made glyphs.

    Returns the reshaped string (reversed for LTR canvas rendering).
    Falls back to the original text when arabic-reshaper is not installed.
    """
    if not text:
        return text
    if not _RESHAPER_AVAILABLE:
        return str(text)
    try:
        reshaped = _arabic_reshaper.reshape(str(text))
        # Reverse word order for LTR canvases (PIL draws left-to-right).
        # Each word is already reshaped; reversing restores RTL visual order.
        words = reshaped.split()
        return " ".join(reversed(words))
    except Exception:
        return str(text)


def render_arabic_on_image(
    image: "Any",
    text: str,
    xy: tuple[int, int],
    font: "Any" = None,
    fill: "Any" = (0, 0, 0),
) -> None:
    """Draw Arabic *text* onto a PIL *image* at position *xy*.

    Handles the full pipeline automatically:
      clean_arabic → reshape_arabic → ImageDraw.text()

    Args:
        image: A ``PIL.Image.Image`` instance.
        text:  Arabic (or mixed) string to render.
        xy:    (x, y) top-left anchor on the image.
        font:  ``PIL.ImageFont`` instance; uses default if None.
        fill:  Colour passed to ``ImageDraw.text()`` (default black).
    """
    try:
        from PIL import ImageDraw
    except ImportError:
        return

    prepared = reshape_arabic(clean_arabic(str(text)))
    draw = ImageDraw.Draw(image)
    if font is not None:
        draw.text(xy, prepared, font=font, fill=fill)
    else:
        draw.text(xy, prepared, fill=fill)