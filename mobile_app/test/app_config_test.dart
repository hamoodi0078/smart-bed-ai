import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/config/app_config.dart';

void main() {
  group('AppConfig.normalizeBaseUrl', () {
    test('non-Android platforms are passed through untouched', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://127.0.0.1:8000',
          isAndroid: false,
          androidHost: '10.0.2.2',
        ),
        'http://127.0.0.1:8000',
      );
    });

    test('Android rewrites localhost to the emulator host alias', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://localhost:8000',
          isAndroid: true,
          androidHost: '10.0.2.2',
        ),
        'http://10.0.2.2:8000',
      );
    });

    test('Android rewrites 127.0.0.1 to the emulator host alias', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://127.0.0.1:8000',
          isAndroid: true,
          androidHost: '10.0.2.2',
        ),
        'http://10.0.2.2:8000',
      );
    });

    test('Android honours a custom androidHost (physical-phone LAN IP)', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://localhost:8000',
          isAndroid: true,
          androidHost: '192.168.1.42',
        ),
        'http://192.168.1.42:8000',
      );
    });

    test('an explicit 10.0.2.2 URL is left untouched on Android', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://10.0.2.2:8000',
          isAndroid: true,
          androidHost: '10.0.2.2',
        ),
        'http://10.0.2.2:8000',
      );
    });

    test('a real LAN IP is not treated as loopback and passes through', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'http://192.168.1.50:8000',
          isAndroid: true,
          androidHost: '10.0.2.2',
        ),
        'http://192.168.1.50:8000',
      );
    });

    test('a production https URL is passed through on Android', () {
      expect(
        AppConfig.normalizeBaseUrl(
          'https://api.danah.app',
          isAndroid: true,
          androidHost: '10.0.2.2',
        ),
        'https://api.danah.app',
      );
    });
  });
}
