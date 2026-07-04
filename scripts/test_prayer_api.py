"""Test script for prayer times API with geolocation support."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from islamic_mode.prayer_times import PrayerTimesService
from islamic_mode.geolocation import GeolocationService


def test_geolocation():
    print("=" * 60)
    print("Testing Geolocation Service")
    print("=" * 60)

    geo = GeolocationService()
    location = geo.get_location_from_ip()

    if location:
        print("✅ Auto-detected location:")
        print(f"   City: {location['city']}")
        print(f"   Country: {location['country']}")
        print(f"   Coordinates: ({location['latitude']}, {location['longitude']})")
        print(f"   Timezone: {location['timezone']}")
        print(f"   Source: {location['source']}")
    else:
        print("❌ Failed to detect location")

    print()


def test_prayer_times_manual():
    print("=" * 60)
    print("Testing Prayer Times (Manual Location)")
    print("=" * 60)

    service = PrayerTimesService(city="Mecca", country="Saudi Arabia", method=4)

    location = service.get_current_location()
    print(f"Location: {location['city']}, {location['country']}")
    print(f"Method: {location['method']}")
    print(f"Auto-detect: {location['auto_detect']}")
    print()

    prayers = service.get_today_prayers()
    print("Prayer Times:")
    for prayer, time in prayers.items():
        print(f"  {prayer}: {time}")

    print()

    next_prayer = service.get_next_prayer()
    print(f"Next Prayer: {next_prayer['name']} at {next_prayer['time']}")
    print(f"Minutes until: {next_prayer['minutes_until']}")

    print()


def test_prayer_times_coordinates():
    print("=" * 60)
    print("Testing Prayer Times (GPS Coordinates)")
    print("=" * 60)

    service = PrayerTimesService(latitude=21.4225, longitude=39.8262, method=4)

    location = service.get_current_location()
    print(f"Coordinates: ({location['latitude']}, {location['longitude']})")
    print(f"Using coordinates: {location['using_coordinates']}")
    print()

    prayers = service.get_today_prayers()
    print("Prayer Times:")
    for prayer, time in prayers.items():
        print(f"  {prayer}: {time}")

    print()


def test_prayer_times_auto():
    print("=" * 60)
    print("Testing Prayer Times (Auto-Detection)")
    print("=" * 60)

    service = PrayerTimesService(auto_detect_location=True)

    location = service.get_current_location()
    print(f"Auto-detected: {location['auto_detect']}")
    print(f"Location: {location['city']}, {location['country']}")
    if location.get("latitude") and location.get("longitude"):
        print(f"Coordinates: ({location['latitude']}, {location['longitude']})")
    print()

    prayers = service.get_today_prayers()
    print("Prayer Times:")
    for prayer, time in prayers.items():
        print(f"  {prayer}: {time}")

    print()


def test_location_update():
    print("=" * 60)
    print("Testing Dynamic Location Update")
    print("=" * 60)

    service = PrayerTimesService(city="Kuwait City", country="Kuwait")

    print("Initial location:")
    location = service.get_current_location()
    print(f"  {location['city']}, {location['country']}")

    prayers_before = service.get_today_prayers()
    print(f"  Fajr: {prayers_before.get('Fajr')}")
    print()

    print("Updating to Dubai...")
    service.update_location(city="Dubai", country="United Arab Emirates")

    location = service.get_current_location()
    print(f"  {location['city']}, {location['country']}")

    prayers_after = service.get_today_prayers()
    print(f"  Fajr: {prayers_after.get('Fajr')}")
    print()

    if prayers_before.get("Fajr") != prayers_after.get("Fajr"):
        print("✅ Prayer times updated successfully!")
    else:
        print("⚠️ Prayer times may be the same (normal if times are similar)")

    print()


def test_detailed_bundle():
    print("=" * 60)
    print("Testing Detailed Prayer Bundle")
    print("=" * 60)

    service = PrayerTimesService()
    bundle = service.get_today_prayer_bundle()

    print("Prayers:")
    for prayer, time in bundle["prayers"].items():
        print(f"  {prayer}: {time}")

    print()
    print("Location Info:")
    for key, value in bundle["location"].items():
        print(f"  {key}: {value}")

    print()


if __name__ == "__main__":
    print("\n🕌 Prayer Times API Test Suite\n")

    try:
        test_geolocation()
        test_prayer_times_manual()
        test_prayer_times_coordinates()
        test_location_update()
        test_detailed_bundle()

        # Only test auto if you want to trigger geolocation
        user_input = input("Test auto-detection? (may be slow) [y/N]: ")
        if user_input.lower() == "y":
            test_prayer_times_auto()

        print("\n✅ All tests completed!\n")

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
