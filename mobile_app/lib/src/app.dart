import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../screens/main_shell.dart';
import '../screens/winddown/winddown_journey_screen.dart';
import '../screens/achievements/achievements_screen.dart';
import '../screens/journal/sleep_journal_screen.dart';
import '../screens/health/health_dashboard_screen.dart';
import 'state/auth_controller.dart';
import 'state/onboarding_controller.dart';
import 'state/theme_controller.dart';
import 'ui/screens/auth_screen.dart';
import 'ui/screens/onboarding_screen.dart';
import 'ui/screens/bed_controls_screen.dart';
import 'ui/screens/bed_viewer_screen.dart';
import 'ui/screens/about_screen.dart';
import 'ui/screens/launch_screen.dart';
import 'ui/screens/alarm_screen.dart';
import 'ui/screens/connect_bed_screen.dart';
import 'ui/screens/profile_screen.dart';
import 'ui/screens/scenes_screen.dart';
import 'ui/screens/spotify_screen.dart';
import 'ui/screens/subscription_screen.dart';
import 'ui/screens/timeline_screen.dart';
import 'ui/theme.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final initialized = ref.watch(
    authControllerProvider.select((state) => state.initialized),
  );
  final authenticated = ref.watch(
    authControllerProvider.select((state) => state.session != null),
  );
  final onboardingCompleted = ref.watch(onboardingControllerProvider);

  return GoRouter(
    initialLocation: '/launch',
    errorBuilder: (context, state) => Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: Center(
        child: Text(
          'Page not found: ${state.uri.path}',
          style: const TextStyle(color: Colors.white70),
        ),
      ),
    ),
    redirect: (context, state) {
      final location = state.matchedLocation;
      final atLaunch = location == '/launch';
      final atAuth = location == '/auth';
      final atOnboarding = location == '/onboarding';

      if (!initialized && !atLaunch) {
        return '/launch';
      }
      if (authenticated && (atAuth || atLaunch || atOnboarding)) {
        return '/dashboard';
      }
      if (initialized && !authenticated) {
        if (!onboardingCompleted && !atOnboarding) {
          return '/onboarding';
        }
        if (onboardingCompleted && atOnboarding) {
          return '/auth';
        }
        if (atLaunch) {
          return onboardingCompleted ? '/auth' : '/onboarding';
        }
        if (!atAuth && !atOnboarding) {
          return onboardingCompleted ? '/auth' : '/onboarding';
        }
      }
      return null;
    },
    routes: <RouteBase>[
      GoRoute(
        path: '/launch',
        builder: (context, state) => const LaunchScreen(),
      ),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(path: '/auth', builder: (context, state) => const AuthScreen()),
      GoRoute(
        path: '/scenes',
        builder: (context, state) => const ScenesScreen(),
      ),
      GoRoute(
        path: '/timeline',
        builder: (context, state) => const TimelineScreen(),
      ),
      GoRoute(
        path: '/bed-viewer',
        builder: (context, state) => const BedViewerScreen(),
      ),
      GoRoute(
        path: '/controls',
        builder: (context, state) => const BedControlsScreen(),
      ),
      GoRoute(
        path: '/spotify',
        builder: (context, state) => const SpotifyScreen(),
      ),
      GoRoute(
        path: '/alarm',
        builder: (context, state) => const AlarmScreen(),
      ),
      GoRoute(
        path: '/about',
        builder: (context, state) => const AboutScreen(),
      ),
      GoRoute(
        path: '/profile',
        builder: (context, state) => const ProfileScreen(),
      ),
      GoRoute(
        path: '/subscription',
        builder: (context, state) => const SubscriptionScreen(),
      ),
      GoRoute(
        path: '/connect-bed',
        builder: (context, state) => const ConnectBedScreen(),
      ),
      GoRoute(
        path: '/dashboard',
        builder: (context, state) => const MainShell(),
      ),
      GoRoute(
        path: '/winddown',
        builder: (context, state) => const WindDownJourneyScreen(),
      ),
      GoRoute(
        path: '/achievements',
        builder: (context, state) => const AchievementsScreen(),
      ),
      GoRoute(
        path: '/journal',
        builder: (context, state) => const SleepJournalScreen(),
      ),
      GoRoute(
        path: '/health',
        builder: (context, state) => const HealthDashboardScreen(),
      ),
    ],
  );
});

class SmartBedApp extends ConsumerWidget {
  const SmartBedApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final themeMode = ref.watch(themeControllerProvider);
    return MaterialApp.router(
      title: 'Danah Smart Bed',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      theme: buildSmartBedTheme(brightness: Brightness.light),
      darkTheme: buildSmartBedTheme(brightness: Brightness.dark),
      themeMode: themeMode,
    );
  }
}

