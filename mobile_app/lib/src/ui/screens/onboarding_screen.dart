import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/onboarding_controller.dart';
import '../theme.dart';
import '../widgets/app_backdrop.dart';
import '../widgets/panel_card.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  late final PageController _controller;
  int _page = 0;
  bool _saving = false;

  static const List<_Slide> _slides = <_Slide>[
    _Slide(
      icon: Icons.auto_awesome_rounded,
      title: 'Meet Dana',
      body:
          'Your AI sleep companion for better wind-down routines, calmer nights, and smarter mornings.',
    ),
    _Slide(
      icon: Icons.bedtime_rounded,
      title: 'Smarter sleep flow',
      body:
          'Control lights, scenes, and alarms from one place. Track habit loops and improve consistency.',
    ),
    _Slide(
      icon: Icons.mosque_rounded,
      title: 'Prayer-aware mode',
      body:
          'Get live prayer timings, guided reminders, and calm transitions around prayer windows.',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _complete() async {
    if (_saving) {
      return;
    }
    setState(() {
      _saving = true;
    });
    await ref.read(onboardingControllerProvider.notifier).markCompleted();
    if (!mounted) {
      return;
    }
    context.go('/auth');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLast = _page == _slides.length - 1;
    return Scaffold(
      body: AppBackdrop(
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 860),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
                child: Column(
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Text('Danah Smart Bed', style: theme.textTheme.titleLarge),
                        const Spacer(),
                        TextButton(
                          onPressed: _saving ? null : _complete,
                          child: const Text('Skip'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      child: PageView.builder(
                        controller: _controller,
                        itemCount: _slides.length,
                        onPageChanged: (index) {
                          setState(() {
                            _page = index;
                          });
                        },
                        itemBuilder: (context, index) {
                          final slide = _slides[index];
                          return PanelCard(
                            gradient: LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: <Color>[
                                SmartBedPalette.surface(
                                  theme.brightness,
                                ),
                                SmartBedPalette.surfaceAlt(
                                  theme.brightness,
                                ),
                              ],
                            ),
                            child: Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: <Widget>[
                                  Icon(
                                    slide.icon,
                                    size: 84,
                                    color: SmartBedPalette.accent,
                                  ),
                                  const SizedBox(height: 18),
                                  Text(
                                    slide.title,
                                    textAlign: TextAlign.center,
                                    style: theme.textTheme.headlineMedium,
                                  ),
                                  const SizedBox(height: 12),
                                  Text(
                                    slide.body,
                                    textAlign: TextAlign.center,
                                    style: theme.textTheme.bodyLarge,
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List<Widget>.generate(_slides.length, (index) {
                        final active = index == _page;
                        return AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          margin: const EdgeInsets.symmetric(horizontal: 5),
                          width: active ? 24 : 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: active
                                ? SmartBedPalette.accent
                                : SmartBedPalette.body(theme.brightness),
                            borderRadius: BorderRadius.circular(99),
                          ),
                        );
                      }),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: <Widget>[
                        if (!isLast)
                          Expanded(
                            child: OutlinedButton(
                              onPressed: _saving
                                  ? null
                                  : () => _controller.nextPage(
                                      duration: const Duration(
                                        milliseconds: 220,
                                      ),
                                      curve: Curves.easeOut,
                                    ),
                              child: const Text('Next'),
                            ),
                          ),
                        if (!isLast) const SizedBox(width: 12),
                        Expanded(
                          child: FilledButton(
                            onPressed: _saving ? null : _complete,
                            child: _saving
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : Text(isLast ? 'Get started' : 'Continue'),
                          ),
                        ),
                      ],
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

class _Slide {
  const _Slide({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;
}
