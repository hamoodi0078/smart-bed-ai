# Islamic Content Library API Documentation

Comprehensive API documentation for the Islamic content features including Quran text, Prophet stories, and audio recitations.

## Table of Contents

- [Overview](#overview)
- [Quran Text Endpoints](#quran-text-endpoints)
- [Prophet Stories Endpoints](#prophet-stories-endpoints)
- [Quran Audio Endpoints](#quran-audio-endpoints)
- [Unified Search](#unified-search)
- [Data Models](#data-models)

---

## Overview

The Islamic Content Library provides access to:
- **Quran Text**: All 114 surahs with multiple editions (Arabic, English, Transliteration)
- **Prophet Stories**: Detailed narratives of 25 prophets mentioned in the Quran
- **Audio Recitations**: High-quality Quran recitations from 10+ renowned reciters
- **Search**: Unified search across all content types

**Base URL**: `/v1/islamic`

---

## Quran Text Endpoints

### Get All Surahs

Get a list of all 114 surahs with metadata.

**Endpoint**: `GET /quran/surahs`

**Response**:
```json
{
  "surahs": [
    {
      "number": 1,
      "name": "Al-Fatihah",
      "english_name": "The Opening",
      "verses": 7,
      "revelation_type": "Meccan"
    }
  ],
  "total": 114
}
```

---

### Get Surah Info

Get metadata for a specific surah.

**Endpoint**: `GET /quran/surah/{surah_number}/info`

**Parameters**:
- `surah_number` (path, required): Surah number (1-114)

**Example**: `GET /quran/surah/1/info`

**Response**:
```json
{
  "number": 1,
  "name": "Al-Fatihah",
  "english_name": "The Opening",
  "verses": 7,
  "revelation_type": "Meccan"
}
```

---

### Get Surah Text

Get full surah with all verses.

**Endpoint**: `GET /quran/surah/{surah_number}`

**Parameters**:
- `surah_number` (path, required): Surah number (1-114)
- `edition` (query, optional): Edition type - `arabic`, `english`, `transliteration` (default: `arabic`)

**Example**: `GET /quran/surah/1?edition=english`

**Response**:
```json
{
  "number": 1,
  "name": "سُورَةُ ٱلْفَاتِحَةِ",
  "englishName": "Al-Faatiha",
  "verses": [
    {
      "number": 1,
      "text": "In the name of Allah, the Entirely Merciful, the Especially Merciful.",
      "numberInSurah": 1
    }
  ]
}
```

---

### Get Specific Ayah

Get a specific verse from the Quran.

**Endpoint**: `GET /quran/ayah/{surah_number}/{ayah_number}`

**Parameters**:
- `surah_number` (path, required): Surah number (1-114)
- `ayah_number` (path, required): Ayah number within the surah
- `edition` (query, optional): Edition type (default: `arabic`)

**Example**: `GET /quran/ayah/1/1?edition=english`

**Response**:
```json
{
  "number": 1,
  "text": "In the name of Allah, the Entirely Merciful, the Especially Merciful.",
  "surah": {
    "number": 1,
    "name": "Al-Fatihah"
  }
}
```

---

### Get Multi-Edition Ayah

Get the same ayah in multiple editions simultaneously.

**Endpoint**: `GET /quran/ayah/{surah_number}/{ayah_number}/multi`

**Parameters**:
- `surah_number` (path, required): Surah number (1-114)
- `ayah_number` (path, required): Ayah number
- `editions` (query, optional): Comma-separated edition codes (default: `arabic,english`)

**Example**: `GET /quran/ayah/1/1/multi?editions=arabic,english,transliteration`

**Response**:
```json
{
  "surah": 1,
  "ayah": 1,
  "editions": {
    "arabic": "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",
    "english": "In the name of Allah, the Entirely Merciful...",
    "transliteration": "Bismillahir Rahmanir Raheem"
  }
}
```

---

### Search Quran

Search for keywords in Quran text.

**Endpoint**: `GET /quran/search`

**Parameters**:
- `q` (query, required): Search query
- `edition` (query, optional): Edition to search (default: `english`)
- `limit` (query, optional): Maximum results (default: 20)

**Example**: `GET /quran/search?q=mercy&edition=english&limit=5`

**Response**:
```json
{
  "query": "mercy",
  "results": [
    {
      "surah": 1,
      "verse": 1,
      "text": "In the name of Allah, the Entirely Merciful...",
      "surah_name": "Al-Fatihah"
    }
  ],
  "count": 5
}
```

---

## Prophet Stories Endpoints

### Get All Prophets

Get list of all 25 prophets.

**Endpoint**: `GET /stories/prophets`

**Response**:
```json
{
  "prophets": [
    {
      "name": "Adam",
      "arabic": "آدم",
      "title": "Father of Mankind"
    }
  ],
  "total": 25
}
```

---

### Get Prophet Story

Get detailed story of a specific prophet.

**Endpoint**: `GET /stories/prophets/{prophet_name}`

**Parameters**:
- `prophet_name` (path, required): Prophet name (e.g., `Muhammad`, `Moses`, `Jesus`)

**Example**: `GET /stories/prophets/Muhammad`

**Response**:
```json
{
  "name": "Muhammad",
  "arabic": "محمد",
  "title": "The Final Messenger - Peace be upon him",
  "story_summary": "Prophet Muhammad ﷺ was born in Makkah in 570 CE...",
  "key_lessons": [
    "The importance of truthfulness and integrity",
    "Patience in the face of persecution"
  ],
  "mentions_in_quran": [
    "Al-Ahzab 33:40",
    "Muhammad 47:2"
  ],
  "age_appropriate": "all"
}
```

---

### Get Stories by Age Group

Filter prophet stories by age appropriateness.

**Endpoint**: `GET /stories/prophets/age/{age_group}`

**Parameters**:
- `age_group` (path, required): `all`, `children`, or `teen_adult`

**Example**: `GET /stories/prophets/age/children`

**Response**:
```json
{
  "age_group": "children",
  "stories": [
    {
      "name": "Noah",
      "arabic": "نوح",
      "title": "The Patient Preacher",
      "story_summary": "..."
    }
  ],
  "count": 24
}
```

---

### Search Prophet Stories

Search stories by keyword.

**Endpoint**: `GET /stories/search`

**Parameters**:
- `q` (query, required): Search query

**Example**: `GET /stories/search?q=patience`

**Response**:
```json
{
  "query": "patience",
  "results": [
    {
      "name": "Job",
      "arabic": "أيوب",
      "title": "The Patient One",
      "story_summary": "..."
    }
  ],
  "count": 14
}
```

---

## Quran Audio Endpoints

### Get All Reciters

Get list of available Quran reciters.

**Endpoint**: `GET /quran/reciters`

**Parameters**:
- `popular` (query, optional): Filter for popular reciters (`true`/`false`)

**Example**: `GET /quran/reciters?popular=true`

**Response**:
```json
{
  "reciters": [
    {
      "id": "mishary",
      "name": "Mishary Rashid Alafasy",
      "arabic_name": "مشاري بن راشد العفاسي",
      "country": "Kuwait",
      "audio_quality": "128kbps",
      "popular": true
    }
  ],
  "total": 10
}
```

---

### Get Reciter Info

Get detailed information about a specific reciter.

**Endpoint**: `GET /quran/reciters/{reciter_id}`

**Parameters**:
- `reciter_id` (path, required): Reciter ID (e.g., `mishary`, `sudais`)

**Example**: `GET /quran/reciters/mishary`

**Response**:
```json
{
  "id": "mishary",
  "name": "Mishary Rashid Alafasy",
  "arabic_name": "مشاري بن راشد العفاسي",
  "language": "Arabic",
  "style": "Warsh",
  "audio_quality": "128kbps",
  "country": "Kuwait",
  "base_url": "https://everyayah.com/data/Alafasy_128kbps/",
  "format": "mp3",
  "popular": true,
  "description": "One of the most popular reciters, known for his beautiful melodious voice."
}
```

---

### Get Audio URL

Get the audio URL for a specific ayah.

**Endpoint**: `GET /quran/audio/{reciter_id}/surah/{surah_number}/ayah/{ayah_number}/url`

**Parameters**:
- `reciter_id` (path, required): Reciter ID
- `surah_number` (path, required): Surah number (1-114)
- `ayah_number` (path, required): Ayah number

**Example**: `GET /quran/audio/mishary/surah/1/ayah/1/url`

**Response**:
```json
{
  "reciter_id": "mishary",
  "surah": 1,
  "ayah": 1,
  "url": "https://everyayah.com/data/Alafasy_128kbps/001001.mp3",
  "format": "mp3"
}
```

---

### Download Ayah Audio

Download and cache a single ayah audio file.

**Endpoint**: `POST /quran/audio/download/ayah`

**Parameters**:
- `reciter_id` (query, required): Reciter ID
- `surah` (query, required): Surah number
- `ayah` (query, required): Ayah number

**Example**: `POST /quran/audio/download/ayah?reciter_id=mishary&surah=1&ayah=1`

**Response**:
```json
{
  "success": true,
  "message": "Downloaded successfully",
  "reciter_id": "mishary",
  "surah": 1,
  "ayah": 1,
  "cached": true
}
```

---

### Download Surah Audio

Download all ayahs in a surah.

**Endpoint**: `POST /quran/audio/download/surah`

**Parameters**:
- `reciter_id` (query, required): Reciter ID
- `surah` (query, required): Surah number
- `total_ayahs` (query, required): Number of ayahs in the surah

**Example**: `POST /quran/audio/download/surah?reciter_id=mishary&surah=1&total_ayahs=7`

**Response**:
```json
{
  "reciter_id": "mishary",
  "surah": 1,
  "total_ayahs": 7,
  "downloaded": 7,
  "failed": 0,
  "already_cached": 0
}
```

---

### Get Cache Statistics

Get statistics about cached audio files.

**Endpoint**: `GET /quran/audio/cache/stats`

**Parameters**:
- `reciter_id` (query, optional): Filter by specific reciter

**Example**: `GET /quran/audio/cache/stats?reciter_id=mishary`

**Response**:
```json
{
  "cache_dir": "/path/to/cache",
  "total_files": 42,
  "total_size_mb": 5.2,
  "reciter": "mishary"
}
```

---

### Clear Audio Cache

Delete cached audio files.

**Endpoint**: `DELETE /quran/audio/cache`

**Parameters**:
- `reciter_id` (query, optional): Clear specific reciter's cache only

**Example**: `DELETE /quran/audio/cache?reciter_id=mishary`

**Response**:
```json
{
  "success": true,
  "deleted": 42,
  "failed": 0,
  "reciter": "mishary"
}
```

---

## Unified Search

Search across all Islamic content types.

**Endpoint**: `GET /search`

**Parameters**:
- `q` (query, required): Search query
- `limit` (query, optional): Maximum results per category (default: 20)

**Example**: `GET /search?q=moses&limit=10`

**Response**:
```json
{
  "query": "moses",
  "quran_results": [
    {
      "surah": 2,
      "verse": 51,
      "text": "And [recall] when We appointed for Moses forty nights...",
      "surah_name": "Al-Baqarah"
    }
  ],
  "story_results": [
    {
      "name": "Moses",
      "arabic": "موسى",
      "title": "The Speaker to Allah",
      "story_summary": "..."
    }
  ],
  "total_results": 15
}
```

---

## Data Models

### Surah Info
```typescript
{
  number: number;           // 1-114
  name: string;            // Arabic name
  english_name: string;    // English name
  verses: number;          // Total verses
  revelation_type: string; // "Meccan" or "Medinan"
}
```

### Prophet Story
```typescript
{
  name: string;              // Prophet name
  arabic: string;           // Arabic name
  title: string;            // Title/description
  story_summary: string;    // Full story
  key_lessons: string[];    // Array of lessons
  mentions_in_quran: string[]; // Quran references
  age_appropriate: string;  // "all", "children", "teen_adult"
}
```

### Reciter
```typescript
{
  id: string;              // Unique ID
  name: string;           // Full name
  arabic_name: string;    // Arabic name
  country: string;        // Country
  audio_quality: string;  // e.g., "128kbps"
  base_url: string;       // Base audio URL
  format: string;         // Audio format (mp3)
  popular: boolean;       // Popular reciter flag
  description: string;    // Description
}
```

---

## Available Reciters

| ID | Name | Country | Quality |
|----|------|---------|---------|
| `mishary` | Mishary Rashid Alafasy | Kuwait | 128kbps |
| `sudais` | Abdurrahman As-Sudais | Saudi Arabia | 128kbps |
| `husary` | Mahmoud Khalil Al-Husary | Egypt | 128kbps |
| `minshawi` | Mohamed Siddiq Al-Minshawi | Egypt | 128kbps |
| `ghamadi` | Saad Al-Ghamadi | Saudi Arabia | 128kbps |
| `ajmi` | Ahmed ibn Ali Al-Ajmi | Saudi Arabia | 128kbps |
| `shuraim` | Saud Ash-Shuraim | Saudi Arabia | 128kbps |
| `basfar` | Abdullah Basfar | Saudi Arabia | 32kbps |
| `jibreen` | Ibrahim Al-Jibreen | Saudi Arabia | 32kbps |
| `rifai` | Hani Ar-Rifai | Saudi Arabia | 192kbps |

---

## Edition Codes

| Code | Description |
|------|-------------|
| `arabic` | Simple Arabic text with diacritics |
| `english` | Sahih International English translation |
| `transliteration` | English transliteration |

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "error": "Error description",
  "surah_number": 999
}
```

**Common HTTP Status Codes**:
- `200`: Success
- `404`: Resource not found
- `500`: Server error

---

## Rate Limiting

- Default rate limit: 60 requests per minute
- Can be configured via environment variables

---

## Caching

- **Quran Text**: 30-day cache
- **Audio Files**: Permanent until manually cleared
- Cache directory: `runtime_data/islamic_content/`

---

## Notes

1. All Quran audio is sourced from [EveryAyah.com](https://everyayah.com)
2. Quran text API uses [AlQuran Cloud](https://alquran.cloud/api)
3. Prophet stories are curated and static
4. Search is performed locally on cached data when available
5. Audio playback requires `pygame` library (optional)

---

## Examples

### Complete Workflow: Download & Play Quran

```bash
# 1. Get surah info
GET /v1/islamic/quran/surah/1/info

# 2. Download audio for entire surah
POST /v1/islamic/quran/audio/download/surah?reciter_id=mishary&surah=1&total_ayahs=7

# 3. Get audio URL for specific ayah
GET /v1/islamic/quran/audio/mishary/surah/1/ayah/1/url

# 4. Check cache stats
GET /v1/islamic/quran/audio/cache/stats?reciter_id=mishary
```

### Search Across All Content

```bash
# Search for "patience"
GET /v1/islamic/search?q=patience&limit=10

# Returns matching Quran verses and Prophet stories
```

---

## Support

For issues or questions:
- Check existing hadith service documentation: `docs/HADITH_SERVICE.md`
- Review prayer times documentation
- Contact: support@yourapp.com
