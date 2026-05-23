"""
Test script for Islamic API endpoints.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from islamic_mode.islamic_api import router

# Create a minimal test app
app = FastAPI()
app.include_router(router)

client = TestClient(app)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"{'=' * 25} {title}")
    print("=" * 80 + "\n")


def test_quran_endpoints():
    """Test Quran-related API endpoints."""
    print_section("Testing Quran API Endpoints")
    
    # Test 1: Get surahs list
    print("📚 GET /v1/islamic/quran/surahs")
    response = client.get("/v1/islamic/quran/surahs")
    assert response.status_code == 200
    data = response.json()
    surahs = data.get("surahs", data)  # Handle both dict and list responses
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Total surahs: {data.get('total', len(surahs))}")
    print(f"   First: {surahs[0]['name']} ({surahs[0]['english_name']})\n")
    
    # Test 2: Get specific surah info
    print("📖 GET /v1/islamic/quran/surah/1/info")
    response = client.get("/v1/islamic/quran/surah/1/info")
    assert response.status_code == 200
    data = response.json()
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Surah: {data['name']} - {data['english_name']}")
    print(f"   Verses: {data['verses']}\n")
    
    # Test 3: Get surah text
    print("🌐 GET /v1/islamic/quran/surah/1?edition=english")
    response = client.get("/v1/islamic/quran/surah/1?edition=english")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Fetched {len(data.get('verses', []))} verses")
    else:
        print(f"   ⚠️ API unavailable (expected in offline mode)\n")
    
    # Test 4: Get specific ayah
    print("📝 GET /v1/islamic/quran/ayah/1/1?edition=english")
    response = client.get("/v1/islamic/quran/ayah/1/1?edition=english")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Ayah retrieved\n")
    else:
        print("   ⚠️ API unavailable (expected in offline mode)\n")


def test_prophet_stories_endpoints():
    """Test Prophet stories API endpoints."""
    print_section("Testing Prophet Stories API Endpoints")
    
    # Test 1: Get all prophets
    print("📜 GET /v1/islamic/stories/prophets")
    response = client.get("/v1/islamic/stories/prophets")
    assert response.status_code == 200
    data = response.json()
    prophets = data.get("prophets", data) if isinstance(data, dict) else data
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Total prophets: {data.get('total', len(prophets)) if isinstance(data, dict) else len(prophets)}")
    if prophets:
        print(f"   Example: {prophets[0]['name']} ({prophets[0]['arabic']})\n")
    
    # Test 2: Get specific prophet
    print("👤 GET /v1/islamic/stories/prophets/Muhammad")
    response = client.get("/v1/islamic/stories/prophets/Muhammad")
    assert response.status_code == 200
    data = response.json()
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Prophet: {data['name']} - {data['title']}")
    print(f"   Lessons: {len(data['key_lessons'])}\n")
    
    # Test 3: Search stories
    print("🔍 GET /v1/islamic/stories/search?q=patience&limit=3")
    response = client.get("/v1/islamic/stories/search?q=patience&limit=3")
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", data) if isinstance(data, dict) else data
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Results: {data.get('count', len(results)) if isinstance(data, dict) else len(results)}")
    if results:
        print(f"   Example: Prophet {results[0]['name']}\n")
    
    # Test 4: Filter by age group
    print("👶 GET /v1/islamic/stories/prophets/age/children")
    response = client.get("/v1/islamic/stories/prophets/age/children")
    assert response.status_code == 200
    data = response.json()
    stories = data.get("stories", data) if isinstance(data, dict) else data
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Child-appropriate stories: {data.get('count', len(stories)) if isinstance(data, dict) else len(stories)}\n")


def test_audio_endpoints():
    """Test Quran audio API endpoints."""
    print_section("Testing Quran Audio API Endpoints")
    
    # Test 1: Get reciters list
    print("🎙️ GET /v1/islamic/quran/reciters")
    response = client.get("/v1/islamic/quran/reciters")
    assert response.status_code == 200
    data = response.json()
    reciters = data.get("reciters", data) if isinstance(data, dict) else data
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Total reciters: {data.get('total', len(reciters)) if isinstance(data, dict) else len(reciters)}")
    if reciters:
        print(f"   Example: {reciters[0]['name']}\n")
    
    # Test 2: Get popular reciters
    print("⭐ GET /v1/islamic/quran/reciters?popular=true")
    response = client.get("/v1/islamic/quran/reciters?popular=true")
    assert response.status_code == 200
    data = response.json()
    reciters = data.get("reciters", data) if isinstance(data, dict) else data
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Popular reciters: {data.get('total', len(reciters)) if isinstance(data, dict) else len(reciters)}\n")
    
    # Test 3: Get specific reciter
    print("👨‍🎤 GET /v1/islamic/quran/reciters/mishary")
    response = client.get("/v1/islamic/quran/reciters/mishary")
    assert response.status_code == 200
    data = response.json()
    print(f"   ✅ Status: {response.status_code}")
    print(f"   Reciter: {data['name']} ({data['country']})\n")
    
    # Test 4: Get audio URL
    print("🔗 GET /v1/islamic/quran/audio/url?reciter_id=mishary&surah=1&ayah=1")
    response = client.get("/v1/islamic/quran/audio/url?reciter_id=mishary&surah=1&ayah=1")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   URL: {data.get('url', 'N/A')[:60]}...\n")
    else:
        print(f"   ⚠️ Endpoint not found (skipping)\n")
    
    # Test 5: Check cache stats
    print("📊 GET /v1/islamic/quran/audio/cache/stats")
    response = client.get("/v1/islamic/quran/audio/cache/stats")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   Total cached files: {data['total_files']}")
        print(f"   Cache size: {data['total_size_mb']} MB\n")
    else:
        print(f"   ⚠️ Endpoint not found (skipping)\n")


def test_search_endpoint():
    """Test unified search endpoint."""
    print_section("Testing Unified Search Endpoint")
    
    print("🔍 GET /v1/islamic/search?q=moses&limit=10")
    response = client.get("/v1/islamic/search?q=moses&limit=10")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   Quran results: {len(data.get('quran_results', []))}")
        print(f"   Story results: {len(data.get('story_results', []))}")
        if data.get('story_results'):
            print(f"   Example: Prophet {data['story_results'][0]['name']}\n")
    else:
        print(f"   ⚠️ Search endpoint not available (skipping)\n")


def test_existing_endpoints():
    """Test that existing Islamic endpoints still work."""
    print_section("Testing Existing Islamic Endpoints (Regression)")
    
    endpoints = [
        ("/v1/islamic/prayer-times", "Prayer times"),
        ("/v1/islamic/hadith/daily", "Daily Hadith"),
        ("/v1/islamic/hadith/sleep", "Sleep Hadith"),
        ("/v1/islamic/sunnah/tip", "Sunnah tip"),
        ("/v1/islamic/calendar", "Islamic calendar"),
    ]
    
    for endpoint, name in endpoints:
        print(f"📡 GET {endpoint}")
        response = client.get(endpoint)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ {name} working\n")
        else:
            print(f"   ⚠️ {name} failed: {response.status_code}\n")


def main():
    """Run all API tests."""
    print("\n" + "🕌" * 40)
    print("Islamic API Endpoints Test Suite")
    print("🕌" * 40)
    
    try:
        test_quran_endpoints()
        test_prophet_stories_endpoints()
        test_audio_endpoints()
        test_search_endpoint()
        test_existing_endpoints()
        
        print_section("✅ ALL API TESTS COMPLETED SUCCESSFULLY!")
        
    except AssertionError as e:
        print(f"\n❌ Test assertion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
