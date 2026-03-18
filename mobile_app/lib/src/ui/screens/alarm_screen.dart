import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class AlarmScreen extends ConsumerStatefulWidget {
  const AlarmScreen({super.key});

  @override
  ConsumerState<AlarmScreen> createState() => _AlarmScreenState();
}

class _AlarmScreenState extends ConsumerState<AlarmScreen> {
  DeviceControls? _controls;
  List<AlarmSchedule>? _alarms;
  bool _savingRelay = false;
  bool _busy = false;
  TimeOfDay _draftTime = const TimeOfDay(hour: 7, minute: 0);
  final Set<int> _draftDays = <int>{1, 2, 3, 4, 5};

  static const List<String> _dayLabels = <String>[
    'Mon',
    'Tue',
    'Wed',
    'Thu',
    'Fri',
    'Sat',
    'Sun',
  ];

  Future<void> _refresh() async {
    ref.invalidate(deviceControlsProvider);
    ref.invalidate(alarmsProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(deviceControlsProvider.future).then((_) {}),
      ref.read(alarmsProvider.future).then((_) {}),
    ]);
  }

  Future<void> _saveRelay() async {
    final controls = _controls;
    if (controls == null) {
      return;
    }
    setState(() {
      _savingRelay = true;
    });
    try {
      final saved = await ref
          .read(smartBedRepositoryProvider)
          .saveDeviceControls(controls);
      if (!mounted) {
        return;
      }
      setState(() {
        _controls = saved;
      });
      ref.invalidate(dashboardBundleProvider);
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) {
        setState(() {
          _savingRelay = false;
        });
      }
    }
  }

  Future<void> _pickTime() async {
    final selected = await showTimePicker(
      context: context,
      initialTime: _draftTime,
    );
    if (selected == null) {
      return;
    }
    setState(() {
      _draftTime = selected;
    });
  }

  Future<void> _createAlarm() async {
    setState(() {
      _busy = true;
    });
    try {
      final hour = _draftTime.hour.toString().padLeft(2, '0');
      final minute = _draftTime.minute.toString().padLeft(2, '0');
      final draft = AlarmSchedule(
        alarmId: '',
        time: '$hour:$minute',
        days: _draftDays.toList()..sort(),
        enabled: true,
        label: 'Wake alarm',
        sound: 'default',
        vibrate: true,
        createdAt: '',
        updatedAt: '',
        nextTriggerAtUtc: '',
      );
      final alarms = await ref.read(smartBedRepositoryProvider).saveAlarm(draft);
      if (!mounted) {
        return;
      }
      setState(() {
        _alarms = alarms;
      });
      ref.invalidate(alarmsProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Alarm saved.')),
      );
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
        });
      }
    }
  }

  Future<void> _toggleAlarm(AlarmSchedule alarm, bool enabled) async {
    setState(() {
      _busy = true;
    });
    try {
      await ref.read(smartBedRepositoryProvider).toggleAlarm(
            alarmId: alarm.alarmId,
            enabled: enabled,
          );
      await _refresh();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
        });
      }
    }
  }

  Future<void> _deleteAlarm(AlarmSchedule alarm) async {
    setState(() {
      _busy = true;
    });
    try {
      await ref.read(smartBedRepositoryProvider).deleteAlarm(alarm.alarmId);
      await _refresh();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
        });
      }
    }
  }

  String get _draftTimeLabel {
    final hour = _draftTime.hourOfPeriod == 0 ? 12 : _draftTime.hourOfPeriod;
    final minute = _draftTime.minute.toString().padLeft(2, '0');
    final period = _draftTime.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }

  String _daysLabel(List<int> days) {
    if (days.isEmpty) {
      return 'One-time';
    }
    return days
        .map((day) => day >= 1 && day <= 7 ? _dayLabels[day - 1] : '?')
        .join(', ');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final controlsAsync = ref.watch(deviceControlsProvider);
    final alarmsAsync = ref.watch(alarmsProvider);
    final controls = controlsAsync.valueOrNull;
    final alarms = alarmsAsync.valueOrNull;
    final error = controlsAsync.error ?? alarmsAsync.error;

    if (controls != null) {
      _controls = controls;
    }
    if (alarms != null) {
      _alarms = alarms;
    }

    final currentControls = _controls;
    final currentAlarms = _alarms;

    if (currentControls == null || currentAlarms == null) {
      return Scaffold(
        appBar: AppBar(
          leading: IconButton(
            onPressed: () => context.pop(),
            icon: const Icon(Icons.arrow_back_rounded),
          ),
          title: const Text('Alarm'),
        ),
        body: Center(
          child: error == null
              ? const CircularProgressIndicator()
              : PanelCard(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Text(
                          error is ApiException
                              ? error.message
                              : 'Unable to load alarm settings.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 14),
                        FilledButton(
                          onPressed: _refresh,
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Alarm'),
        actions: <Widget>[
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: <Widget>[
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Alarm relay', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'Enable bed wake relay, then manage multiple recurring alarms below.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(
                      label: currentControls.alarmOn ? 'Relay armed' : 'Relay off',
                      tone: currentControls.alarmOn
                          ? StatusTone.warning
                          : StatusTone.neutral,
                    ),
                    StatusPill(
                      label: '${currentAlarms.length} alarms',
                      tone: StatusTone.info,
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                SwitchListTile.adaptive(
                  value: currentControls.alarmOn,
                  title: const Text('Enable alarm relay'),
                  subtitle: const Text('Allow wake sequence playback on the bed.'),
                  contentPadding: EdgeInsets.zero,
                  onChanged: (value) {
                    setState(() {
                      _controls = currentControls.copyWith(alarmOn: value);
                    });
                    _saveRelay();
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Create alarm', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        _draftTimeLabel,
                        style: theme.textTheme.headlineSmall,
                      ),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: _pickTime,
                      icon: const Icon(Icons.schedule_rounded),
                      label: const Text('Set time'),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Text('Repeat days', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: List<Widget>.generate(7, (index) {
                    final day = index + 1;
                    final active = _draftDays.contains(day);
                    return FilterChip(
                      selected: active,
                      label: Text(_dayLabels[index]),
                      onSelected: (selected) {
                        setState(() {
                          if (selected) {
                            _draftDays.add(day);
                          } else {
                            _draftDays.remove(day);
                          }
                        });
                      },
                    );
                  }),
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: _busy ? null : _createAlarm,
                  icon: const Icon(Icons.add_alarm_rounded),
                  label: const Text('Save alarm'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Scheduled alarms', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                if (currentAlarms.isEmpty)
                  Text(
                    'No alarms yet. Add your first wake schedule above.',
                    style: theme.textTheme.bodyMedium,
                  )
                else
                  ...currentAlarms.map((alarm) {
                    return Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: ListTile(
                        leading: const Icon(Icons.alarm_rounded),
                        title: Text(alarm.time),
                        subtitle: Text(
                          '${_daysLabel(alarm.days)}${alarm.nextTriggerAtUtc.isEmpty ? '' : ' - Next: ${alarm.nextTriggerAtUtc}'}',
                        ),
                        trailing: Wrap(
                          spacing: 8,
                          children: <Widget>[
                            Switch.adaptive(
                              value: alarm.enabled,
                              onChanged: _busy
                                  ? null
                                  : (value) => _toggleAlarm(alarm, value),
                            ),
                            IconButton(
                              onPressed: _busy ? null : () => _deleteAlarm(alarm),
                              icon: const Icon(Icons.delete_outline_rounded),
                            ),
                          ],
                        ),
                      ),
                    );
                  }),
              ],
            ),
          ),
          if (_savingRelay || _busy) ...<Widget>[
            const SizedBox(height: 16),
            const LinearProgressIndicator(minHeight: 3),
          ],
        ],
      ),
    );
  }
}
