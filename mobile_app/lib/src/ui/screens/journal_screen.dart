import 'package:flutter/material.dart';
import '../../core/journal_store.dart';
import '../theme.dart';

class SleepJournalScreen extends StatefulWidget {
  const SleepJournalScreen({super.key});

  @override
  State<SleepJournalScreen> createState() => _SleepJournalScreenState();
}

class _SleepJournalScreenState extends State<SleepJournalScreen> {
  List<_JournalEntry> _entries = <_JournalEntry>[];

  static final List<_JournalEntry> _seedEntries = <_JournalEntry>[
    _JournalEntry(
      date: DateTime(2026, 5, 4),
      mood: _Mood.great,
      sleepQuality: 4.5,
      hoursSlept: 7.5,
      notes: 'Felt amazing! Wind-down journey really helped. Woke up naturally before alarm.',
      tags: <String>['wind-down', 'natural wake'],
    ),
    _JournalEntry(
      date: DateTime(2026, 5, 3),
      mood: _Mood.okay,
      sleepQuality: 3.0,
      hoursSlept: 6.0,
      notes: 'Woke up several times during the night. Too much caffeine yesterday.',
      tags: <String>['restless', 'caffeine'],
    ),
    _JournalEntry(
      date: DateTime(2026, 5, 2),
      mood: _Mood.good,
      sleepQuality: 4.0,
      hoursSlept: 8.0,
      notes: 'Ocean waves sound helped a lot. Should use it more often.',
      tags: <String>['ocean waves', 'peaceful'],
    ),
  ];

  static Map<String, dynamic> _entryToMap(_JournalEntry e) => <String, dynamic>{
    'date': e.date.toIso8601String(),
    'mood': e.mood.name,
    'sleepQuality': e.sleepQuality,
    'hoursSlept': e.hoursSlept,
    'notes': e.notes,
    'tags': e.tags,
  };

  static _JournalEntry _entryFromMap(Map<String, dynamic> m) => _JournalEntry(
    date: DateTime.parse(m['date'] as String),
    mood: _Mood.values.firstWhere(
      (mo) => mo.name == m['mood'],
      orElse: () => _Mood.good,
    ),
    sleepQuality: (m['sleepQuality'] as num).toDouble(),
    hoursSlept: (m['hoursSlept'] as num).toDouble(),
    notes: m['notes'] as String,
    tags: List<String>.from(m['tags'] as List<dynamic>),
  );

  @override
  void initState() {
    super.initState();
    _loadEntries();
  }

