import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/network_status_service.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';

class DanaScreen extends ConsumerStatefulWidget {
  const DanaScreen({super.key});

  @override
  ConsumerState<DanaScreen> createState() => _DanaScreenState();
}

class _DanaScreenState extends ConsumerState<DanaScreen> {
  String _selectedPersonality = 'guide';
  bool _saving = false;

  static const List<_PersonalityOption> _options = <_PersonalityOption>[
    _PersonalityOption(
      key: 'coach',
      emoji: '💪',
      name: 'Dana Coach',
      displayName: 'Coach',
      tagline: 'Your sleep performance partner',
      description:
          'Motivational and data-driven. Dana Coach pushes you to hit your sleep goals with energy and accountability.',
      sampleMessage: "Let's crush your sleep goals tonight! 💪",
      accentColor: SmartBedPalette.warmAccent,
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
      accentColor: SmartBedPalette.secondaryAccent,
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
      accentColor: SmartBedPalette.accent,
    ),
  ];

  _PersonalityOption get _selectedOption =>
      _options.firstWhere((option) => option.key == _selectedPersonality);

  void _goBackToHome() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/dashboard');
    }
  }

  Future<void> _activatePersonality() async {
    final option = _selectedOption;
    setState(() {
      _saving = true;
    });

    try {
      // Wire with backend API using smartBedRepositoryProvider
      final isOnline = ref.read(isOnlineProvider);
      if (!isOnline) {
        throw const ApiException(message: 'No internet connection', statusCode: 0);
      }
      
      // In canonical backend, settings holds the active personality or the bed state does.
      // Let's call the device control save API to persist active personality
      final bedState = ref.read(bedStateProvider).valueOrNull;
      if (bedState != null) {
        await ref.read(smartBedRepositoryProvider).sendDeviceCommand('personality_${option.key}');
      }
      
      ref.invalidate(bedStateProvider);
      ref.invalidate(dashboardBundleProvider);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Dana ${option.displayName} is now active! ${option.emoji}',
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 1000));
      if (!mounted) return;
      _goBackToHome();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: SmartBedPalette.danger,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selected = _selectedOption;

    // Prefill the active personality if already set on bedState
    final bedStateAsync = ref.watch(bedStateProvider);
    final activePersonality = bedStateAsync.valueOrNull?.activePersonality;
    if (activePersonality != null && activePersonality.isNotEmpty) {
      final exists = _options.any((o) => o.key == activePersonality.toLowerCase());
      if (exists && _selectedPersonality != activePersonality.toLowerCase() && !_saving) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            setState(() {
              _selectedPersonality = activePersonality.toLowerCase();
            });
          }
        });
      }
    }

    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            children: <Widget>[
              _buildTopBar(),
              const SizedBox(height: 18),
              Text(
                'Dana is your personal AI sleep assistant.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Choose her personality to match your style.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: SmartBedPalette.body(theme.brightness),
                ),
              ),
              const SizedBox(height: 18),
              ..._options.map(_buildPersonalityCard),
              const SizedBox(height: 16),
              if (_saving)
                const CircularProgressIndicator()
              else
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _activatePersonality,
                    style: FilledButton.styleFrom(
                      backgroundColor: selected.accentColor,
                      foregroundColor: selected.key == 'therapist'
                          ? SmartBedPalette.background
                          : Colors.white,
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
      children: <Widget>[
        IconButton(
          onPressed: _goBackToHome,
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: Colors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            'Meet Dana 🧠',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white,
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
    final theme = Theme.of(context);
    final isSelected = _selectedPersonality == option.key;
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
              color: SmartBedPalette.surface(theme.brightness),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: isSelected
                    ? option.accentColor
                    : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.16),
                width: isSelected ? 1.6 : 1,
              ),
              boxShadow: isSelected
                  ? <BoxShadow>[
                      BoxShadow(
                        color: option.accentColor.withValues(alpha: 0.45),
                        blurRadius: 20,
                        spreadRadius: 0.8,
                      ),
                    ]
                  : <BoxShadow>[],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
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
                    color: Colors.white,
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
                  style: TextStyle(
                    color: SmartBedPalette.body(theme.brightness),
                    fontSize: 12,
                    height: 1.45,
                  ),
                ),
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  decoration: BoxDecoration(
                    color: SmartBedPalette.surfaceAlt(theme.brightness),
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
