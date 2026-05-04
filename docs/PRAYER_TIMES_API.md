# Prayer Times API - Location-Based Prayer Times

## Overview

The Smart Bed now supports **automatic location-based prayer times** using IP geolocation. Prayer times will automatically adjust according to the user's location without manual configuration.

## Features

✅ **Automatic Location Detection** - Uses IP-based geolocation to detect user's city and coordinates  
✅ **Manual Location Override** - Can manually set city/country or precise GPS coordinates  
✅ **Dynamic Location Updates** - Change location on-the-fly via API  
✅ **Fallback to Defaults** - Uses configured defaults if auto-detection fails  
✅ **Cache Support** - Caches prayer times to work offline  
✅ **Multiple Calculation Methods** - Support for various Islamic calculation methods

---

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Location for prayer times (use either city/country OR latitude/longitude)
ISLAMIC_PRAYER_CITY=Kuwait City
ISLAMIC_PRAYER_COUNTRY=Kuwait
ISLAMIC_PRAYER_LATITUDE=
ISLAMIC_PRAYER_LONGITUDE=

# Calculation method: 1=MWL, 2=ISNA, 3=Egypt, 4=Makkah, 5=Karachi, 8=Kuwait, etc.
ISLAMIC_PRAYER_METHOD=8

# Auto-detect location from IP (requires internet)
ISLAMIC_PRAYER_AUTO_LOCATION=0

# Timeout and cache settings
ISLAMIC_PRAYER_TIMEOUT_SECONDS=12
ISLAMIC_PRAYER_CACHE_PATH=runtime_data/prayer_times_cache.json
```

### Calculation Methods

| Method | Name | Regions |
|--------|------|---------|
| 1 | Muslim World League | Most of the world |
| 2 | Islamic Society of North America (ISNA) | USA, Canada |
| 3 | Egyptian General Authority | Egypt |
| 4 | Umm Al-Qura University | Saudi Arabia, Gulf |
| 5 | University of Islamic Sciences, Karachi | Pakistan |
| 8 | Kuwait | Kuwait, Gulf |
| 9 | Qatar | Qatar |
| 11 | Majlis Ugama Islam Singapura | Singapore |
| 12 | Union des Organisations Islamiques de France | France |

---

## API Endpoints

### 1. Get Prayer Times (Simple)

**GET** `/v1/islamic/prayer-times`

Returns today's prayer times for the configured location.

**Response:**
```json
{
  "Fajr": "04:30",
  "Dhuhr": "11:45",
  "Asr": "15:15",
  "Maghrib": "18:20",
  "Isha": "19:50"
}
```

### 2. Get Prayer Times (Detailed)

**GET** `/v1/islamic/prayer-times/detailed`

Returns prayer times with location metadata and next prayer info.

**Response:**
```json
{
  "prayers": {
    "Fajr": "04:30",
    "Dhuhr": "11:45",
    "Asr": "15:15",
    "Maghrib": "18:20",
    "Isha": "19:50"
  },
  "location": {
    "city": "Kuwait City",
    "country": "Kuwait",
    "latitude": 29.3759,
    "longitude": 47.9774,
    "timezone": "Asia/Kuwait",
    "method": "Kuwait",
    "mode": "coordinates"
  },
  "next_prayer": {
    "name": "Asr",
    "time": "15:15",
    "minutes_until": 45
  }
}
```

### 3. Get Next Prayer

**GET** `/v1/islamic/next-prayer`

Returns the next upcoming prayer.

**Response:**
```json
{
  "name": "Asr",
  "time": "15:15",
  "minutes_until": 45
}
```

### 4. Get Current Location

**GET** `/v1/islamic/location`

Returns current location settings.

**Response:**
```json
{
  "city": "Kuwait City",
  "country": "Kuwait",
  "latitude": 29.3759,
  "longitude": 47.9774,
  "method": 8,
  "auto_detect": false,
  "using_coordinates": true
}
```

### 5. Update Location

**POST** `/v1/islamic/location/update`

Update prayer times location dynamically.

**Query Parameters:**
- `city` (optional) - City name
- `country` (optional) - Country name
- `latitude` (optional) - GPS latitude
- `longitude` (optional) - GPS longitude

**Example Request:**
```bash
curl -X POST "http://localhost:8000/v1/islamic/location/update?city=Riyadh&country=Saudi+Arabia"
```

**Response:**
```json
{
  "success": true,
  "message": "Prayer times location updated",
  "location": {
    "city": "Riyadh",
    "country": "Saudi Arabia",
    "latitude": null,
    "longitude": null,
    "method": 8,
    "auto_detect": false,
    "using_coordinates": false
  }
}
```

### 6. Refresh Auto-Location

**POST** `/v1/islamic/location/refresh`

Re-detect location using IP geolocation (only works if `ISLAMIC_PRAYER_AUTO_LOCATION=1`).

**Response:**
```json
{
  "success": true,
  "message": "Location refreshed",
  "location": {
    "city": "Dubai",
    "country": "United Arab Emirates",
    "latitude": 25.2048,
    "longitude": 55.2708,
    "method": 8,
    "auto_detect": true,
    "using_coordinates": true
  }
}
```

---

## Usage Examples

### 1. Enable Auto-Location Detection

Set in `.env`:
```bash
ISLAMIC_PRAYER_AUTO_LOCATION=1
```

The system will automatically detect the user's location when the service starts.

### 2. Use Manual City/Country

Set in `.env`:
```bash
ISLAMIC_PRAYER_AUTO_LOCATION=0
ISLAMIC_PRAYER_CITY=Dubai
ISLAMIC_PRAYER_COUNTRY=United Arab Emirates
```

### 3. Use GPS Coordinates (Most Accurate)

Set in `.env`:
```bash
ISLAMIC_PRAYER_AUTO_LOCATION=0
ISLAMIC_PRAYER_LATITUDE=25.2048
ISLAMIC_PRAYER_LONGITUDE=55.2708
```

### 4. Mobile App Integration

**Get prayer times for user's current GPS location:**

```dart
// In Flutter mobile app
final position = await Geolocator.getCurrentPosition();

