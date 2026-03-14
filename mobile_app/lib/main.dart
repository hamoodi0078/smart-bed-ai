import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/auth/auth_screen.dart';
import 'screens/chat/dana_chat_screen.dart';
import 'screens/dana/dana_selector_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/islamic/islamic_mode_screen.dart';
import 'screens/onboarding/onboarding_screen.dart';
import 'screens/partner/partner_mode_screen.dart';
import 'screens/qr/qr_scanner_screen.dart';
import 'screens/report/sleep_report_screen.dart';
import 'screens/settings/settings_screen.dart';
import 'screens/subscription/subscription_screen.dart';
import 'screens/winddown/winddown_screen.dart';
import 'services/api_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final SharedPreferences prefs = await SharedPreferences.getInstance();
  final String? token = prefs.getString('auth_token');
  final bool isLoggedIn = token != null && token.isNotEmpty;

  assert(ApiService.baseUrl.isNotEmpty);

  runApp(DanahApp(isLoggedIn: isLoggedIn));
}

class DanahApp extends StatelessWidget {
  const DanahApp({required this.isLoggedIn, super.key});

  final bool isLoggedIn;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Danah Smart Bed',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0A1628),
        primaryColor: const Color(0xFF00D4FF),
      ),
      initialRoute: isLoggedIn ? '/home' : '/onboarding',
      routes: {
        '/onboarding': (context) => const OnboardingScreen(),
        '/auth': (context) => const AuthScreen(),
        '/qr': (context) => const QRScannerScreen(),
        '/home': (context) => const HomeScreen(),
        '/chat': (context) => const DanaChatScreen(),
        '/partner': (context) => const PartnerModeScreen(),
        '/settings': (context) => const SettingsScreen(),
        '/subscription': (context) => const SubscriptionScreen(),
        '/islamic': (context) => const IslamicModeScreen(),
        '/winddown': (context) => const WinddownScreen(),
        '/report': (context) => const SleepReportScreen(),
        '/dana': (context) => const DanaSelectorScreen(),
      },
    );
  }
}
