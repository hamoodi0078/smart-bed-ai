import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';
import '../../src/core/network_status_service.dart';
import '../../widgets/network_banner.dart';
import '../../widgets/shimmer_loader.dart';

final alarmsProvider = FutureProvider.autoDispose<List<_Alarm>>((ref) async {
  final response = await ApiService.getAlarms();
  if (response['error'] == true) {
    throw Exception(response['message'] ?? 'Failed to load alarms');
  }
  final list = response['alarms'] as List<dynamic>? ?? [];
  return list
      .whereType<Map<String, dynamic>>()
      .map(_Alarm.fromJson)
      .toList();
});

class AlarmScreen extends ConsumerWidget {
  const AlarmScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alarmsAsync = ref.watch(alarmsProvider);

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
      body: Column(
        children: [
          const NetworkBanner(),
          Expanded(
            child: alarmsAsync.when(
              loading: () => Padding(
                padding: const EdgeInsets.all(16),
                child: ShimmerLoader.cardList(count: 4, cardHeight: 88),
              ),
              error: (err, _) => Center(
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
                      err.toString().replaceAll('Exception: ', ''),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: AppColors.softWhite,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: () => ref.invalidate(alarmsProvider),
                      icon: const Icon(Icons.refresh),
                      label: const Text('Retry'),
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.accent,
                      ),
                    ),
                  ],
                ),
              ),
              data: (alarms) => alarms.isEmpty
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
                  : RefreshIndicator(
                      color: AppColors.accent,
                      onRefresh: () async => ref.invalidate(alarmsProvider),
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: alarms.length,
                        itemBuilder: (context, index) {
                          final alarm = alarms[index];
                          return _AlarmCard(
                            alarm: alarm,
                            onToggle: () async {
                              if (!ref.read(isOnlineProvider)) {
                                _showOfflineSnack(context);
                                return;
                              }
                              await ApiService.updateAlarm(
                                alarmId: alarm.id,
                                time: alarm.timeString,
                                days: alarm.days.toList(),
                                label: alarm.label,
                                enabled: !alarm.isEnabled,
                                wakeStyle: alarm.wakeStyle.apiKey,
                              );
                              ref.invalidate(alarmsProvider);
                            },
                            onDelete: () async {
                              if (!ref.read(isOnlineProvider)) {
                                _showOfflineSnack(context);
                                return;
                              }
                              await ApiService.deleteAlarm(alarm.id);
                              ref.invalidate(alarmsProvider);
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Alarm deleted'),
                                    backgroundColor: AppColors.accent,
                                  ),
                                );
                              }
                            },
                            onEdit: () async {
                              await Navigator.of(context).push<void>(
                                MaterialPageRoute(
                                  builder: (_) =>
                                      _AlarmEditScreen(alarm: alarm),
                                ),
                              );
                              ref.invalidate(alarmsProvider);
                            },
                          );
                        },
                      ),
                    ),
            ),
          ),
        ],
      ),
      floatingActionButton: Semantics(
        button: true,
        label: 'Add new alarm',
        child: FloatingActionButton(
          onPressed: () async {
            if (!ref.read(isOnlineProvider)) {
              _showOfflineSnack(context);
              return;
            }
            await Navigator.of(context).push<void>(
              MaterialPageRoute(
                builder: (_) => _AlarmEditScreen(
                  alarm: _Alarm(
                    id: '',
                    time: TimeOfDay.now(),
                    label: '',
                    days: const {},
                    isEnabled: true,
                    wakeStyle: _WakeStyle.ledSunrise,
                  ),
                ),
              ),
            );
            ref.invalidate(alarmsProvider);
          },
          backgroundColor: AppColors.accent,
          foregroundColor: AppColors.background,
          child: const Icon(Icons.add_rounded, size: 28),
        ),
      ),
    );
  }

  void _showOfflineSnack(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('No internet connection'),
        backgroundColor: AppColors.orange,
      ),
    );
  }
}

