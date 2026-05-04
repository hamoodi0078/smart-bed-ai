import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';

class AlarmScreen extends StatefulWidget {
  const AlarmScreen({super.key});

  @override
  State<AlarmScreen> createState() => _AlarmScreenState();
}

class _AlarmScreenState extends State<AlarmScreen> {
  List<_Alarm> _alarms = [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadAlarms();
  }

  Future<void> _loadAlarms() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final response = await ApiService.getAlarms();
      if (response['error'] == true) {
        throw Exception(response['message'] ?? 'Failed to load alarms');
      }

      final alarmsList = response['alarms'] as List<dynamic>? ?? [];
      if (mounted) {
        setState(() {
          _alarms = alarmsList.map((data) => _Alarm.fromJson(data)).toList();
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString().replaceAll('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _addAlarm() async {
    final pickedTime = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.now(),
      builder: (context, child) {
        return Theme(
          data: ThemeData.dark().copyWith(
            colorScheme: const ColorScheme.dark(
              primary: AppColors.accent,
              surface: AppColors.cardBg,
            ),
          ),
          child: child!,
        );
      },
    );

    if (pickedTime != null) {
      try {
        final timeString = '${pickedTime.hour.toString().padLeft(2, '0')}:${pickedTime.minute.toString().padLeft(2, '0')}';
        final response = await ApiService.createAlarm(
          time: timeString,
          days: [],
          label: '',
          enabled: true,
          wakeStyle: 'led_sunrise',
        );

        if (response['error'] != true) {
          _loadAlarms();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Alarm created successfully'),
                backgroundColor: AppColors.accent,
              ),
            );
          }
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to create alarm: $e'),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    }
  }

  void _toggleAlarm(String id) {
    setState(() {
      final index = _alarms.indexWhere((a) => a.id == id);
      if (index != -1) {
        _alarms[index] = _alarms[index].copyWith(
          isEnabled: !_alarms[index].isEnabled,
        );
      }
    });
  }

  Future<void> _deleteAlarm(String id) async {
    try {
      await ApiService.deleteAlarm(id);
      _loadAlarms();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Alarm deleted'),
            backgroundColor: AppColors.accent,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to delete alarm: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _editAlarm(_Alarm alarm) {
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => _AlarmEditScreen(
          alarm: alarm,
          onSave: (updated) {
            setState(() {
              final index = _alarms.indexWhere((a) => a.id == alarm.id);
              if (index != -1) {
                _alarms[index] = updated;
              }
            });
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text(
          'Alarms',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(
                color: AppColors.accent,
              ),
            )
          : _errorMessage != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        size: 64,
                        color: AppColors.orange,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        _errorMessage!,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: AppColors.softWhite,
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: _loadAlarms,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Retry'),
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColors.accent,
                        ),
                      ),
                    ],
                  ),
                )
              : _alarms.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.alarm_rounded,
                    size: 64,
                    color: AppColors.softWhite.withValues(alpha: 0.3),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'No alarms set',
                    style: TextStyle(
                      color: AppColors.softWhite,
                      fontSize: 16,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Tap + to create your first alarm',
                    style: TextStyle(
                      color: AppColors.softWhite,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _alarms.length,
              itemBuilder: (context, index) {
                final alarm = _alarms[index];
                return _AlarmCard(
                  alarm: alarm,
                  onToggle: () => _toggleAlarm(alarm.id),
                  onDelete: () => _deleteAlarm(alarm.id),
                  onEdit: () => _editAlarm(alarm),
                );
              },
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: _addAlarm,
        backgroundColor: AppColors.accent,
        foregroundColor: AppColors.background,
        child: const Icon(Icons.add_rounded, size: 28),
      ),
    );
  }
}

class _AlarmCard extends StatelessWidget {
  const _AlarmCard({
    required this.alarm,
    required this.onToggle,
    required this.onDelete,
    required this.onEdit,
  });

  final _Alarm alarm;
  final VoidCallback onToggle;
  final VoidCallback onDelete;
  final VoidCallback onEdit;

  String _formatTime(TimeOfDay time) {
    final hour = time.hourOfPeriod == 0 ? 12 : time.hourOfPeriod;
    final minute = time.minute.toString().padLeft(2, '0');
    final period = time.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }

