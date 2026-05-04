import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../home/home_screen.dart';

class DanaScreen extends StatefulWidget {
  const DanaScreen({super.key});

  @override
  State<DanaScreen> createState() => _DanaScreenState();
}

class _DanaScreenState extends State<DanaScreen> {
  String _selectedPersonality = 'guide';

  static const List<_PersonalityOption> _options = [
    _PersonalityOption(
      key: 'coach',
      emoji: '💪',
      name: 'Dana Coach',
      displayName: 'Coach',
      tagline: 'Your sleep performance partner',
      description:
          'Motivational and data-driven. Dana Coach pushes you to hit your sleep goals with energy and accountability.',
      sampleMessage: "Let's crush your sleep goals tonight! 💪",
      accentColor: AppColors.orange,
    ),
    _PersonalityOption(
      key: 'guide',
      emoji: '🌙',
      name: 'Dana Guide',
      displayName: 'Guide',
      tagline: 'Your gentle sleep companion',
      description:
          'Calm, warm and spiritual. Dana Guide brings peace and Islamic wisdom to your nights.',
      sampleMessage: "Peace be with you. Let's prepare for a restful night. 🌙",
      accentColor: AppColors.purple,
    ),
    _PersonalityOption(
      key: 'therapist',
      emoji: '🧠',
      name: 'Dana Therapist',
      displayName: 'Therapist',
      tagline: 'Your sleep wellness advisor',
      description:
          'Professional and empathetic. Dana Therapist listens, analyses your sleep patterns and supports your wellbeing.',
      sampleMessage: "How are you feeling tonight? Let's check in before sleep. 🧠",
      accentColor: AppColors.accent,
    ),
  ];

  _PersonalityOption get _selectedOption =>
      _options.firstWhere((option) => option.key == _selectedPersonality);

  void _goBackToHome() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
    );
  }

  Future<void> _activatePersonality() async {
    final _PersonalityOption option = _selectedOption;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Dana ${option.displayName} is now active! ${option.emoji}',
        ),
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    if (!mounted) {
      return;
    }
    _goBackToHome();
  }

  @override
  Widget build(BuildContext context) {
    final _PersonalityOption selected = _selectedOption;
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            children: [
              _buildTopBar(),
              const SizedBox(height: 18),
              const Text(
                'Dana is your personal AI sleep assistant.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                'Choose her personality to match your style.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 18),
              ..._options.map(_buildPersonalityCard),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _activatePersonality,
                  style: FilledButton.styleFrom(
                    backgroundColor: selected.accentColor,
                    foregroundColor: selected.key == 'therapist'
                        ? AppColors.background
                        : AppColors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: Text(
                    'Activate Dana ${selected.displayName} ✓',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          onPressed: _goBackToHome,
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            'Meet Dana 🧠',
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

  Widget _buildPersonalityCard(_PersonalityOption option) {
    final bool isSelected = _selectedPersonality == option.key;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: () {
            setState(() {
              _selectedPersonality = option.key;
            });
          },
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF1A2640),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: isSelected
                    ? option.accentColor
                    : AppColors.softWhite.withValues(alpha: 0.16),
                width: isSelected ? 1.6 : 1,
              ),
              boxShadow: isSelected
                  ? [
                      BoxShadow(
                        color: option.accentColor.withValues(alpha: 0.45),
                        blurRadius: 20,
                        spreadRadius: 0.8,
                        offset: const Offset(0, 0),
                      ),
                    ]
                  : [],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Text(
                    option.emoji,
                    style: const TextStyle(fontSize: 48),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  option.name,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  option.tagline,
                  style: TextStyle(
                    color: option.accentColor,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  option.description,
                  style: const TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 12,
                    height: 1.45,
                  ),
                ),
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2C3751),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    option.sampleMessage,
                    style: TextStyle(
                      color: option.accentColor,
                      fontSize: 12,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PersonalityOption {
  const _PersonalityOption({
    required this.key,
    required this.emoji,
    required this.name,
    required this.displayName,
    required this.tagline,
    required this.description,
    required this.sampleMessage,
    required this.accentColor,
  });

  final String key;
  final String emoji;
  final String name;
  final String displayName;
  final String tagline;
  final String description;
  final String sampleMessage;
  final Color accentColor;
}
