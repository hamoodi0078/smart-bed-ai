"""Test script for comprehensive hadith service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from islamic_mode.hadith_daily import HadithService
from islamic_mode.sunnah_tips import SunnahSleepTips


def test_daily_hadith():
    print("=" * 70)
    print("Testing Daily Hadith Service")
    print("=" * 70)

    service = HadithService()

    print("\n📖 Fetching daily hadith...")
    hadith = service.get_daily_hadith()

    print("\n✅ Hadith of the Day:")
    print(f"   {hadith.get('hadith', 'N/A')}")
    print(f"\n   Source: {hadith.get('source', 'N/A')}")
    if hadith.get("chapter"):
        print(f"   Chapter: {hadith['chapter']}")
    if hadith.get("narrator"):
        print(f"   Narrator: {hadith['narrator']}")
    if hadith.get("number"):
        print(f"   Hadith #: {hadith['number']}")
    print(f"   API Source: {hadith.get('api_source', 'unknown')}")

    if hadith.get("hadith_arabic"):
        print(f"\n   Arabic: {hadith['hadith_arabic'][:100]}...")

    print()


def test_cache():
    print("=" * 70)
    print("Testing Cache System")
    print("=" * 70)

    service = HadithService()
    cache_path = service._get_daily_cache_path()

    print(f"\n📁 Cache path: {cache_path}")
    print(f"   Cache exists: {cache_path.exists()}")

    if cache_path.exists():
        cached = service._read_cache(cache_path)
        if cached:
            print("   ✅ Cached hadith found")
            print(f"   Source: {cached.get('api_source', 'unknown')}")
        else:
            print("   ❌ Failed to read cache")
    else:
        print("   ℹ️ No cache yet (will be created on first fetch)")

    print()


def test_sleep_hadiths():
    print("=" * 70)
    print("Testing Sleep Hadiths (Weekly Rotation)")
    print("=" * 70)

    service = HadithService()

    print("\n🌙 Sleep-specific hadith:")
    sleep_hadith = service.get_sleep_hadith()
    print(f"   {sleep_hadith.get('hadith', 'N/A')}")
    print(f"   Source: {sleep_hadith.get('source', 'N/A')}")

    print()


def test_sunnah_tips():
    print("=" * 70)
    print("Testing Sunnah Sleep Tips")
    print("=" * 70)

    service = SunnahSleepTips()

    print(f"\n📊 Total tips available: {service.get_tips_count()}")

    print("\n🌟 Tip of the night:")
    tip = service.get_tip_of_night()
    print(f"   {tip}")

    print("\n🔀 Random tip:")
    random_tip = service.get_random_tip()
    print(f"   {random_tip}")

    print()


def test_sunnah_categories():
    print("=" * 70)
    print("Testing Sunnah Tips by Category")
    print("=" * 70)

    service = SunnahSleepTips()
    categories = ["posture", "quran", "dua", "timing", "spiritual"]

    for category in categories:
        tips = service.get_tip_by_category(category)
        print(f"\n{category.upper()} ({len(tips)} tips):")
        for i, tip in enumerate(tips[:2], 1):  # Show first 2
            print(f"   {i}. {tip[:60]}...")

    print()


def test_deterministic_selection():
    print("=" * 70)
    print("Testing Deterministic Selection")
    print("=" * 70)

    service = HadithService()

    print("\n🔍 Testing date-based book selection...")
    book, number = service._get_deterministic_book_and_number()
    print(f"   Selected: {book.upper()} #{number}")

    # Verify same call returns same result
    book2, number2 = service._get_deterministic_book_and_number()
    if book == book2 and number == number2:
        print("   ✅ Deterministic: Same date returns same selection")
    else:
        print("   ❌ Error: Results differ on same date!")

    print()


def test_api_sources():
    print("=" * 70)
    print("Testing API Source Fallback")
    print("=" * 70)

    service = HadithService()

    print("\n🌐 Available hadith books:")
    for key, slug in service.BOOKS.items():
        print(f"   - {key}: {slug}")

    print(f"\n📡 Primary API: {service.HADITH_API_BASE}")
    print(f"   Fallback API: {service.RANDOM_HADITH_API}")
    print("   Local fallback: 5 hadiths")

    print()


def test_full_integration():
    print("=" * 70)
    print("Full Integration Test")
    print("=" * 70)

    print("\n🚀 Simulating daily bedtime routine...")

    # Get daily hadith
    hadith_service = HadithService()
    hadith = hadith_service.get_daily_hadith()
    print("\n1. Daily Hadith:")
    print(f"   {hadith['hadith'][:80]}...")
    print(f"   — {hadith.get('source', 'Unknown')}")

    # Get sleep hadith
    sleep_hadith = hadith_service.get_sleep_hadith()
    print("\n2. Sleep Hadith:")
    print(f"   {sleep_hadith['hadith'][:80]}...")

    # Get sunnah tip
    sunnah_service = SunnahSleepTips()
    tip = sunnah_service.get_tip_of_night()
    print("\n3. Sunnah Tip:")
    print(f"   {tip[:80]}...")

    print("\n✅ All Islamic content loaded successfully!")
    print()


if __name__ == "__main__":
    print("\n🕌 Comprehensive Hadith Service Test Suite\n")

    try:
        test_cache()
        test_deterministic_selection()
        test_api_sources()
        test_daily_hadith()
        test_sleep_hadiths()
        test_sunnah_tips()
        test_sunnah_categories()
        test_full_integration()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print()

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
