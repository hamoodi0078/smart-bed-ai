import 'package:flutter/foundation.dart';

class AppConfig {
  /// Build-time override: --dart-define=SMART_BED_API_BASE_URL=https://api.example.com
  static String get apiBaseUrl {
    const configured = String.fromEnvironment('SMART_BED_API_BASE_URL');
    if (configured.isNotEmpty) {
      return _normalizeForPlatform(configured);
    }

    // In release builds, a real production URL must be injected at build time.
    assert(
      !kReleaseMode,
      'SMART_BED_API_BASE_URL must be set via --dart-define in production builds.',
    );

    if (kIsWeb) {
      return 'http://127.0.0.1:8000';
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }

    return 'http://127.0.0.1:8000';
  }

  static String _normalizeForPlatform(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return trimmed;
    }

    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return trimmed;
    }

    final uri = Uri.tryParse(trimmed);
    if (uri == null || uri.host.isEmpty) {
      return trimmed;
    }

    const androidLoopbackHosts = <String>{'localhost', '127.0.0.1', '::1'};
    if (!androidLoopbackHosts.contains(uri.host)) {
      return trimmed;
    }

    return uri.replace(host: '10.0.2.2').toString();
  }
}
