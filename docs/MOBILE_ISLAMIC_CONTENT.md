# Mobile App Islamic Content Integration Guide

Guide for integrating the Islamic Content Library into the Flutter mobile app.

## Table of Contents

- [Overview](#overview)
- [API Integration](#api-integration)
- [Recommended Screen Structure](#recommended-screen-structure)
- [State Management](#state-management)
- [UI Components](#ui-components)
- [Implementation Steps](#implementation-steps)

---

## Overview

The mobile app needs to integrate three new Islamic content types:

1. **Quran Browser** - Read and search Quran with translations
2. **Prophet Stories** - Browse and read prophet stories
3. **Audio Player** - Listen to Quran recitations

These will extend the existing Islamic mode features (prayer times, hadith, sunnah tips).

---

## API Integration

### Create API Service Classes

**File**: `mobile_app/lib/src/services/islamic_content_service.dart`

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

class IslamicContentService {
  final String baseUrl;
  
  IslamicContentService(this.baseUrl);
  
  // Quran Methods
  Future<List<Surah>> getSurahs() async {
    final response = await http.get(
      Uri.parse('$baseUrl/v1/islamic/quran/surahs')
    );
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return (data['surahs'] as List)
          .map((s) => Surah.fromJson(s))
          .toList();
    }
    throw Exception('Failed to load surahs');
  }
  
  Future<SurahText> getSurahText(int surahNumber, String edition) async {
    final response = await http.get(
      Uri.parse('$baseUrl/v1/islamic/quran/surah/$surahNumber?edition=$edition')
    );
    
    if (response.statusCode == 200) {
      return SurahText.fromJson(json.decode(response.body));
    }
    throw Exception('Failed to load surah text');
  }
  
  // Prophet Stories Methods
  Future<List<ProphetSummary>> getProphets() async {
    final response = await http.get(
      Uri.parse('$baseUrl/v1/islamic/stories/prophets')
    );
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return (data['prophets'] as List)
          .map((p) => ProphetSummary.fromJson(p))
          .toList();
    }
    throw Exception('Failed to load prophets');
  }
  
  Future<ProphetStory> getProphetStory(String name) async {
    final response = await http.get(
      Uri.parse('$baseUrl/v1/islamic/stories/prophets/$name')
    );
    
    if (response.statusCode == 200) {
      return ProphetStory.fromJson(json.decode(response.body));
    }
    throw Exception('Failed to load prophet story');
  }
  
  // Audio Methods
  Future<List<Reciter>> getReciters({bool popularOnly = false}) async {
    final url = popularOnly 
        ? '$baseUrl/v1/islamic/quran/reciters?popular=true'
        : '$baseUrl/v1/islamic/quran/reciters';
        
    final response = await http.get(Uri.parse(url));
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return (data['reciters'] as List)
          .map((r) => Reciter.fromJson(r))
          .toList();
    }
    throw Exception('Failed to load reciters');
  }
  
  String getAudioUrl(String reciterId, int surah, int ayah) {
    final surahStr = surah.toString().padLeft(3, '0');
    final ayahStr = ayah.toString().padLeft(3, '0');
    // Note: This constructs the URL directly. You can also call the API endpoint.
    return 'https://everyayah.com/data/Alafasy_128kbps/$surahStr$ayahStr.mp3';
  }
  
  // Search
  Future<SearchResults> searchAll(String query, {int limit = 20}) async {
    final response = await http.get(
      Uri.parse('$baseUrl/v1/islamic/search?q=$query&limit=$limit')
    );
    
    if (response.statusCode == 200) {
      return SearchResults.fromJson(json.decode(response.body));
    }
    throw Exception('Failed to search');
  }
}
```

---

## Recommended Screen Structure

### 1. Islamic Library Screen (Main Hub)

**File**: `mobile_app/lib/src/ui/screens/islamic_library_screen.dart`

```dart
import 'package:flutter/material.dart';

class IslamicLibraryScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Islamic Library'),
        actions: [
          IconButton(
            icon: Icon(Icons.search),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => IslamicSearchScreen()),
            ),
          ),
        ],
      ),
      body: GridView.count(
        crossAxisCount: 2,
        padding: EdgeInsets.all(16),
        mainAxisSpacing: 16,
        crossAxisSpacing: 16,
        children: [
          _LibraryCard(
            title: 'Holy Quran',
            icon: Icons.book,
            color: Colors.green,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => QuranBrowserScreen()),
            ),
          ),
          _LibraryCard(
            title: 'Prophet Stories',
            icon: Icons.person,
            color: Colors.blue,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => ProphetStoriesScreen()),
            ),
          ),
          _LibraryCard(
            title: 'Audio Recitations',
            icon: Icons.headphones,
            color: Colors.purple,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => QuranAudioScreen()),
            ),
          ),
          _LibraryCard(
            title: 'Daily Hadith',
            icon: Icons.format_quote,
            color: Colors.orange,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => IslamicScreen()), // Existing screen
            ),
          ),
        ],
      ),
    );
  }
}