  String _formatDays(Set<int> days) {
    if (days.isEmpty) return 'Never';
    if (days.length == 7) return 'Every day';
    if (days.containsAll([1, 2, 3, 4, 5]) && days.length == 5) {
      return 'Weekdays';
    }
    if (days.containsAll([6, 7]) && days.length == 2) return 'Weekends';

    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    final sorted = days.toList()..sort();
    return sorted.map((d) => dayNames[d - 1]).join(', ');
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Dismissible(
        key: Key(alarm.id),
        direction: DismissDirection.endToStart,
        background: Container(
          alignment: Alignment.centerRight,
          padding: const EdgeInsets.only(right: 20),
          decoration: BoxDecoration(
            color: Colors.red,
            borderRadius: BorderRadius.circular(16),
          ),
          child: const Icon(Icons.delete_rounded, color: Colors.white),
        ),
        onDismissed: (_) => onDelete(),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: onEdit,
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.cardBg,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: alarm.isEnabled
                      ? AppColors.accent.withValues(alpha: 0.3)
                      : Colors.transparent,
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _formatTime(alarm.time),
                          style: TextStyle(
                            color: alarm.isEnabled
                                ? AppColors.white
                                : AppColors.softWhite.withValues(alpha: 0.5),
                            fontSize: 32,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (alarm.label.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            alarm.label,
                            style: TextStyle(
                              color: alarm.isEnabled
                                  ? AppColors.accent
                                  : AppColors.softWhite.withValues(alpha: 0.5),
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                        const SizedBox(height: 4),
                        Text(
                          _formatDays(alarm.days),
                          style: TextStyle(
                            color: alarm.isEnabled
                                ? AppColors.softWhite
                                : AppColors.softWhite.withValues(alpha: 0.4),
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Switch(
                    value: alarm.isEnabled,
                    onChanged: (_) => onToggle(),
                    activeColor: AppColors.accent,
                    activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AlarmEditScreen extends StatefulWidget {
  const _AlarmEditScreen({
    required this.alarm,
    required this.onSave,
  });

  final _Alarm alarm;
  final void Function(_Alarm) onSave;

  @override
  State<_AlarmEditScreen> createState() => _AlarmEditScreenState();
}

class _AlarmEditScreenState extends State<_AlarmEditScreen> {
  late TimeOfDay _time;
  late String _label;
  late Set<int> _days;
  late _WakeStyle _wakeStyle;

  @override
  void initState() {
    super.initState();
    _time = widget.alarm.time;
    _label = widget.alarm.label;
    _days = Set.from(widget.alarm.days);
    _wakeStyle = widget.alarm.wakeStyle;
  }

  void _save() {
    widget.onSave(
      widget.alarm.copyWith(
        time: _time,
        label: _label,
        days: _days,
        wakeStyle: _wakeStyle,
      ),
    );
    Navigator.of(context).pop();
  }

  void _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _time,
      builder: (context, child) {
        return Theme(
          data: ThemeData.dark().copyWith(
            colorScheme: const ColorScheme.dark(
              primary: AppColors.accent,
              surface: AppColors.cardBg,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        _time = picked;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final hour = _time.hourOfPeriod == 0 ? 12 : _time.hourOfPeriod;
    final minute = _time.minute.toString().padLeft(2, '0');
    final period = _time.period == DayPeriod.am ? 'AM' : 'PM';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text('Edit Alarm'),
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text(
              'Save',
              style: TextStyle(
                color: AppColors.accent,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(
              onTap: _pickTime,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: AppColors.cardBg,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Column(
                  children: [
                    Text(
                      '$hour:$minute',
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 56,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      period,
                      style: const TextStyle(
                        color: AppColors.softWhite,
                        fontSize: 20,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Label',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: TextEditingController(text: _label),
              onChanged: (val) => _label = val,
              style: const TextStyle(color: AppColors.white),
              decoration: InputDecoration(
                hintText: 'Alarm name',
                hintStyle: const TextStyle(color: AppColors.softWhite),
                filled: true,
                fillColor: AppColors.cardBg,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Repeat',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (var i = 1; i <= 7; i++)
                  _DayChip(
                    day: i,
                    isSelected: _days.contains(i),
                    onTap: () {
                      setState(() {
                        if (_days.contains(i)) {
                          _days.remove(i);
                        } else {
                          _days.add(i);
                        }
                      });
                    },
                  ),
              ],
            ),
            const SizedBox(height: 20),
            const Text(
              'Wake Style',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            ..._WakeStyle.values.map((style) {
              final isSelected = _wakeStyle == style;
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () => setState(() => _wakeStyle = style),
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.cardBg,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: isSelected
                              ? AppColors.accent
                              : Colors.transparent,
                          width: 2,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            style.icon,
                            color: isSelected
                                ? AppColors.accent
                                : AppColors.softWhite,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  style.name,
                                  style: TextStyle(
                                    color: isSelected
                                        ? AppColors.white
                                        : AppColors.softWhite,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  style.description,
                                  style: TextStyle(
                                    color: AppColors.softWhite
                                        .withValues(alpha: 0.7),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _DayChip extends StatelessWidget {
  const _DayChip({
    required this.day,
    required this.isSelected,
    required this.onTap,
  });

  final int day;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: isSelected ? AppColors.accent : AppColors.cardBg,
          shape: BoxShape.circle,
          border: Border.all(
            color: isSelected ? AppColors.accent : AppColors.softWhite,
          ),
        ),
        child: Center(
          child: Text(
            dayLabels[day - 1],
            style: TextStyle(
              color: isSelected ? AppColors.background : AppColors.softWhite,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

enum _WakeStyle {
  ledSunrise,
  gentle,
  voiceOnly;

  String get name {
    switch (this) {
      case _WakeStyle.ledSunrise:
        return 'LED Sunrise + Sound + Dana';
      case _WakeStyle.gentle:
        return 'Gentle Sound Only';
      case _WakeStyle.voiceOnly:
        return 'Dana Voice Only';
    }
  }

  String get description {
    switch (this) {
      case _WakeStyle.ledSunrise:
        return '5-min LED sunrise simulation, alarm sound, then Dana greeting';
      case _WakeStyle.gentle:
        return 'Soft alarm sound gradually increases volume';
      case _WakeStyle.voiceOnly:
        return 'Dana wakes you with her voice';
    }
  }

  IconData get icon {
    switch (this) {
      case _WakeStyle.ledSunrise:
        return Icons.wb_sunny_rounded;
      case _WakeStyle.gentle:
        return Icons.music_note_rounded;
      case _WakeStyle.voiceOnly:
        return Icons.record_voice_over_rounded;
    }
  }
}

class _Alarm {
  const _Alarm({
    required this.id,
    required this.time,
    required this.label,
    required this.days,
    required this.isEnabled,
    required this.wakeStyle,
  });

  final String id;
  final TimeOfDay time;
  final String label;
  final Set<int> days;
  final bool isEnabled;
  final _WakeStyle wakeStyle;

  factory _Alarm.fromJson(Map<String, dynamic> json) {
    final timeStr = json['time'] as String? ?? '07:00';
    final timeParts = timeStr.split(':');
    final hour = int.tryParse(timeParts[0]) ?? 7;
    final minute = timeParts.length > 1 ? int.tryParse(timeParts[1]) ?? 0 : 0;

    final daysList = json['days'] as List<dynamic>? ?? [];
    final daysSet = daysList.map((d) => d as int).toSet();

    final wakeStyleStr = json['wake_style'] as String? ?? 'led_sunrise';
    _WakeStyle wakeStyle = _WakeStyle.ledSunrise;
    if (wakeStyleStr == 'gentle') {
      wakeStyle = _WakeStyle.gentle;
    } else if (wakeStyleStr == 'voice_only') {
      wakeStyle = _WakeStyle.voiceOnly;
    }

    return _Alarm(
      id: json['alarm_id'] as String? ?? json['id'] as String? ?? '',
      time: TimeOfDay(hour: hour, minute: minute),
      label: json['label'] as String? ?? '',
      days: daysSet,
      isEnabled: json['enabled'] as bool? ?? true,
      wakeStyle: wakeStyle,
    );
  }

  _Alarm copyWith({
    TimeOfDay? time,
    String? label,
    Set<int>? days,
    bool? isEnabled,
    _WakeStyle? wakeStyle,
  }) {
    return _Alarm(
      id: id,
      time: time ?? this.time,
      label: label ?? this.label,
      days: days ?? this.days,
      isEnabled: isEnabled ?? this.isEnabled,
      wakeStyle: wakeStyle ?? this.wakeStyle,
    );
  }
}
