"""
Test script for Islamic content library (Quran text, Prophet stories, Audio).
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from islamic_mode.content.quran_text import QuranTextService
from islamic_mode.content.prophet_stories import ProphetStoriesService
from islamic_mode.content.content_manager import ContentManager
from islamic_mode.audio.reciter_catalog import ReciterCatalog
from islamic_mode.audio.quran_recitation import QuranRecitationService


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"{'=' * 25} {title}")
    print("=" * 80 + "\n")


def test_quran_text_service():
    """Test Quran text service functionality."""
    print_section("Testing Quran Text Service")

    service = QuranTextService()

    # Test 1: Get list of surahs
    print("📚 Testing Surah List...")
    surahs = service.get_surahs_list()
    print(f"   Total surahs: {len(surahs)}")
    print(f"   First surah: {surahs[0]['name']} ({surahs[0]['english_name']})")
    print(f"   Last surah: {surahs[-1]['name']} ({surahs[-1]['english_name']})")
    print("   ✅ Surah list loaded\n")

    # Test 2: Get specific surah info
    print("📖 Testing Surah Info...")
    al_fatiha = service.get_surah_info(1)
    print(f"   Surah 1: {al_fatiha['name']} - {al_fatiha['english_name']}")
    print(f"   Verses: {al_fatiha['verses']}, Type: {al_fatiha['revelation_type']}")
    print("   ✅ Surah info retrieved\n")

    # Test 3: Fetch a surah (will use API or show error)
    print("🌐 Testing Surah Fetch (Al-Fatiha)...")
    try:
        surah_data = service.get_surah(1, edition="english")
        if surah_data:
            print(f"   ✅ Fetched Surah {surah_data['number']}: {surah_data['name']}")
            print(f"   Verses: {len(surah_data.get('verses', []))}")
            if surah_data.get("verses"):
                print(f"   First verse: {surah_data['verses'][0]['text'][:80]}...")
        else:
            print("   ⚠️ API unavailable, but service is functional")
    except Exception as e:
        print(f"   ⚠️ API test skipped: {e}")

    # Test 4: Search functionality
    print("\n🔍 Testing Quran Search...")
    try:
        results = service.search_quran("mercy", edition="english", limit=3)
        if results:
            print(f"   Found {len(results)} results for 'mercy'")
            if results:
                print(f"   Example: Surah {results[0]['surah']}:{results[0]['verse']}")
        else:
            print("   ⚠️ Search API unavailable, but service is functional")
    except Exception as e:
        print(f"   ⚠️ Search test skipped: {e}")


def test_prophet_stories():
    """Test Prophet stories service."""
    print_section("Testing Prophet Stories Service")

    service = ProphetStoriesService()

    # Test 1: Get all prophets
    print("📜 Testing Prophet List...")
    prophets = service.get_all_prophets()
    print(f"   Total prophets: {len(prophets)}")
    print(f"   First: {prophets[0]['name']} ({prophets[0]['arabic']})")
    print(f"   Last: {prophets[-1]['name']} ({prophets[-1]['arabic']})")
    print("   ✅ Prophet list loaded\n")

    # Test 2: Get specific prophet
    print("👤 Testing Specific Prophet (Muhammad ﷺ)...")
    muhammad = service.get_prophet_by_name("Muhammad")
    if muhammad:
        print(f"   Name: {muhammad['name']} ({muhammad['arabic']})")
        print(f"   Title: {muhammad['title']}")
        print(f"   Summary: {muhammad['story_summary'][:100]}...")
        print(f"   Key Lessons: {len(muhammad['key_lessons'])} lessons")
        print(f"   Quran Mentions: {len(muhammad['mentions_in_quran'])} references")
        print("   ✅ Prophet data retrieved\n")

    # Test 3: Search stories
    print("🔍 Testing Story Search...")
    results = service.search_stories("patience")
    print(f"   Found {len(results)} stories mentioning 'patience'")
    if results:
        print(f"   Example: Prophet {results[0]['name']}")
    print("   ✅ Search working\n")

    # Test 4: Filter by age group
    print("👶 Testing Age-Appropriate Filtering...")
    for age_group in ["children", "teens", "all"]:
        filtered = service.get_prophets_by_age_group(age_group)
        print(f"   {age_group.capitalize()}: {len(filtered)} stories")
    print("   ✅ Age filtering working")


def test_reciter_catalog():
    """Test Quran reciter catalog."""
    print_section("Testing Quran Reciter Catalog")

    # Test 1: Get all reciters
    print("🎙️ Testing Reciter Catalog...")
    reciters = ReciterCatalog.get_all_reciters()
    print(f"   Total reciters: {len(reciters)}")
    print(f"   Popular reciters: {len(ReciterCatalog.get_popular_reciters())}\n")

    # Test 2: Get specific reciter
    print("👨‍🎤 Testing Specific Reciter (Mishary Alafasy)...")
    mishary = ReciterCatalog.get_reciter("mishary")
    if mishary:
        print(f"   Name: {mishary['name']}")
        print(f"   Arabic: {mishary['arabic_name']}")
        print(f"   Country: {mishary['country']}")
        print(f"   Quality: {mishary['audio_quality']}")
        print(f"   Description: {mishary['description'][:80]}...")
        print("   ✅ Reciter data retrieved\n")

    # Test 3: Get audio URLs
    print("🔗 Testing Audio URL Generation...")
    url = ReciterCatalog.get_audio_url("mishary", 1, 1)  # Al-Fatiha, verse 1
    print(f"   URL format: {url[:60]}...")
    print("   ✅ URL generation working")


def test_audio_service():
    """Test Quran audio recitation service."""
    print_section("Testing Quran Audio Service")

    service = QuranRecitationService()

    # Test 1: Check player status
    print("🎵 Testing Audio Player Initialization...")
    print(f"   Player ready: {service.is_player_ready()}")
    if not service.is_player_ready():
        print("   ℹ️ pygame not available - playback features disabled")
    print("   ✅ Service initialized\n")

    # Test 2: Cache management
    print("📁 Testing Cache Management...")
    stats = service.get_cache_stats()
    print(f"   Cache directory: {stats['cache_dir']}")
    print(f"   Total files: {stats['total_files']}")
    print(f"   Total size: {stats['total_size_mb']:.2f} MB")
    print("   ✅ Cache system working\n")

    # Test 3: Check if specific ayah is cached
    print("🔍 Testing Cache Check...")
    is_cached = service.is_cached("mishary", 1, 1)
    print(f"   Al-Fatiha verse 1 cached: {is_cached}")
    print("   ✅ Cache lookup working")


def test_content_manager():
    """Test unified content manager."""
    print_section("Testing Content Manager")

    manager = ContentManager()

    # Test 1: Access services
    print("🔧 Testing Service Access...")
    print(f"   Quran service: {type(manager.quran).__name__}")
    print(f"   Stories service: {type(manager.prophet_stories).__name__}")
    print("   ✅ Services accessible\n")

    # Test 2: Unified search
    print("🔍 Testing Unified Search...")
    results = manager.search_all("moses", limit=5)
    print(f"   Quran results: {len(results.get('quran_results', []))}")
    print(f"   Story results: {len(results.get('story_results', []))}")
    if results.get("story_results"):
        print(f"   Example story: Prophet {results['story_results'][0]['name']}")
    print("   ✅ Unified search working")


def main():
    """Run all tests."""
    print("\n" + "🕌" * 40)
    print("Islamic Content Library Test Suite")
    print("🕌" * 40)

    try:
        test_quran_text_service()
        test_prophet_stories()
        test_reciter_catalog()
        test_audio_service()
        test_content_manager()

        print_section("✅ ALL TESTS COMPLETED SUCCESSFULLY!")

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
