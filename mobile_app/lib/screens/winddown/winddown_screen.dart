import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../home/home_screen.dart';

class WindDownScreen extends StatefulWidget {
  const WindDownScreen({super.key});

  @override
  State<WindDownScreen> createState() => _WindDownScreenState();
}

class _WindDownScreenState extends State<WindDownScreen>
    with SingleTickerProviderStateMixin {
  int _currentStep = 1;
  double _brightness = 30;
  String _selectedAudio = 'Rain 🌧';

  late final AnimationController _breathingController;
  late final Animation<double> _breathingSize;

  static const List<String> _audioOptions = ['Rain 🌧', 'Ocean 🌊', 'Forest 🌲'];

  @override
  void initState() {
    super.initState();
    _breathingController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat();
    _breathingSize = TweenSequence<double>([
      TweenSequenceItem<double>(
        tween: Tween<double>(
          begin: 120,
          end: 160,
        ).chain(CurveTween(curve: Curves.easeInOut)),
        weight: 50,
      ),
      TweenSequenceItem<double>(
        tween: Tween<double>(
          begin: 160,
          end: 120,
        ).chain(CurveTween(curve: Curves.easeInOut)),
        weight: 50,
      ),
    ]).animate(_breathingController);
  }

  @override
  void dispose() {
    _breathingController.dispose();
    super.dispose();
  }

  String get _breathingPrompt =>
      _breathingController.value < 0.5 ? 'Inhale' : 'Exhale';

  void _goBackToHome() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
    );
  }

  void _nextStep() {
    if (_currentStep < 4) {
      setState(() {
        _currentStep += 1;
      });
    }
  }

  Future<void> _completeWindDown() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('MashaAllah! Sweet dreams 🌙')),
    );
    await Future<void>.delayed(const Duration(seconds: 2));
    if (!mounted) {
      return;
    }
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          child: Column(
            children: [
              _buildTopSection(),
              const SizedBox(height: 12),
              _buildStepIndicator(),
              const SizedBox(height: 24),
              Expanded(
                child: Center(
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 280),
                    child: _buildStepContent(),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              _buildBottomSection(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopSection() {
    return Row(
      children: [
        IconButton(
          onPressed: _goBackToHome,
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
        ),
        const Expanded(
          child: Text(
            'Wind-Down Journey',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 48),
      ],
    );
  }

  Widget _buildStepIndicator() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List<Widget>.generate(4, (index) {
        final int step = index + 1;
        final bool isActive = step == _currentStep;
        final bool isCompleted = step < _currentStep;

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6),
          child: Container(
            width: 14,
            height: 14,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isActive
                  ? AppColors.accent
                  : isCompleted
                      ? AppColors.purple
                      : Colors.transparent,
              border: isActive || isCompleted
                  ? null
                  : Border.all(
                      color: AppColors.white,
                      width: 1.5,
                    ),
            ),
          ),
        );
      }),
    );
  }

  Widget _buildStepContent() {
    switch (_currentStep) {
      case 1:
        return _buildBreathingStep();
      case 2:
        return _buildDimLightsStep();
      case 3:
        return _buildAmbientAudioStep();
      case 4:
        return _buildSleepReadyStep();
      default:
        return _buildBreathingStep();
    }
  }

  Widget _buildBreathingStep() {
    return Column(
      key: const ValueKey<int>(1),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        AnimatedBuilder(
          animation: _breathingController,
          builder: (context, child) {
            return Container(
              width: _breathingSize.value,
              height: _breathingSize.value,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.accent.withValues(alpha: 0.3),
              ),
              alignment: Alignment.center,
              child: Text(
                _breathingPrompt,
                style: const TextStyle(
                  color: AppColors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 24),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 20),
          child: Text(
            'Breathe in slowly... hold... and release. Let your body relax.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 14,
              height: 1.5,
            ),
          ),
        ),
        const SizedBox(height: 16),
        const Text(
          '2:00',
          style: TextStyle(
            color: AppColors.accent,
            fontSize: 28,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }

  Widget _buildDimLightsStep() {
    return Column(
      key: const ValueKey<int>(2),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(
          Icons.nightlight_round,
          color: AppColors.orange,
          size: 80,
        ),
        const SizedBox(height: 16),
        const Text(
          'Dimming your lights...',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 10),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'Feel the lights softening around you. Let your body relax.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 14,
            ),
          ),
        ),
        const SizedBox(height: 20),
        Slider(
          min: 0,
          max: 100,
          divisions: 100,
          value: _brightness,
          label: _brightness.round().toString(),
          activeColor: AppColors.accent,
          inactiveColor: AppColors.softWhite.withValues(alpha: 0.25),
          onChanged: (value) {
            setState(() {
              _brightness = value;
            });
          },
        ),
      ],
    );
  }

  Widget _buildAmbientAudioStep() {
    return Column(
      key: const ValueKey<int>(3),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(
          Icons.headphones,
          color: AppColors.purple,
          size: 80,
        ),
        const SizedBox(height: 16),
        const Text(
          'Nature Sounds Playing',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 10),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'The sounds of nature surround you. Release the day.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 14,
            ),
          ),
        ),
        const SizedBox(height: 20),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 10,
          runSpacing: 10,
          children: _audioOptions.map((option) {
            final bool isSelected = option == _selectedAudio;
            return ChoiceChip(
              label: Text(option),
              selected: isSelected,
              selectedColor: AppColors.accent,
              backgroundColor: AppColors.cardBg,
              side: BorderSide(
                color: isSelected
                    ? AppColors.accent
                    : AppColors.softWhite.withValues(alpha: 0.35),
              ),
              labelStyle: TextStyle(
                color: isSelected ? AppColors.background : AppColors.softWhite,
                fontWeight: FontWeight.w600,
              ),
              onSelected: (_) {
                setState(() {
                  _selectedAudio = option;
                });
              },
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildSleepReadyStep() {
    return const Column(
      key: ValueKey<int>(4),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.star,
          color: AppColors.gold,
          size: 80,
        ),
        SizedBox(height: 16),
        Text(
          'You are ready for sleep',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: 10),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'You are safe and peaceful. Drift gently into sleep.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 14,
            ),
          ),
        ),
        SizedBox(height: 22),
        Text(
          'بِسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.gold,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: 8),
        Text(
          'In Your name O Allah, I die and I live.',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.softWhite,
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _buildBottomSection() {
    final bool isFinalStep = _currentStep == 4;

    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: isFinalStep ? _completeWindDown : _nextStep,
            style: FilledButton.styleFrom(
              backgroundColor: isFinalStep ? AppColors.purple : AppColors.accent,
              foregroundColor:
                  isFinalStep ? AppColors.white : AppColors.background,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            child: Text(
              isFinalStep ? 'Complete Wind-Down ✓' : 'Next Step →',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Step $_currentStep of 4',
          style: TextStyle(
            color: AppColors.softWhite.withValues(alpha: 0.55),
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

class WinddownScreen extends StatelessWidget {
  const WinddownScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const WindDownScreen();
  }
}
