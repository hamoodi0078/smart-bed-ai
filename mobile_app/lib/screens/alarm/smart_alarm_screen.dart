import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';

class SmartAlarmScreen extends StatefulWidget {
  const SmartAlarmScreen({super.key});

  @override
  State<SmartAlarmScreen> createState() => _SmartAlarmScreenState();
}

class _SmartAlarmScreenState extends State<SmartAlarmScreen> {
  TimeOfDay _targetWakeTime = const TimeOfDay(hour: 7, minute: 0);
  int _windowMinutes = 30;
  bool _smartWakeEnabled = true;
  bool _sleepCycleOptimization = true;
  String _wakeMethod = 'gentle';
  
  final List<_SleepCycle> _predictedCycles = [
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
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text(
          'Smart Alarm',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
          ],
        ),
      ),
    );
  }

  Widget _buildInfoCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.purple.withOpacity(0.2),
            AppColors.accent.withOpacity(0.1),
          ],
        ),
        border: Border.all(
          color: AppColors.accent.withOpacity(0.3),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.accent.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(
              Icons.psychology_rounded,
              color: AppColors.accent,
              size: 32,
            ),
          ),
          const SizedBox(width: 16),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Sleep Cycle Detection',
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'Wakes you during light sleep for easier mornings',
                  style: TextStyle(
                    color: AppColors.softWhite,
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
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.cardBg,
        border: Border.all(
          color: AppColors.accent.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Target Wake Time',
            style: TextStyle(
              color: AppColors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          GestureDetector(
            onTap: _selectTime,
            child: Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.accent.withOpacity(0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: AppColors.accent.withOpacity(0.5),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.alarm_rounded,
                    color: AppColors.accent,
                    size: 32,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    _formatTime(_targetWakeTime),
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontSize: 42,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_smartWakeEnabled) ...[
            const SizedBox(height: 12),
            Text(
              'Will wake you between ${_formatTime(_calculateEarliestWake())} - ${_formatTime(_targetWakeTime)}',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite.withOpacity(0.7),
                fontSize: 13,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSmartWakeSettings() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.cardBg,
        border: Border.all(
          color: AppColors.purple.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Smart Wake Settings',
            style: TextStyle(
              color: AppColors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          SwitchListTile(
            value: _smartWakeEnabled,
            onChanged: (value) => setState(() => _smartWakeEnabled = value),
            title: const Text(
              'Enable Smart Wake',
              style: TextStyle(color: AppColors.white, fontSize: 15),
            ),
            subtitle: const Text(
              'Wake during light sleep phase',
              style: TextStyle(color: AppColors.softWhite, fontSize: 13),
            ),
            activeColor: AppColors.accent,
            contentPadding: EdgeInsets.zero,
          ),
          if (_smartWakeEnabled) ...[
            const Divider(color: AppColors.softWhite, height: 24),
            Text(
              'Smart Wake Window: $_windowMinutes minutes',
              style: const TextStyle(
                color: AppColors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Slider(
              value: _windowMinutes.toDouble(),
              min: 15,
              max: 60,
              divisions: 9,
              activeColor: AppColors.accent,
              label: '$_windowMinutes min',
              onChanged: (value) => setState(() => _windowMinutes = value.toInt()),
            ),
            Text(
              'Larger window = better chance to wake during light sleep',
              style: TextStyle(
                color: AppColors.softWhite.withOpacity(0.7),
                fontSize: 12,
              ),
            ),
          ],
          const Divider(color: AppColors.softWhite, height: 24),
          SwitchListTile(
            value: _sleepCycleOptimization,
            onChanged: (value) => setState(() => _sleepCycleOptimization = value),
            title: const Text(
              'Sleep Cycle Optimization',
              style: TextStyle(color: AppColors.white, fontSize: 15),
            ),
            subtitle: const Text(
              'Suggest optimal bedtime based on cycles',
              style: TextStyle(color: AppColors.softWhite, fontSize: 13),
            ),
            activeColor: AppColors.purple,
            contentPadding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }

  Widget _buildSleepCycleVisualization() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.cardBg,
        border: Border.all(
          color: AppColors.gold.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Tonight\'s Sleep Cycles',
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.gold.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppColors.gold),
                ),
                child: Row(
                  children: [
                    Icon(Icons.star_rounded, color: AppColors.gold, size: 12),
                    const SizedBox(width: 4),
                    const Text(
                      'Optimal',
                      style: TextStyle(
                        color: AppColors.gold,
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
      children: [
        _buildLegendItem('Light', AppColors.accent),
        _buildLegendItem('Deep', AppColors.purple),
        _buildLegendItem('REM', AppColors.orange),
      ],
    );
  }

  Widget _buildLegendItem(String label, Color color) {
    return Row(
      children: [
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
            color: AppColors.softWhite.withOpacity(0.8),
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _buildWakeMethodSelector() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.cardBg,
        border: Border.all(
          color: AppColors.orange.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Wake Method',
            style: TextStyle(
              color: AppColors.white,
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
            AppColors.orange,
          ),
          const SizedBox(height: 12),
          _buildMethodOption(
            'voice',
            'Voice Wake',
            'Dana speaks your personalized message',
            Icons.record_voice_over_rounded,
            AppColors.accent,
          ),
          const SizedBox(height: 12),
          _buildMethodOption(
            'vibration',
            'Vibration Only',
            'Silent vibration wake (partner mode)',
            Icons.vibration_rounded,
            AppColors.purple,
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
    final isSelected = _wakeMethod == value;
    return GestureDetector(
      onTap: () => setState(() => _wakeMethod = value),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected
              ? color.withOpacity(0.15)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? color : AppColors.softWhite.withOpacity(0.2),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: color.withOpacity(0.2),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: color, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: isSelected ? color : AppColors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    description,
                    style: TextStyle(
                      color: AppColors.softWhite.withOpacity(0.7),
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
    );
  }

  Widget _buildSaveButton() {
    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        onPressed: _saveSmartAlarm,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.accent,
          foregroundColor: AppColors.background,
          padding: const EdgeInsets.symmetric(vertical: 16),
        ),
        child: const Text(
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
    final pickedTime = await showTimePicker(
      context: context,
      initialTime: _targetWakeTime,
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
      setState(() => _targetWakeTime = pickedTime);
    }
  }

  TimeOfDay _calculateEarliestWake() {
    final minutes = _targetWakeTime.hour * 60 + _targetWakeTime.minute - _windowMinutes;
    return TimeOfDay(hour: minutes ~/ 60, minute: minutes % 60);
  }

  String _formatTime(TimeOfDay time) {
    final hour = time.hourOfPeriod == 0 ? 12 : time.hourOfPeriod;
    final minute = time.minute.toString().padLeft(2, '0');
    final period = time.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }

  void _saveSmartAlarm() async {
    try {
      final timeString = '${_targetWakeTime.hour.toString().padLeft(2, '0')}:${_targetWakeTime.minute.toString().padLeft(2, '0')}';
      
      // Save to backend (using existing alarm API)
      await ApiService.createAlarm(
        time: timeString,
        days: [1, 2, 3, 4, 5], // Weekdays
        label: 'Smart Alarm',
        enabled: true,
        wakeStyle: _wakeMethod,
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Smart alarm saved successfully!'),
            backgroundColor: AppColors.accent,
          ),
        );
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to save alarm: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
}

class _SleepCycleBar extends StatelessWidget {
  const _SleepCycleBar({required this.cycle});

  final _SleepCycle cycle;

  @override
  Widget build(BuildContext context) {
    final color = cycle.phase == 'Light'
        ? AppColors.accent
        : cycle.phase == 'Deep'
            ? AppColors.purple
            : AppColors.orange;

    return Container(
      width: 60,
      margin: const EdgeInsets.only(right: 8),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          if (cycle.isOptimal)
            const Icon(Icons.star_rounded, color: AppColors.gold, size: 16),
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
                    ? Border.all(color: AppColors.gold, width: 2)
                    : null,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            cycle.startTime,
            style: TextStyle(
              color: AppColors.softWhite.withOpacity(0.7),
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
    );
  }
}

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