  Future<void> _loadEntries() async {
    final stored = JournalStore.readAll();
    if (stored.isEmpty) {
      for (final e in _seedEntries) {
        await JournalStore.add(_entryToMap(e));
      }
      if (mounted) {
        setState(() => _entries = List<_JournalEntry>.of(_seedEntries));
      }
    } else {
      if (mounted) {
        setState(() => _entries = stored.map(_entryFromMap).toList());
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      appBar: AppBar(
        backgroundColor: SmartBedPalette.background,
        foregroundColor: Colors.white,
        elevation: 0,
        title: const Text(
          'Sleep Journal',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.filter_list_rounded),
            onPressed: _showFilterSheet,
          ),
        ],
      ),
      body: Column(
        children: <Widget>[
          _buildWeeklyInsight(),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _entries.length,
              itemBuilder: (context, index) {
                return _JournalCard(
                  entry: _entries[index],
                  onTap: () => _showEntryDetail(_entries[index]),
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _createNewEntry,
        backgroundColor: SmartBedPalette.accent,
        foregroundColor: SmartBedPalette.background,
        icon: const Icon(Icons.add_rounded),
        label: const Text(
          'New Entry',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
    );
  }

  Widget _buildWeeklyInsight() {
    final count = _entries.isEmpty ? 1 : _entries.length;
    final avgQuality = _entries.fold<double>(0, (sum, e) => sum + e.sleepQuality) / count;
    final avgHours = _entries.fold<double>(0, (sum, e) => sum + e.hoursSlept) / count;

    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            SmartBedPalette.secondaryAccent.withValues(alpha: 0.2),
            SmartBedPalette.accent.withValues(alpha: 0.1),
          ],
        ),
        border: Border.all(
          color: SmartBedPalette.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'This Week',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: <Widget>[
              Expanded(
                child: _buildInsightStat(
                  'Avg Quality',
                  '${avgQuality.toStringAsFixed(1)}/5',
                  Icons.star_rounded,
                  SmartBedPalette.gold,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildInsightStat(
                  'Avg Hours',
                  '${avgHours.toStringAsFixed(1)}h',
                  Icons.bedtime_rounded,
                  SmartBedPalette.accent,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildInsightStat(
                  'Entries',
                  '${_entries.length}',
                  Icons.edit_note_rounded,
                  SmartBedPalette.secondaryAccent,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInsightStat(String label, String value, IconData icon, Color color) {
    final theme = Theme.of(context);
    return Column(
      children: <Widget>[
        Icon(icon, color: color, size: 24),
        const SizedBox(height: 6),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(
            color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  void _createNewEntry() {
    Navigator.of(context).push<dynamic>(
      MaterialPageRoute<dynamic>(
        builder: (_) => const _JournalEntryEditor(),
      ),
    ).then((dynamic result) {
      if (result != null && result is _JournalEntry) {
        JournalStore.add(_entryToMap(result));
        if (!mounted) return;
        setState(() {
          _entries.insert(0, result);
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Journal entry saved!'),
            backgroundColor: SmartBedPalette.accent,
          ),
        );
      }
    });
  }

  void _showEntryDetail(_JournalEntry entry) {
    Navigator.of(context).push<dynamic>(
      MaterialPageRoute<dynamic>(
        builder: (_) => _JournalEntryDetail(entry: entry),
      ),
    );
  }

  void _showFilterSheet() {
    final theme = Theme.of(context);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: SmartBedPalette.surface(theme.brightness),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text(
              'Filter Entries',
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 20),
            ListTile(
              leading: const Icon(Icons.star_rounded, color: SmartBedPalette.gold),
              title: const Text('High Quality Only', style: TextStyle(color: Colors.white)),
              onTap: () => Navigator.pop(context),
            ),
            ListTile(
              leading: const Icon(Icons.mood_bad_rounded, color: SmartBedPalette.warmAccent),
              title: const Text('Poor Sleep Nights', style: TextStyle(color: Colors.white)),
              onTap: () => Navigator.pop(context),
            ),
            ListTile(
              leading: const Icon(Icons.tag_rounded, color: SmartBedPalette.accent),
              title: const Text('By Tags', style: TextStyle(color: Colors.white)),
              onTap: () => Navigator.pop(context),
            ),
          ],
        ),
      ),
    );
  }
}

class _JournalCard extends StatelessWidget {
  const _JournalCard({
    required this.entry,
    required this.onTap,
  });

  final _JournalEntry entry;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: entry.mood.color.withValues(alpha: 0.3),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: entry.mood.color.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        entry.mood.icon,
                        color: entry.mood.color,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            _formatDate(entry.date),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          Text(
                            entry.mood.label,
                            style: TextStyle(
                              color: entry.mood.color,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: <Widget>[
                        Row(
                          children: List<Widget>.generate(5, (index) {
                            return Icon(
                              index < entry.sleepQuality.round()
                                  ? Icons.star_rounded
                                  : Icons.star_border_rounded,
                              color: SmartBedPalette.gold,
                              size: 16,
                            );
                          }),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${entry.hoursSlept}h',
                          style: TextStyle(
                            color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  entry.notes,
                  style: TextStyle(
                    color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.8),
                    fontSize: 14,
                    height: 1.4,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (entry.tags.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: entry.tags.take(3).map((tag) {
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: SmartBedPalette.accent.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: SmartBedPalette.accent.withValues(alpha: 0.3),
                          ),
                        ),
                        child: Text(
                          tag,
                          style: TextStyle(
                            color: SmartBedPalette.accent.withValues(alpha: 0.9),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final compareDate = DateTime(date.year, date.month, date.day);
    
    final diff = today.difference(compareDate).inDays;
    
    if (diff == 0) return 'Today';
    if (diff == 1) return 'Yesterday';
    if (diff < 7) return '$diff days ago';
    
    return '${date.day}/${date.month}/${date.year}';
  }
}

class _JournalEntryEditor extends StatefulWidget {
  const _JournalEntryEditor();

  @override
  State<_JournalEntryEditor> createState() => _JournalEntryEditorState();
}

class _JournalEntryEditorState extends State<_JournalEntryEditor> {
  _Mood _selectedMood = _Mood.good;
  double _sleepQuality = 4.0;
  double _hoursSlept = 7.0;
  final _notesController = TextEditingController();
  final List<String> _selectedTags = <String>[];
  
  final List<String> _availableTags = <String>[
    'wind-down',
    'natural wake',
    'restless',
    'caffeine',
    'ocean waves',
    'peaceful',
    'prayer',
    'exercise',
    'stressed',
    'productive',
  ];

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      appBar: AppBar(
        backgroundColor: SmartBedPalette.background,
        foregroundColor: Colors.white,
        elevation: 0,
        title: const Text(
          'New Journal Entry',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: _saveEntry,
            child: const Text(
              'Save',
              style: TextStyle(
                color: SmartBedPalette.accent,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _buildSection('How do you feel?', _buildMoodSelector()),
            const SizedBox(height: 24),
            _buildSection('Sleep Quality', _buildQualitySlider()),
            const SizedBox(height: 24),
            _buildSection('Hours Slept', _buildHoursSlider()),
            const SizedBox(height: 24),
            _buildSection('Notes', _buildNotesField()),
            const SizedBox(height: 24),
            _buildSection('Tags', _buildTagSelector()),
          ],
        ),
      ),
    );
  }

  Widget _buildSection(String title, Widget child) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        child,
      ],
    );
  }

  Widget _buildMoodSelector() {
    final theme = Theme.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: _Mood.values.map((mood) {
        final isSelected = _selectedMood == mood;
        return GestureDetector(
          onTap: () => setState(() => _selectedMood = mood),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isSelected
                  ? mood.color.withValues(alpha: 0.2)
                  : SmartBedPalette.surface(theme.brightness),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected ? mood.color : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.2),
                width: isSelected ? 2 : 1,
              ),
            ),
            child: Column(
              children: <Widget>[
                Icon(
                  mood.icon,
                  color: isSelected ? mood.color : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.5),
                  size: 32,
                ),
                const SizedBox(height: 6),
                Text(
                  mood.label,
                  style: TextStyle(
                    color: isSelected ? mood.color : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildQualitySlider() {
    return Column(
      children: <Widget>[
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List<Widget>.generate(5, (index) {
            return Icon(
              index < _sleepQuality.round()
                  ? Icons.star_rounded
                  : Icons.star_border_rounded,
              color: SmartBedPalette.gold,
              size: 32,
            );
          }),
        ),
        Slider(
          value: _sleepQuality,
          min: 1,
          max: 5,
          divisions: 4,
          activeColor: SmartBedPalette.gold,
          label: '${_sleepQuality.toInt()}/5',
          onChanged: (value) => setState(() => _sleepQuality = value),
        ),
      ],
    );
  }

  Widget _buildHoursSlider() {
    return Column(
      children: <Widget>[
        Text(
          '${_hoursSlept.toStringAsFixed(1)} hours',
          style: const TextStyle(
            color: SmartBedPalette.accent,
            fontSize: 24,
            fontWeight: FontWeight.w700,
          ),
        ),
        Slider(
          value: _hoursSlept,
          min: 3,
          max: 12,
          divisions: 18,
          activeColor: SmartBedPalette.accent,
          onChanged: (value) => setState(() => _hoursSlept = value),
        ),
      ],
    );
  }

  Widget _buildNotesField() {
    final theme = Theme.of(context);
    return TextField(
      controller: _notesController,
      maxLines: 5,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        hintText: 'How was your sleep? Any dreams? What helped?',
        hintStyle: TextStyle(color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.5)),
        filled: true,
        fillColor: SmartBedPalette.surface(theme.brightness),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }

  Widget _buildTagSelector() {
    final theme = Theme.of(context);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: _availableTags.map((tag) {
        final isSelected = _selectedTags.contains(tag);
        return GestureDetector(
          onTap: () {
            setState(() {
              if (isSelected) {
                _selectedTags.remove(tag);
              } else {
                _selectedTags.add(tag);
              }
            });
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: isSelected
                  ? SmartBedPalette.accent.withValues(alpha: 0.2)
                  : SmartBedPalette.surface(theme.brightness),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: isSelected
                    ? SmartBedPalette.accent
                    : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.2),
              ),
            ),
            child: Text(
              tag,
              style: TextStyle(
                color: isSelected ? SmartBedPalette.accent : SmartBedPalette.body(theme.brightness),
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  void _saveEntry() {
    if (_notesController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please add some notes about your sleep'),
          backgroundColor: SmartBedPalette.warmAccent,
        ),
      );
      return;
    }

    final entry = _JournalEntry(
      date: DateTime.now(),
      mood: _selectedMood,
      sleepQuality: _sleepQuality,
      hoursSlept: _hoursSlept,
      notes: _notesController.text.trim(),
      tags: _selectedTags,
    );

    Navigator.pop(context, entry);
  }
}

class _JournalEntryDetail extends StatelessWidget {
  const _JournalEntryDetail({required this.entry});

  final _JournalEntry entry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      appBar: AppBar(
        backgroundColor: SmartBedPalette.background,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Text(
          _formatDate(entry.date),
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.edit_rounded),
            onPressed: () {},
          ),
          IconButton(
            icon: const Icon(Icons.delete_rounded),
            onPressed: () {},
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Center(
              child: Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: entry.mood.color.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  entry.mood.icon,
                  color: entry.mood.color,
                  size: 64,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(
                entry.mood.label,
                style: TextStyle(
                  color: entry.mood.color,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(height: 32),
            _buildDetailRow(context, 'Sleep Quality', '${entry.sleepQuality}/5', Icons.star_rounded, SmartBedPalette.gold),
            _buildDetailRow(context, 'Hours Slept', '${entry.hoursSlept}h', Icons.bedtime_rounded, SmartBedPalette.accent),
            const SizedBox(height: 24),
            const Text(
              'Notes',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              entry.notes,
              style: TextStyle(
                color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.9),
                fontSize: 16,
                height: 1.6,
              ),
            ),
            if (entry.tags.isNotEmpty) ...<Widget>[
              const SizedBox(height: 24),
              const Text(
                'Tags',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: entry.tags.map((tag) {
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: SmartBedPalette.accent.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: SmartBedPalette.accent),
                    ),
                    child: Text(
                      tag,
                      style: const TextStyle(
                        color: SmartBedPalette.accent,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildDetailRow(BuildContext context, String label, String value, IconData icon, Color color) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(width: 12),
          Text(
            label,
            style: TextStyle(
              color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
              fontSize: 14,
            ),
          ),
          const Spacer(),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  String _formatDate(DateTime date) {
    const months = <String>['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${months[date.month - 1]} ${date.day}, ${date.year}';
  }
}

class _JournalEntry {
  const _JournalEntry({
    required this.date,
    required this.mood,
    required this.sleepQuality,
    required this.hoursSlept,
    required this.notes,
    required this.tags,
  });

  final DateTime date;
  final _Mood mood;
  final double sleepQuality;
  final double hoursSlept;
  final String notes;
  final List<String> tags;
}

enum _Mood {
  terrible(Icons.sentiment_very_dissatisfied_rounded, 'Terrible', SmartBedPalette.warmAccent),
  bad(Icons.sentiment_dissatisfied_rounded, 'Bad', Colors.orange),
  okay(Icons.sentiment_neutral_rounded, 'Okay', Colors.white),
  good(Icons.sentiment_satisfied_rounded, 'Good', SmartBedPalette.accent),
  great(Icons.sentiment_very_satisfied_rounded, 'Great', Colors.green);

  const _Mood(this.icon, this.label, this.color);

  final IconData icon;
  final String label;
  final Color color;
}
