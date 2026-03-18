import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/auth_controller.dart';
import '../theme.dart';
import '../widgets/app_backdrop.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class LaunchScreen extends ConsumerStatefulWidget {
  const LaunchScreen({super.key});

  @override
  ConsumerState<LaunchScreen> createState() => _LaunchScreenState();
}

class _LaunchScreenState extends ConsumerState<LaunchScreen> {
  static const _stepLabels = <String>[
    'Restoring your Danah session...',
    'Syncing profile, theme, and location...',
    'Preparing Dana and tonight\'s routines...',
  ];

  Timer? _pulseTimer;
  Timer? _stepTimer;
  bool _minimumElapsed = false;
  bool _didNavigate = false;
  int _pulseIndex = 0;
  int _stepIndex = 0;

  @override
  void initState() {
    super.initState();
    _pulseTimer = Timer.periodic(const Duration(milliseconds: 320), (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _pulseIndex = (_pulseIndex + 1) % 3;
      });
    });
    _stepTimer = Timer.periodic(const Duration(milliseconds: 1000), (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _stepIndex = (_stepIndex + 1) % _stepLabels.length;
      });
    });
    Future<void>.delayed(const Duration(milliseconds: 1600), () {
      if (!mounted) {
        return;
      }
      _minimumElapsed = true;
      _attemptNavigate(ref.read(authControllerProvider));
    });
  }

  @override
  void dispose() {
    _pulseTimer?.cancel();
    _stepTimer?.cancel();
    super.dispose();
  }

  void _attemptNavigate(AuthViewState state) {
    if (_didNavigate || !_minimumElapsed || !state.initialized) {
      return;
    }
    _didNavigate = true;
    context.go(state.session == null ? '/auth' : '/dashboard');
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthViewState>(authControllerProvider, (previous, next) {
      _attemptNavigate(next);
    });

    final theme = Theme.of(context);
    return Scaffold(
      body: AppBackdrop(
        child: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    Container(
                      width: 88,
                      height: 88,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: SmartBedPalette.accent.withValues(alpha: 0.12),
                        border: Border.all(
                          color: SmartBedPalette.accent.withValues(alpha: 0.26),
                        ),
                      ),
                      child: const Icon(
                        Icons.auto_awesome_rounded,
                        size: 42,
                        color: SmartBedPalette.accent,
                      ),
                    ),
                    const SizedBox(height: 22),
                    Text('Danah Smart Bed', style: theme.textTheme.headlineMedium),
                    const SizedBox(height: 8),
                    Text(
                      'Built by Dana Abuhalifa',
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 10),
                    const StatusPill(
                      label: 'Dana is getting ready',
                      tone: StatusTone.info,
                    ),
                    const SizedBox(height: 22),
                    PanelCard(
                      child: Column(
                        children: <Widget>[
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: List<Widget>.generate(3, (index) {
                              final active = index == _pulseIndex;
                              return AnimatedContainer(
                                duration: const Duration(milliseconds: 180),
                                margin: const EdgeInsets.symmetric(horizontal: 5),
                                width: active ? 12 : 8,
                                height: active ? 12 : 8,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: active
                                      ? SmartBedPalette.accent
                                      : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.45),
                                ),
                              );
                            }),
                          ),
                          const SizedBox(height: 16),
                          AnimatedSwitcher(
                            duration: const Duration(milliseconds: 220),
                            child: Text(
                              _stepLabels[_stepIndex],
                              key: ValueKey<int>(_stepIndex),
                              style: theme.textTheme.bodyLarge,
                              textAlign: TextAlign.center,
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
        ),
      ),
    );
  }
}