class _LibraryCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  
  const _LibraryCard({
    required this.title,
    required this.icon,
    required this.color,
    required this.onTap,
  });
  
  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 4,
      child: InkWell(
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 64, color: color),
            SizedBox(height: 16),
            Text(
              title,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
```

---

### 2. Quran Browser Screen

**File**: `mobile_app/lib/src/ui/screens/quran_browser_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class QuranBrowserScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final surahsAsync = ref.watch(surahsProvider);
    
    return Scaffold(
      appBar: AppBar(
        title: Text('Holy Quran'),
        actions: [
          PopupMenuButton<String>(
            onSelected: (edition) {
              ref.read(selectedEditionProvider.notifier).state = edition;
            },
            itemBuilder: (context) => [
              PopupMenuItem(value: 'arabic', child: Text('Arabic')),
              PopupMenuItem(value: 'english', child: Text('English')),
              PopupMenuItem(value: 'transliteration', child: Text('Transliteration')),
            ],
          ),
        ],
      ),
      body: surahsAsync.when(
        data: (surahs) => ListView.builder(
          itemCount: surahs.length,
          itemBuilder: (context, index) {
            final surah = surahs[index];
            return ListTile(
              leading: CircleAvatar(
                child: Text('${surah.number}'),
              ),
              title: Text(surah.englishName),
              subtitle: Text('${surah.name} • ${surah.verses} verses • ${surah.revelationType}'),
              trailing: Icon(Icons.arrow_forward_ios, size: 16),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => SurahReaderScreen(surahNumber: surah.number),
                ),
              ),
            );
          },
        ),
        loading: () => Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(child: Text('Error: $err')),
      ),
    );
  }
}
```

---

### 3. Surah Reader Screen

**File**: `mobile_app/lib/src/ui/screens/surah_reader_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SurahReaderScreen extends ConsumerWidget {
  final int surahNumber;
  
  const SurahReaderScreen({required this.surahNumber});
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final surahTextAsync = ref.watch(surahTextProvider(surahNumber));
    final selectedEdition = ref.watch(selectedEditionProvider);
    
    return Scaffold(
      appBar: AppBar(
        title: surahTextAsync.maybeWhen(
          data: (surah) => Text(surah.englishName),
          orElse: () => Text('Loading...'),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.bookmark_border),
            onPressed: () {
              // TODO: Add bookmark functionality
            },
          ),
        ],
      ),
      body: surahTextAsync.when(
        data: (surah) => ListView.builder(
          padding: EdgeInsets.all(16),
          itemCount: surah.verses.length,
          itemBuilder: (context, index) {
            final verse = surah.verses[index];
            return Card(
              margin: EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 16,
                          child: Text(
                            '${verse.numberInSurah}',
                            style: TextStyle(fontSize: 12),
                          ),
                        ),
                        Spacer(),
                        IconButton(
                          icon: Icon(Icons.volume_up, size: 20),
                          onPressed: () {
                            // TODO: Play audio for this ayah
                          },
                        ),
                      ],
                    ),
                    SizedBox(height: 12),
                    Text(
                      verse.text,
                      style: TextStyle(
                        fontSize: selectedEdition == 'arabic' ? 24 : 18,
                        height: 1.8,
                      ),
                      textAlign: selectedEdition == 'arabic' 
                          ? TextAlign.right 
                          : TextAlign.left,
                    ),
                  ],
                ),
              ),
            );
          },
        ),
        loading: () => Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(child: Text('Error: $err')),
      ),
    );
  }
}
```

---

### 4. Prophet Stories Screen

**File**: `mobile_app/lib/src/ui/screens/prophet_stories_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class ProphetStoriesScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prophetsAsync = ref.watch(prophetsProvider);
    
    return Scaffold(
      appBar: AppBar(
        title: Text('Prophet Stories'),
      ),
      body: prophetsAsync.when(
        data: (prophets) => ListView.builder(
          itemCount: prophets.length,
          itemBuilder: (context, index) {
            final prophet = prophets[index];
            return Card(
              margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: ListTile(
                contentPadding: EdgeInsets.all(16),
                title: Text(
                  prophet.name,
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(height: 4),
                    Text(
                      prophet.arabic,
                      style: TextStyle(fontSize: 20, color: Colors.green),
                    ),
                    SizedBox(height: 8),
                    Text(prophet.title),
                  ],
                ),
                trailing: Icon(Icons.arrow_forward_ios),
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => ProphetStoryDetailScreen(
                      prophetName: prophet.name,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
        loading: () => Center(child: CircularProgressIndicator()),
        error: (err, stack) => Center(child: Text('Error: $err')),
      ),
    );
  }
}
```

---

### 5. Audio Player Screen

**File**: `mobile_app/lib/src/ui/screens/quran_audio_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:audioplayers/audioplayers.dart';

class QuranAudioScreen extends ConsumerStatefulWidget {
  @override
  _QuranAudioScreenState createState() => _QuranAudioScreenState();
}

class _QuranAudioScreenState extends ConsumerState<QuranAudioScreen> {
  final AudioPlayer _audioPlayer = AudioPlayer();
  bool _isPlaying = false;
  
  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }
  
  Future<void> _playAudio(String url) async {
    if (_isPlaying) {
      await _audioPlayer.stop();
      setState(() => _isPlaying = false);
    } else {
      await _audioPlayer.play(UrlSource(url));
      setState(() => _isPlaying = true);
    }
  }
  
  @override
  Widget build(BuildContext context) {
    final recitersAsync = ref.watch(recitersProvider);
    final selectedReciter = ref.watch(selectedReciterProvider);
    
    return Scaffold(
      appBar: AppBar(
        title: Text('Quran Recitations'),
      ),
      body: Column(
        children: [
          // Reciter Selection
          Container(
            padding: EdgeInsets.all(16),
            child: recitersAsync.when(
              data: (reciters) => DropdownButton<String>(
                value: selectedReciter,
                isExpanded: true,
                items: reciters.map((reciter) {
                  return DropdownMenuItem(
                    value: reciter.id,
                    child: Text('${reciter.name} (${reciter.country})'),
                  );
                }).toList(),
                onChanged: (value) {
                  if (value != null) {
                    ref.read(selectedReciterProvider.notifier).state = value;
                  }
                },
              ),
              loading: () => CircularProgressIndicator(),
              error: (_, __) => Text('Failed to load reciters'),
            ),
          ),
          
          Divider(),
          
          // Surah List for Audio
          Expanded(
            child: ListView.builder(
              itemCount: 114,
              itemBuilder: (context, index) {
                final surahNumber = index + 1;
                return ListTile(
                  leading: Icon(Icons.play_circle_outline),
                  title: Text('Surah $surahNumber'),
                  onTap: () {
                    // Navigate to ayah selection or start playing
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => SurahAudioPlayerScreen(
                          surahNumber: surahNumber,
                          reciterId: selectedReciter,
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
```

---

## State Management

### Riverpod Providers

**File**: `mobile_app/lib/src/providers/islamic_content_providers.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';

// Service Provider
final islamicContentServiceProvider = Provider<IslamicContentService>((ref) {
  return IslamicContentService('http://your-api-url');
});

// Quran Providers
final surahsProvider = FutureProvider<List<Surah>>((ref) async {
  final service = ref.read(islamicContentServiceProvider);
  return service.getSurahs();
});

final selectedEditionProvider = StateProvider<String>((ref) => 'english');

final surahTextProvider = FutureProvider.family<SurahText, int>((ref, surahNumber) async {
  final service = ref.read(islamicContentServiceProvider);
  final edition = ref.watch(selectedEditionProvider);
  return service.getSurahText(surahNumber, edition);
});

// Prophet Stories Providers
final prophetsProvider = FutureProvider<List<ProphetSummary>>((ref) async {
  final service = ref.read(islamicContentServiceProvider);
  return service.getProphets();
});

final prophetStoryProvider = FutureProvider.family<ProphetStory, String>((ref, name) async {
  final service = ref.read(islamicContentServiceProvider);
  return service.getProphetStory(name);
});

// Audio Providers
final recitersProvider = FutureProvider<List<Reciter>>((ref) async {
  final service = ref.read(islamicContentServiceProvider);
  return service.getReciters(popularOnly: false);
});

final selectedReciterProvider = StateProvider<String>((ref) => 'mishary');

// Search Provider
final searchQueryProvider = StateProvider<String>((ref) => '');

final searchResultsProvider = FutureProvider<SearchResults>((ref) async {
  final query = ref.watch(searchQueryProvider);
  if (query.isEmpty) return SearchResults.empty();
  
  final service = ref.read(islamicContentServiceProvider);
  return service.searchAll(query);
});
```

---

## Data Models

**File**: `mobile_app/lib/src/models/islamic_content_models.dart`

```dart
class Surah {
  final int number;
  final String name;
  final String englishName;
  final int verses;
  final String revelationType;
  
  Surah({
    required this.number,
    required this.name,
    required this.englishName,
    required this.verses,
    required this.revelationType,
  });
  
  factory Surah.fromJson(Map<String, dynamic> json) => Surah(
    number: json['number'],
    name: json['name'],
    englishName: json['english_name'],
    verses: json['verses'],
    revelationType: json['revelation_type'],
  );
}

class SurahText {
  final int number;
  final String name;
  final String englishName;
  final List<Verse> verses;
  
  SurahText({
    required this.number,
    required this.name,
    required this.englishName,
    required this.verses,
  });
  
  factory SurahText.fromJson(Map<String, dynamic> json) => SurahText(
    number: json['number'],
    name: json['name'],
    englishName: json['englishName'] ?? json['english_name'] ?? '',
    verses: (json['verses'] as List)
        .map((v) => Verse.fromJson(v))
        .toList(),
  );
}

class Verse {
  final int number;
  final String text;
  final int numberInSurah;
  
  Verse({
    required this.number,
    required this.text,
    required this.numberInSurah,
  });
  
  factory Verse.fromJson(Map<String, dynamic> json) => Verse(
    number: json['number'],
    text: json['text'],
    numberInSurah: json['numberInSurah'],
  );
}

class ProphetSummary {
  final String name;
  final String arabic;
  final String title;
  
  ProphetSummary({
    required this.name,
    required this.arabic,
    required this.title,
  });
  
  factory ProphetSummary.fromJson(Map<String, dynamic> json) => ProphetSummary(
    name: json['name'],
    arabic: json['arabic'],
    title: json['title'],
  );
}

class ProphetStory {
  final String name;
  final String arabic;
  final String title;
  final String storySummary;
  final List<String> keyLessons;
  final List<String> mentionsInQuran;
  
  ProphetStory({
    required this.name,
    required this.arabic,
    required this.title,
    required this.storySummary,
    required this.keyLessons,
    required this.mentionsInQuran,
  });
  
  factory ProphetStory.fromJson(Map<String, dynamic> json) => ProphetStory(
    name: json['name'],
    arabic: json['arabic'],
    title: json['title'],
    storySummary: json['story_summary'],
    keyLessons: List<String>.from(json['key_lessons']),
    mentionsInQuran: List<String>.from(json['mentions_in_quran']),
  );
}

class Reciter {
  final String id;
  final String name;
  final String arabicName;
  final String country;
  final String audioQuality;
  final bool popular;
  
  Reciter({
    required this.id,
    required this.name,
    required this.arabicName,
    required this.country,
    required this.audioQuality,
    required this.popular,
  });
  
  factory Reciter.fromJson(Map<String, dynamic> json) => Reciter(
    id: json['id'],
    name: json['name'],
    arabicName: json['arabic_name'],
    country: json['country'],
    audioQuality: json['audio_quality'],
    popular: json['popular'] ?? false,
  );
}

class SearchResults {
  final String query;
  final List<dynamic> quranResults;
  final List<dynamic> storyResults;
  
  SearchResults({
    required this.query,
    required this.quranResults,
    required this.storyResults,
  });
  
  factory SearchResults.fromJson(Map<String, dynamic> json) => SearchResults(
    query: json['query'],
    quranResults: json['quran_results'] ?? [],
    storyResults: json['story_results'] ?? [],
  );
  
  factory SearchResults.empty() => SearchResults(
    query: '',
    quranResults: [],
    storyResults: [],
  );
}
```

---

## Implementation Steps

### Phase 1: Setup (Week 1)
1. ✅ Add required dependencies to `pubspec.yaml`:
   ```yaml
   dependencies:
     http: ^1.1.0
     audioplayers: ^5.0.0
     flutter_riverpod: ^2.4.0 # Already installed
   ```

2. ✅ Create service layer files
3. ✅ Create data model files
4. ✅ Create provider files

### Phase 2: Quran Feature (Week 2)
1. ✅ Implement `QuranBrowserScreen`
2. ✅ Implement `SurahReaderScreen`
3. ✅ Add bookmarking functionality
4. ✅ Add text size controls
5. ✅ Test with real API

### Phase 3: Prophet Stories (Week 3)
1. ✅ Implement `ProphetStoriesScreen`
2. ✅ Implement `ProphetStoryDetailScreen`
3. ✅ Add age filter UI
4. ✅ Add favorites/bookmarks
5. ✅ Test with real API

### Phase 4: Audio Player (Week 4)
1. ✅ Implement `QuranAudioScreen`
2. ✅ Implement `SurahAudioPlayerScreen`
3. ✅ Add playlist controls
4. ✅ Add download management
5. ✅ Test audio playback

### Phase 5: Polish (Week 5)
1. ✅ Add unified search screen
2. ✅ Add loading states & error handling
3. ✅ Add offline mode support
4. ✅ Performance optimization
5. ✅ UI/UX refinement

---

## Navigation Integration

Update the main app navigation to include Islamic Library:

**File**: `mobile_app/lib/src/ui/screens/home_screen.dart`

```dart
// Add to existing home screen navigation
ListTile(
  leading: Icon(Icons.mosque),
  title: Text('Islamic Library'),
  onTap: () => Navigator.push(
    context,
    MaterialPageRoute(builder: (_) => IslamicLibraryScreen()),
  ),
),
```

---

## Offline Support

Implement caching for offline use:

```dart
// Use shared_preferences or hive for local storage
final cachedSurahsProvider = FutureProvider<List<Surah>>((ref) async {
  final prefs = await SharedPreferences.getInstance();
  final cached = prefs.getString('cached_surahs');
  
  if (cached != null) {
    // Return cached data
    return parseCachedSurahs(cached);
  }
  
  // Fetch from API and cache
  final service = ref.read(islamicContentServiceProvider);
  final surahs = await service.getSurahs();
  prefs.setString('cached_surahs', jsonEncode(surahs));
  return surahs;
});
```

---

## Next Steps

1. Start with Phase 1 setup
2. Implement screens incrementally
3. Test each feature thoroughly
4. Gather user feedback
5. Iterate and improve

For questions, refer to:
- API Documentation: `docs/ISLAMIC_CONTENT_API.md`
- Backend Implementation: `islamic_mode/` directory
- Existing Islamic screen: `mobile_app/lib/src/ui/screens/islamic_screen.dart`
