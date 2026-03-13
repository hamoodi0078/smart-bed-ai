import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/auth_controller.dart';
import '../theme.dart';
import '../widgets/app_backdrop.dart';
import '../widgets/panel_card.dart';

class LaunchScreen extends ConsumerStatefulWidget {
  const LaunchScreen({super.key});

  @override
  ConsumerState<LaunchScreen> createState() => _LaunchScreenState();
}

class _LaunchScreenState extends ConsumerState<LaunchScreen> {
  static const _stepLabels = <String>[
    'Warming up your calm command center...',
    'Syncing scenes and sleep context...',
    'Preparing your first action loop...',
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

    _stepTimer = Timer.periodic(const Duration(milliseconds: 950), (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _stepIndex = (_stepIndex + 1) % _stepLabels.length;
      });
    });

    Future<void>.delayed(const Duration(milliseconds: 1800), () {
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
    final destination = state.session == null ? '/auth' : '/dashboard';
    context.go(destination);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthViewState>(authControllerProvider, (previous, next) {
      _attemptNavigate(next);
    });

    return Scaffold(
      body: AppBackdrop(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(
                      Icons.bedtime_rounded,
                      size: 64,
                      color: SmartBedPalette.secondaryAccent,
                    ),
                    const SizedBox(height: 14),
                    Text(
                      'Smart Bed',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Danah Abuhalifa',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.white.withValues(alpha: 0.86),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Smart Living, Smart Sleep',
                      style: Theme.of(context).textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 26),
                    PanelCard(
                      child: Column(
                        children: <Widget>[
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: List<Widget>.generate(3, (index) {
                              final active = index == _pulseIndex;
                              return AnimatedContainer(
                                duration: const Duration(milliseconds: 180),
                                margin: const EdgeInsets.symmetric(
                                  horizontal: 5,
                                ),
                                width: active ? 11 : 8,
                                height: active ? 11 : 8,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: active
                                      ? SmartBedPalette.secondaryAccent
                                      : SmartBedPalette.bodyText.withValues(
                                          alpha: 0.45,
                                        ),
                                  boxShadow: active
                                      ? <BoxShadow>[
                                          BoxShadow(
                                            color: SmartBedPalette
                                                .secondaryAccent
                                                .withValues(alpha: 0.35),
                                            blurRadius: 12,
                                            spreadRadius: -1,
                                          ),
                                        ]
                                      : const <BoxShadow>[],
                                ),
                              );
                            }),
                          ),
                          const SizedBox(height: 14),
                          AnimatedSwitcher(
                            duration: const Duration(milliseconds: 240),
                            child: Text(
                              _stepLabels[_stepIndex],
                              key: ValueKey<int>(_stepIndex),
                              style: Theme.of(context).textTheme.bodyMedium,
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
