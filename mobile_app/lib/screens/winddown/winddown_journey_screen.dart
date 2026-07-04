import 'dart:async';
import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class WindDownJourneyScreen extends StatefulWidget {
  const WindDownJourneyScreen({super.key});

  @override
  State<WindDownJourneyScreen> createState() => _WindDownJourneyScreenState();
}

class _WindDownJourneyScreenState extends State<WindDownJourneyScreen>
    with SingleTickerProviderStateMixin {
  int _currentStep = 0;
  bool _isPlaying = false;
  bool _isPaused = false;
  late AnimationController _breathingController;
  Timer? _stepTimer;
  int _secondsRemaining = 0;

  final List<_JourneyStep> _steps = const [
    _JourneyStep(
      title: 'Breathing Exercise',
      subtitle: '4-7-8 breathing technique',
      duration: 120,
      icon: Icons.air_rounded,
      color: AppColors.accent,
      instruction: 'Breathe in for 4 seconds\nHold for 7 seconds\nExhale for 8 seconds',
    ),
    _JourneyStep(
      title: 'Dim the Lights',
      subtitle: 'Preparing your sleep environment',
      duration: 30,
      icon: Icons.lightbulb_outline_rounded,
      color: AppColors.orange,
      instruction: 'Your bed lights are dimming to warm amber...',
    ),
    _JourneyStep(
      title: 'Ambient Audio',
      subtitle: 'Relaxing soundscape',
      duration: 180,
      icon: Icons.music_note_rounded,
      color: AppColors.purple,
      instruction: 'Ocean waves playing softly...',
    ),
    _JourneyStep(
      title: 'Ready for Sleep',
      subtitle: 'Time to rest',
      duration: 10,
      icon: Icons.nightlight_round,
      color: AppColors.gold,
      instruction: 'Sweet dreams! May your sleep be restful.',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _breathingController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 19),
    );
  }

  @override
  void dispose() {
    _breathingController.dispose();
    _stepTimer?.cancel();
    super.dispose();
  }

  void _startJourney() {
    setState(() {
      _isPlaying = true;
      _isPaused = false;
      _currentStep = 0;
      _secondsRemaining = _steps[0].duration;
    });

    if (_currentStep == 0) {
      _breathingController.repeat();
    }

    _stepTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!_isPaused) {
        setState(() {
          if (_secondsRemaining > 0) {
            _secondsRemaining--;
          } else {
            if (_currentStep < _steps.length - 1) {
              _currentStep++;
              _secondsRemaining = _steps[_currentStep].duration;
              if (_currentStep != 0) {
                _breathingController.stop();
                _breathingController.reset();
              } else {
                _breathingController.repeat();
              }
            } else {
              _completeJourney();
            }
          }
        });
      }
    });
  }

  void _pauseJourney() {
    setState(() {
      _isPaused = !_isPaused;
    });
    if (_isPaused) {
      _breathingController.stop();
    } else if (_currentStep == 0) {
      _breathingController.repeat();
    }
  }

  void _stopJourney() {
    _stepTimer?.cancel();
    _breathingController.stop();
    _breathingController.reset();
    setState(() {
      _isPlaying = false;
      _isPaused = false;
      _currentStep = 0;
      _secondsRemaining = 0;
    });
  }

  void _completeJourney() {
    _stepTimer?.cancel();
    _breathingController.stop();
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.cardBg,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Row(
          children: [
            Icon(Icons.celebration_rounded, color: AppColors.gold, size: 28),
            SizedBox(width: 10),
            Text(
              'Journey Complete!',
              style: TextStyle(color: AppColors.white, fontWeight: FontWeight.w700),
            ),
          ],
        ),
        content: const Text(
          'You completed the wind-down journey. Sweet dreams!',
          style: TextStyle(color: AppColors.softWhite, fontSize: 14),
        ),
        actions: [
          FilledButton(
            onPressed: () {
              Navigator.of(context).pop();
              Navigator.of(context).pop();
            },
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent,
              foregroundColor: AppColors.background,
            ),
            child: const Text('Done'),
          ),
        ],
      ),
    );
  }

  String _formatTime(int seconds) {
    final mins = seconds ~/ 60;
    final secs = seconds % 60;
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final currentStepData = _steps[_currentStep];
    final progress = _isPlaying
        ? (_steps[_currentStep].duration - _secondsRemaining) /
            _steps[_currentStep].duration
        : 0.0;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text(
          'Wind-Down Journey',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          if (_isPlaying)
            IconButton(
              onPressed: _stopJourney,
              icon: const Icon(Icons.close_rounded),
              tooltip: 'Stop',
            ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: LinearProgressIndicator(
                value: _isPlaying
                    ? (_currentStep + progress) / _steps.length
                    : 0.0,
                minHeight: 6,
                borderRadius: BorderRadius.circular(99),
                backgroundColor: AppColors.cardBg,
                valueColor: AlwaysStoppedAnimation<Color>(currentStepData.color),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    const SizedBox(height: 20),
                    if (!_isPlaying) _buildStartView(),
                    if (_isPlaying) _buildActiveView(currentStepData, progress),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStartView() {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.cardBg,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: AppColors.accent.withValues(alpha: 0.3)),
          ),
          child: const Column(
            children: [
              Icon(
                Icons.nightlight_round,
                size: 64,
                color: AppColors.accent,
              ),
              SizedBox(height: 16),
              Text(
                'Ready for a restful night?',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: 8),
              Text(
                'This 6-minute journey will guide you through breathing, lighting, and ambient sounds.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        ..._steps.asMap().entries.map((entry) {
          final index = entry.key;
          final step = entry.value;
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.cardBg,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: step.color.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(step.icon, color: step.color, size: 24),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Step ${index + 1}: ${step.title}',
                          style: const TextStyle(
                            color: AppColors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          step.subtitle,
                          style: const TextStyle(
                            color: AppColors.softWhite,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    _formatTime(step.duration),
                    style: TextStyle(
                      color: step.color,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
        const SizedBox(height: 24),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: _startJourney,
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent,
              foregroundColor: AppColors.background,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            icon: const Icon(Icons.play_arrow_rounded, size: 24),
            label: const Text(
              'Start Wind-Down Journey',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildActiveView(_JourneyStep step, double progress) {
    return Column(
      children: [
        Text(
          'Step ${_currentStep + 1} of ${_steps.length}',
          style: const TextStyle(
            color: AppColors.softWhite,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          step.title,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: step.color,
            fontSize: 26,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          step.subtitle,
          style: const TextStyle(
            color: AppColors.softWhite,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 40),
        if (_currentStep == 0)
          AnimatedBuilder(
            animation: _breathingController,
            builder: (context, child) {
              final scale = 0.6 + (_breathingController.value * 0.4);
              return Transform.scale(
                scale: scale,
                child: Container(
                  width: 200,
                  height: 200,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        step.color.withValues(alpha: 0.8),
                        step.color.withValues(alpha: 0.2),
                      ],
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: step.color.withValues(alpha: 0.5),
                        blurRadius: 40,
                        spreadRadius: 10,
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.air_rounded,
                      size: 64,
                      color: AppColors.white,
                    ),
                  ),
                ),
              );
            },
          ),
        if (_currentStep != 0)
          Container(
            width: 200,
            height: 200,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: step.color.withValues(alpha: 0.2),
              border: Border.all(color: step.color, width: 3),
            ),
            child: Center(
              child: Icon(step.icon, size: 80, color: step.color),
            ),
          ),
        const SizedBox(height: 40),
        Text(
          step.instruction,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: AppColors.white,
            fontSize: 16,
            height: 1.6,
          ),
        ),
        const SizedBox(height: 40),
        Text(
          _formatTime(_secondsRemaining),
          style: TextStyle(
            color: step.color,
            fontSize: 48,
            fontWeight: FontWeight.w700,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
        const SizedBox(height: 40),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            FilledButton.icon(
              onPressed: _pauseJourney,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.cardBg,
                foregroundColor: AppColors.white,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                  side: BorderSide(color: step.color.withValues(alpha: 0.5)),
                ),
              ),
              icon: Icon(_isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded),
              label: Text(_isPaused ? 'Resume' : 'Pause'),
            ),
            const SizedBox(width: 16),
            OutlinedButton.icon(
              onPressed: _stopJourney,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.softWhite,
                side: const BorderSide(color: AppColors.softWhite),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              icon: const Icon(Icons.stop_rounded),
              label: const Text('Stop'),
            ),
          ],
        ),
      ],
    );
  }
}

class _JourneyStep {
  const _JourneyStep({
    required this.title,
    required this.subtitle,
    required this.duration,
    required this.icon,
    required this.color,
    required this.instruction,
  });

  final String title;
  final String subtitle;
  final int duration;
  final IconData icon;
  final Color color;
  final String instruction;
}