// ─── Alarm card ──────────────────────────────────────────────────────────────

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

  String _formatDays(Set<int> days) {
    if (days.isEmpty) return 'Once';
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
    final timeLabel = alarm.displayTime;
    final daysLabel = _formatDays(alarm.days);
    final semanticLabel =
        '${alarm.isEnabled ? 'Enabled' : 'Disabled'} alarm at $timeLabel, $daysLabel'
        '${alarm.label.isNotEmpty ? ', ${alarm.label}' : ''}';

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Semantics(
        label: semanticLabel,
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
                            timeLabel,
                            style: TextStyle(
                              color: alarm.isEnabled
                                  ? AppColors.white
                                  : AppColors.softWhite
                                      .withValues(alpha: 0.5),
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
                                    : AppColors.softWhite
                                        .withValues(alpha: 0.5),
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                          const SizedBox(height: 4),
                          Text(
                            daysLabel,
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
                    Semantics(
                      toggled: alarm.isEnabled,
                      label:
                          '${alarm.isEnabled ? 'Disable' : 'Enable'} alarm',
                      excludeSemantics: true,
                      child: Switch(
                        value: alarm.isEnabled,
                        onChanged: (_) => onToggle(),
                        activeThumbColor: AppColors.accent,
                        activeTrackColor:
                            AppColors.accent.withValues(alpha: 0.4),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ─── Edit / Create screen ─────────────────────────────────────────────────────

class _AlarmEditScreen extends ConsumerStatefulWidget {
  const _AlarmEditScreen({required this.alarm});

  final _Alarm alarm;

  @override
  ConsumerState<_AlarmEditScreen> createState() => _AlarmEditScreenState();
}

class _AlarmEditScreenState extends ConsumerState<_AlarmEditScreen> {
  late TimeOfDay _time;
  late Set<int> _days;
  late _WakeStyle _wakeStyle;
  late TextEditingController _labelCtrl;
  bool _isSaving = false;

  bool get _isNew => widget.alarm.id.isEmpty;

  @override
  void initState() {
    super.initState();
    _time = widget.alarm.time;
    _days = Set.from(widget.alarm.days);
    _wakeStyle = widget.alarm.wakeStyle;
    _labelCtrl = TextEditingController(text: widget.alarm.label);
  }

  @override
  void dispose() {
    _labelCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!ref.read(isOnlineProvider)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No internet connection'),
          backgroundColor: AppColors.orange,
        ),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      final timeStr =
          '${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}';
      final label = _labelCtrl.text.trim();

      Map<String, dynamic> response;
      if (_isNew) {
        response = await ApiService.createAlarm(
          time: timeStr,
          days: _days.toList(),
          label: label,
          enabled: true,
          wakeStyle: _wakeStyle.apiKey,
        );
      } else {
        response = await ApiService.updateAlarm(
          alarmId: widget.alarm.id,
          time: timeStr,
          days: _days.toList(),
          label: label,
          enabled: widget.alarm.isEnabled,
          wakeStyle: _wakeStyle.apiKey,
        );
      }

      if (response['error'] == true) {
        throw Exception(response['message'] ?? 'Failed to save alarm');
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_isNew ? 'Alarm created' : 'Alarm updated'),
            backgroundColor: AppColors.accent,
          ),
        );
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isSaving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.toString().replaceAll('Exception: ', '')),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
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
    if (picked != null) setState(() => _time = picked);
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
        title: Text(_isNew ? 'New Alarm' : 'Edit Alarm'),
        actions: [
          _isSaving
              ? const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.accent,
                    ),
                  ),
                )
              : TextButton(
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
            Semantics(
              button: true,
              label: 'Change alarm time, currently $hour:$minute $period',
              child: GestureDetector(
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
              controller: _labelCtrl,
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
                child: Semantics(
                  button: true,
                  selected: isSelected,
                  label: '${style.name}: ${style.description}',
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
                            if (isSelected)
                              const Icon(
                                Icons.check_circle_rounded,
                                color: AppColors.accent,
                                size: 20,
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              );
            }),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

// ─── Day chip ─────────────────────────────────────────────────────────────────

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
    return Semantics(
      button: true,
      toggled: isSelected,
      label: dayLabels[day - 1],
      child: GestureDetector(
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
      ),
    );
  }
}

// ─── Wake style enum ──────────────────────────────────────────────────────────

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

  String get apiKey {
    switch (this) {
      case _WakeStyle.ledSunrise:
        return 'led_sunrise';
      case _WakeStyle.gentle:
        return 'gentle';
      case _WakeStyle.voiceOnly:
        return 'voice_only';
    }
  }
}

// ─── Alarm data model ─────────────────────────────────────────────────────────

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

  String get timeString =>
      '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

  String get displayTime {
    final hour = time.hourOfPeriod == 0 ? 12 : time.hourOfPeriod;
    final minute = time.minute.toString().padLeft(2, '0');
    final period = time.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }

  factory _Alarm.fromJson(Map<String, dynamic> json) {
    final timeStr = json['time'] as String? ?? '07:00';
    final timeParts = timeStr.split(':');
    final hour = int.tryParse(timeParts[0]) ?? 7;
    final minute =
        timeParts.length > 1 ? int.tryParse(timeParts[1]) ?? 0 : 0;

    final daysList = json['days'] as List<dynamic>? ?? [];
    final daysSet = daysList
        .map((d) => d is int ? d : int.tryParse(d.toString()) ?? 0)
        .toSet();

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