final response = await dio.post(
  '/v1/islamic/location/update',
  queryParameters: {
    'latitude': position.latitude,
    'longitude': position.longitude,
  },
);

final prayerTimes = await dio.get('/v1/islamic/prayer-times/detailed');
```

---

## Geolocation Service

The system uses two free IP geolocation APIs with automatic fallback:

1. **ip-api.com** (Primary)
2. **ipapi.co** (Fallback)

Both services provide:
- City name
- Country name
- GPS coordinates (latitude/longitude)
- Timezone

**No API key required** for basic usage.

---

## Prayer Times API Provider

Uses **Aladhan Prayer Times API** (https://aladhan.com/prayer-times-api)

**Features:**
- Free and open-source
- Multiple calculation methods
- Supports city/country and GPS coordinates
- Returns accurate prayer times based on Islamic calculations

---

## Offline Support

Prayer times are cached in `runtime_data/prayer_times_cache.json`.

If the API request fails:
1. System tries to use cached prayer times
2. Cache is updated on every successful API call
3. Works offline as long as cache exists

---

## Voice Commands (Future)

Planned voice integration:
- "What time is Fajr?"
- "When is the next prayer?"
- "Update my location to Mecca"
- "What's my current prayer location?"

---

## Testing

### Test Auto-Detection
```bash
# In .env
ISLAMIC_PRAYER_AUTO_LOCATION=1

# Start server and check logs
python -m uvicorn web_server:app --reload

# Should see:
# INFO: Auto-detecting location for prayer times...
# INFO: Auto-detected location: Dubai, United Arab Emirates (25.2048, 55.2708)
```

### Test Manual Location
```bash
curl http://localhost:8000/v1/islamic/prayer-times/detailed
```

### Test Location Update
```bash
curl -X POST "http://localhost:8000/v1/islamic/location/update?city=Mecca&country=Saudi+Arabia"
curl http://localhost:8000/v1/islamic/prayer-times
```

---

## Migration from Old System

**Before:** Hard-coded city in code
```python
prayer_service = PrayerTimesService(city="Kuwait City", country="Kuwait")
```

**After:** Automatic from config
```python
prayer_service = PrayerTimesService()  # Uses config automatically
```

All existing code continues to work. The service is backward-compatible.

---

## Security Notes

- IP geolocation is **anonymous** and doesn't expose personal data
- No authentication required for public prayer times
- Location data is stored locally, not sent to external servers (except Aladhan API)
- Cache files are stored in `runtime_data/` directory

---

## Troubleshooting

### Prayer times not updating

**Check:**
1. Internet connection (required for API calls)
2. `ISLAMIC_PRAYER_AUTO_LOCATION` setting in `.env`
3. Cache file permissions in `runtime_data/`

**Solution:**
```bash
# Clear cache and restart
rm runtime_data/prayer_times_cache.json
python main.py
```

### Auto-detection fails

**Fallback:** System uses configured defaults from `.env`

**Check logs:**
```
INFO: Auto-detecting location for prayer times...
WARNING: All geolocation services failed to detect location
INFO: Using default location: Kuwait City, Kuwait
```

### Wrong calculation method

Update `ISLAMIC_PRAYER_METHOD` in `.env` to match your region (see table above).

---

## Future Enhancements

- [ ] Support for custom prayer time adjustments (±minutes)
- [ ] Qibla direction based on location
- [ ] Prayer time notifications/alerts
- [ ] Historical prayer times lookup
- [ ] Multiple location profiles (home/work/travel)
- [ ] Automatic timezone detection
- [ ] Prayer time widgets for mobile app

---

**Last Updated:** April 18, 2026  
**API Version:** v1  
**Status:** ✅ Production Ready
