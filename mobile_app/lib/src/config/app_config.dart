import 'package:flutter/foundation.dart';

class AppConfig {
  static String get apiBaseUrl {
    const configured = String.fromEnvironment('SMART_BED_API_BASE_URL');
    if (configured.isNotEmpty) {
      return configured;
    }

    if (kIsWeb) {
      return 'http://127.0.0.1:8000';
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }

    return 'http://127.0.0.1:8000';
  }
}
