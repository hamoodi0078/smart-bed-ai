import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'state/auth_controller.dart';
import 'ui/screens/auth_screen.dart';
import 'ui/screens/dashboard_screen.dart';
import 'ui/screens/home_shell.dart';
import 'ui/screens/launch_screen.dart';
import 'ui/screens/scenes_screen.dart';
import 'ui/screens/settings_screen.dart';
import 'ui/screens/timeline_screen.dart';
import 'ui/theme.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final initialized = ref.watch(
    authControllerProvider.select((state) => state.initialized),
  );
  final authenticated = ref.watch(
    authControllerProvider.select((state) => state.session != null),
  );

  return GoRouter(
    initialLocation: '/launch',
    redirect: (context, state) {
      final atLaunch = state.matchedLocation == '/launch';
      final atAuth = state.matchedLocation == '/auth';
      if (atLaunch) {
        return null;
      }
      if (!initialized && !atAuth) {
        return '/auth';
      }
      if (!authenticated && !atAuth) {
        return '/auth';
      }
      if (authenticated && atAuth) {
        return '/dashboard';
      }
      return null;
    },
    routes: <RouteBase>[
      GoRoute(
        path: '/launch',
        builder: (context, state) => const LaunchScreen(),
      ),
      GoRoute(path: '/auth', builder: (context, state) => const AuthScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return HomeShell(navigationShell: navigationShell);
        },
        branches: <StatefulShellBranch>[
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/dashboard',
                builder: (context, state) => const DashboardScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/scenes',
                builder: (context, state) => const ScenesScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/timeline',
                builder: (context, state) => const TimelineScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/settings',
                builder: (context, state) => const SettingsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});

class SmartBedApp extends ConsumerWidget {
  const SmartBedApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Smart Bed',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
      theme: buildSmartBedTheme(),
    );
  }
}
