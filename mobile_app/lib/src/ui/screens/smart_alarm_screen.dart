import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../core/network_status_service.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/network_banner.dart';

class SmartAlarmScreen extends ConsumerStatefulWidget {
  const SmartAlarmScreen({super.key});

  @override
  ConsumerState<SmartAlarmScreen> createState() => _SmartAlarmScreenState();
}

class _SmartAlarmScreenState extends ConsumerState<SmartAlarmScreen> {
  TimeOfDay _targetWakeTime = const TimeOfDay(hour: 7, minute: 0);
  int _windowMinutes = 30;
  bool _smartWakeEnabled = true;
  bool _sleepCycleOptimization = true;
  String _wakeMethod = 'gentle';
  bool _isSaving = false;

  static const List<_SleepCycle> _predictedCycles = <_SleepCycle>[
    _SleepCycle(phase: 'Light', startTime: '22:00', duration: 30, isOptimal: false),
    _SleepCycle(phase: 'Deep', startTime: '22:30', duration: 90, isOptimal: false),
    _SleepCycle(phase: 'REM', startTime: '00:00', duration: 60, isOptimal: false),
    _SleepCycle(phase: 'Light', startTime: '01:00', duration: 30, isOptimal: true),
    _SleepCycle(phase: 'Deep', startTime: '01:30', duration: 90, isOptimal: false),
    _SleepCycle(phase: 'REM', startTime: '03:00', duration: 60, isOptimal: false),
    _SleepCycle(phase: 'Light', startTime: '04:00', duration: 30, isOptimal: false),
    _SleepCycle(phase: 'Deep', startTime: '04:30', duration: 90, isOptimal: false),
    _SleepCycle(phase: 'Light', startTime: '06:00', duration: 30, isOptimal: true),
    _SleepCycle(phase: 'REM', startTime: '06:30', duration: 45, isOptimal: true),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      appBar: AppBar(
        backgroundColor: SmartBedPalette.background,
        foregroundColor: Colors.white,
        elevation: 0,
        title: const Text(
          'Smart Alarm',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: Column(
        children: <Widget>[
          const NetworkBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _buildInfoCard(),
                  const SizedBox(height: 20),
                  _buildTargetTimeCard(),
                  const SizedBox(height: 20),
                  _buildSmartWakeSettings(),
                  const SizedBox(height: 20),
                  _buildSleepCycleVisualization(),
                  const SizedBox(height: 20),
                  _buildWakeMethodSelector(),
                  const SizedBox(height: 20),
                  _buildSaveButton(),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            SmartBedPalette.secondaryAccent,
            Color(0xFF0F1C35),
          ],
        ),
        border: Border.all(
          color: SmartBedPalette.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SmartBedPalette.accent.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(
              Icons.psychology_rounded,
              color: SmartBedPalette.accent,
              size: 32,
            ),
          ),
          const SizedBox(width: 16),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Sleep Cycle Detection',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'Wakes you during light sleep for easier mornings',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 13,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTargetTimeCard() {
    final theme = Theme.of(context);
    final hour =
        _targetWakeTime.hourOfPeriod == 0 ? 12 : _targetWakeTime.hourOfPeriod;
    final minute = _targetWakeTime.minute.toString().padLeft(2, '0');
    final period =
        _targetWakeTime.period == DayPeriod.am ? 'AM' : 'PM';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: SmartBedPalette.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Target Wake Time',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          Semantics(
            button: true,
            label:
                'Target wake time: $hour:$minute $period. Tap to change.',
            child: GestureDetector(
              onTap: _selectTime,
              child: Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: SmartBedPalette.accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: SmartBedPalette.accent.withValues(alpha: 0.5),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    const Icon(
                      Icons.alarm_rounded,
                      color: SmartBedPalette.accent,
                      size: 32,
                    ),
                    const SizedBox(width: 12),
                    Text(
                      _formatTime(_targetWakeTime),
                      style: const TextStyle(
                        color: SmartBedPalette.accent,
                        fontSize: 42,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (_smartWakeEnabled) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              'Will wake you between ${_formatTime(_calculateEarliestWake())} – ${_formatTime(_targetWakeTime)}',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                fontSize: 13,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSmartWakeSettings() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Smart Wake Settings',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          Semantics(
            toggled: _smartWakeEnabled,
            label: 'Enable Smart Wake — wake during light sleep phase',
            child: SwitchListTile(
              value: _smartWakeEnabled,
              onChanged: (value) => setState(() => _smartWakeEnabled = value),
              title: const Text(
                'Enable Smart Wake',
                style: TextStyle(color: Colors.white, fontSize: 15),
              ),
              subtitle: const Text(
                'Wake during light sleep phase',
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
              activeThumbColor: SmartBedPalette.accent,
              contentPadding: EdgeInsets.zero,
            ),
          ),
          if (_smartWakeEnabled) ...<Widget>[
            const Divider(color: Colors.white24, height: 24),
            Text(
              'Smart Wake Window: $_windowMinutes minutes',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Semantics(
              label: 'Smart wake window slider, currently $_windowMinutes minutes',
              child: Slider(
                value: _windowMinutes.toDouble(),
                min: 15,
                max: 60,
                divisions: 9,
                activeColor: SmartBedPalette.accent,
                label: '$_windowMinutes min',
                onChanged: (value) =>
                    setState(() => _windowMinutes = value.toInt()),
              ),
            ),
            Text(
              'Larger window = better chance to wake during light sleep',
              style: TextStyle(
                color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                fontSize: 12,
              ),
            ),
          ],
          const Divider(color: Colors.white24, height: 24),
          Semantics(
            toggled: _sleepCycleOptimization,
            label:
                'Sleep Cycle Optimization — suggest optimal bedtime based on cycles',
            child: SwitchListTile(
              value: _sleepCycleOptimization,
              onChanged: (value) =>
                  setState(() => _sleepCycleOptimization = value),
              title: const Text(
                'Sleep Cycle Optimization',
                style: TextStyle(color: Colors.white, fontSize: 15),
              ),
              subtitle: const Text(
                'Suggest optimal bedtime based on cycles',
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
              activeThumbColor: SmartBedPalette.secondaryAccent,
              contentPadding: EdgeInsets.zero,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSleepCycleVisualization() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: SmartBedPalette.gold.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Text(
                "Tonight's Sleep Cycles",
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: SmartBedPalette.gold.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: SmartBedPalette.gold),
                ),
                child: const Row(
                  children: <Widget>[
                    Icon(Icons.star_rounded, color: SmartBedPalette.gold, size: 12),
                    SizedBox(width: 4),
                    Text(
                      'Optimal',
                      style: TextStyle(
                        color: SmartBedPalette.gold,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 200,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: _predictedCycles.length,
              itemBuilder: (context, index) {
                return _SleepCycleBar(cycle: _predictedCycles[index]);
              },
            ),
          ),
          const SizedBox(height: 12),
          _buildCycleLegend(),
        ],
      ),
    );
  }

  Widget _buildCycleLegend() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: <Widget>[
        _buildLegendItem('Light', SmartBedPalette.accent),
        _buildLegendItem('Deep', SmartBedPalette.secondaryAccent),
        _buildLegendItem('REM', SmartBedPalette.warmAccent),
      ],
    );
  }

  Widget _buildLegendItem(String label, Color color) {
    final theme = Theme.of(context);
    return Row(
      children: <Widget>[
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.8),
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _buildWakeMethodSelector() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: SmartBedPalette.warmAccent.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Wake Method',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          _buildMethodOption(
            'gentle',
            'Gentle Wake',
            'Gradual LED sunrise + soft sounds',
            Icons.wb_sunny_rounded,
            SmartBedPalette.warmAccent,
          ),
          const SizedBox(height: 12),
          _buildMethodOption(
            'voice',
            'Voice Wake',
            'Dana speaks your personalized message',
            Icons.record_voice_over_rounded,
            SmartBedPalette.accent,
          ),
          const SizedBox(height: 12),
          _buildMethodOption(
            'vibration',
            'Vibration Only',
            'Silent vibration wake (partner mode)',
            Icons.vibration_rounded,
            SmartBedPalette.secondaryAccent,
          ),
        ],
      ),
    );
  }

  Widget _buildMethodOption(
    String value,
    String title,
    String description,
    IconData icon,
    Color color,
  ) {
    final theme = Theme.of(context);
    final isSelected = _wakeMethod == value;
    return Semantics(
      button: true,
      selected: isSelected,
      label: '$title: $description',
      child: GestureDetector(
        onTap: () => setState(() => _wakeMethod = value),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isSelected
                ? color.withValues(alpha: 0.15)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isSelected
                  ? color
                  : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.2),
              width: isSelected ? 2 : 1,
            ),
          ),
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
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      title,
                      style: TextStyle(
                        color: isSelected ? color : Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      description,
                      style: TextStyle(
                        color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              if (isSelected)
                Icon(Icons.check_circle_rounded, color: color, size: 24),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSaveButton() {
    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        onPressed: _isSaving ? null : _saveSmartAlarm,
        style: FilledButton.styleFrom(
          backgroundColor: SmartBedPalette.accent,
          foregroundColor: SmartBedPalette.background,
          disabledBackgroundColor: SmartBedPalette.accent.withValues(alpha: 0.5),
          padding: const EdgeInsets.symmetric(vertical: 16),
        ),
        child: _isSaving
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: SmartBedPalette.background,
                ),
              )
            : const Text(
                'Save Smart Alarm',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
      ),
    );
  }

  void _selectTime() async {
    final theme = Theme.of(context);
    final pickedTime = await showTimePicker(
      context: context,
      initialTime: _targetWakeTime,
      builder: (context, child) {
        return Theme(
          data: ThemeData.dark().copyWith(
            colorScheme: ColorScheme.dark(
              primary: SmartBedPalette.accent,
              surface: SmartBedPalette.surface(theme.brightness),
            ),
          ),
          child: child!,
        );
      },
    );
    if (pickedTime != null) setState(() => _targetWakeTime = pickedTime);
  }

  TimeOfDay _calculateEarliestWake() {
    final totalMinutes =
        _targetWakeTime.hour * 60 + _targetWakeTime.minute - _windowMinutes;
    final clamped = totalMinutes < 0 ? totalMinutes + 1440 : totalMinutes;
    return TimeOfDay(hour: clamped ~/ 60, minute: clamped % 60);
  }

  String _formatTime(TimeOfDay time) {
    final hour = time.hourOfPeriod == 0 ? 12 : time.hourOfPeriod;
    final minute = time.minute.toString().padLeft(2, '0');
    final period = time.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }

  void _saveSmartAlarm() async {
    if (!ref.read(isOnlineProvider)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No internet connection'),
          backgroundColor: SmartBedPalette.warmAccent,
        ),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      final timeString =
          '${_targetWakeTime.hour.toString().padLeft(2, '0')}:${_targetWakeTime.minute.toString().padLeft(2, '0')}';

      final newAlarm = AlarmSchedule(
        alarmId: '',
        time: timeString,
        days: const <int>[1, 2, 3, 4, 5],
        enabled: true,
        label: 'Smart Alarm',
        sound: _wakeMethod,
        vibrate: _wakeMethod == 'vibration' || _wakeMethod == 'gentle',
        createdAt: '',
        updatedAt: '',
        nextTriggerAtUtc: '',
      );

      // Save alarm using canonical repository
      await ref.read(smartBedRepositoryProvider).saveAlarm(newAlarm);
      ref.invalidate(alarmsProvider);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Smart alarm saved successfully!'),
            backgroundColor: SmartBedPalette.accent,
          ),
        );
        context.pop();
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _isSaving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e.message),
            backgroundColor: SmartBedPalette.danger,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isSaving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to save alarm: $e'),
            backgroundColor: SmartBedPalette.danger,
          ),
        );
      }
    }
  }
}

