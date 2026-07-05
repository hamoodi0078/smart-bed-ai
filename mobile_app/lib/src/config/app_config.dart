import 'package:flutter/foundation.dart';

class AppConfig {
  /// Build-time override: --dart-define=SMART_BED_API_BASE_URL=https://api.example.com
  ///
  /// On the Android emulator the host machine's localhost is reachable at
  /// 10.0.2.2, never localhost/127.0.0.1 (those resolve to the emulator
  /// itself). So when a loopback URL is supplied on Android it is rewritten to
  /// the Android host alias. For a physical phone, pass your PC's LAN IP
  /// explicitly, or override the rewrite target with
  /// --dart-define=SMART_BED_ANDROID_HOST=192.168.1.42
  static const String _androidHostOverride = String.fromEnvironment(
    'SMART_BED_ANDROID_HOST',
  );

  /// Android emulator's standard alias for the host machine's loopback.
  static const String _androidEmulatorLoopback = '10.0.2.2';

  /// The host Android should use in place of a loopback host: the
  /// --dart-define override when set, otherwise the emulator alias.
  static String get _androidHost =>
      _androidHostOverride.isNotEmpty
          ? _androidHostOverride
          : _androidEmulatorLoopback;

  // ✅ YOUR CLOUDFLARE TUNNEL URL — change this when your tunnel changes
  static const String _productionUrl = 'https://app.danaabuhalifa.com';

  static String get apiBaseUrl {
    const configured = String.fromEnvironment('SMART_BED_API_BASE_URL');
    if (configured.isNotEmpty) {
      return _normalizeForPlatform(configured);
    }

    // In release builds, a real production URL must be injected at build time.
    // We now fall back to the Cloudflare tunnel URL instead of crashing.
    if (kReleaseMode) {
      return _productionUrl;
    }

    // ── DEBUG / DEV builds ──────────────────────────────────────────────────

    if (kIsWeb) {
      // Web debug: use Cloudflare tunnel so it works from any browser
      return _productionUrl;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      // Physical Android phone → use Cloudflare tunnel (works on any network)
      // Android emulator       → still use 10.0.2.2 to hit your local server
      //
      // To force emulator to also use the tunnel:
      //   --dart-define=SMART_BED_API_BASE_URL=https://app.danaabuhalifa.com
      return 'http://$_androidHost:8000';
    }

    // iOS simulator / Desktop debug → Cloudflare tunnel
    return _productionUrl;
  }

  static String _normalizeForPlatform(String value) {
    final isAndroid =
        !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
    return normalizeBaseUrl(
      value,
      isAndroid: isAndroid,
      androidHost: _androidHost,
    );
  }

  /// Pure, testable normalization: on Android, rewrite loopback hosts (which
  /// are unreachable from the emulator) to [androidHost]; pass everything else
  /// through untouched. Exposed for unit testing.
  @visibleForTesting
  static String normalizeBaseUrl(
    String value, {
    required bool isAndroid,
    required String androidHost,
  }) {
    final trimmed = value.trim();
    if (trimmed.isEmpty || !isAndroid) {
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

    return uri.replace(host: androidHost).toString();
  }
}