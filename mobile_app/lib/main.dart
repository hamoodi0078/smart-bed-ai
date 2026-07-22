import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

import 'firebase_options.dart';
import 'services/journal_store.dart';
import 'services/local_notification_service.dart';
import 'src/app.dart';
import 'src/state/onboarding_controller.dart';
import 'src/state/theme_controller.dart';

const String _sentryDsn = String.fromEnvironment(
  'SENTRY_DSN',
  defaultValue: '',
);

const String _appEnv = String.fromEnvironment(
  'ENV',
  defaultValue: 'development',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  await LocalNotificationService.instance.init();
  await JournalStore.init();

  assert(
  !kReleaseMode || _sentryDsn.isNotEmpty,
  'SENTRY_DSN must be set via --dart-define in production builds.',
  );

  final initialThemeMode = await ThemePreferenceStore.readInitialMode();
  final onboardingCompleted = await OnboardingStore.readCompleted();

  final app = ProviderScope(
    overrides: <Override>[
      initialThemeModeProvider.overrideWithValue(initialThemeMode),
      initialOnboardingCompletedProvider.overrideWithValue(
        onboardingCompleted,
      ),
    ],
    child: const SmartBedApp(),
  );

  if (_sentryDsn.isNotEmpty) {
    await SentryFlutter.init(
          (options) {
        options.dsn = _sentryDsn;
        options.tracesSampleRate = kReleaseMode ? 0.3 : 1.0;
        options.environment = _appEnv;
      },
      appRunner: () => runApp(app),
    );
  } else {
    runApp(app);
  }
}