// ─── Sleep cycle bar ──────────────────────────────────────────────────────────

class _SleepCycleBar extends StatelessWidget {
  const _SleepCycleBar({required this.cycle});

  final _SleepCycle cycle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = cycle.phase == 'Light'
        ? SmartBedPalette.accent
        : cycle.phase == 'Deep'
            ? SmartBedPalette.secondaryAccent
            : SmartBedPalette.warmAccent;

    return Semantics(
      label:
          '${cycle.phase} sleep at ${cycle.startTime}, ${cycle.duration} minutes${cycle.isOptimal ? ', optimal wake window' : ''}',
      child: Container(
        width: 60,
        margin: const EdgeInsets.only(right: 8),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: <Widget>[
            if (cycle.isOptimal)
              const Icon(Icons.star_rounded, color: SmartBedPalette.gold, size: 16),
            const SizedBox(height: 4),
            Expanded(
              flex: cycle.duration,
              child: Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(8),
                  ),
                  border: cycle.isOptimal
                      ? Border.all(color: SmartBedPalette.gold, width: 2)
                      : null,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              cycle.startTime,
              style: TextStyle(
                color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.7),
                fontSize: 10,
                fontWeight: FontWeight.w600,
              ),
            ),
            Text(
              cycle.phase,
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Sleep cycle data ─────────────────────────────────────────────────────────

class _SleepCycle {
  const _SleepCycle({
    required this.phase,
    required this.startTime,
    required this.duration,
    required this.isOptimal,
  });

  final String phase;
  final String startTime;
  final int duration;
  final bool isOptimal;
}
