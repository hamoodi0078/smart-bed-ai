import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import  'screens/main_shell.dart';
import 'src/app.dart';
import 'src/state/onboarding_controller.dart';
import 'src/state/theme_controller.dart';
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final initialThemeMode = await ThemePreferenceStore.readInitialMode();
  final onboardingCompleted = await OnboardingStore.readCompleted();

  runApp(
    ProviderScope(
      overrides: <Override>[
        initialThemeModeProvider.overrideWithValue(initialThemeMode),
        initialOnboardingCompletedProvider.overrideWithValue(onboardingCompleted),
      ],
      child: const SmartBedApp(),
    ),
  );
}
