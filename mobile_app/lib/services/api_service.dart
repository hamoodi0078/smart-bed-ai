import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import '../src/config/app_config.dart';

class ApiService {
  static String get baseUrl => AppConfig.apiBaseUrl;
  static const String _tokenKey = 'auth_token';
  static const String _chatFallback =
      'Dana is unavailable right now. Please try again. 🌙';

  // Encrypted keychain/keystore storage — safe on both Android and iOS.
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static Future<void> saveToken(String token) async {
    try {
      await _secureStorage.write(key: _tokenKey, value: token);
    } catch (_) {}
  }

  static Future<String?> getToken() async {
    try {
      return await _secureStorage.read(key: _tokenKey);
    } catch (_) {
      return null;
    }
  }

  static Future<void> clearToken() async {
    try {
      await _secureStorage.delete(key: _tokenKey);
    } catch (_) {}
  }

  static Future<Map<String, String>> _authHeaders() async {
    const headers = <String, String>{'Content-Type': 'application/json'};
    try {
      final String? token = await getToken();
      if (token != null && token.isNotEmpty) {
        return {...headers, 'Authorization': 'Bearer $token'};
      }
    } catch (_) {}
    return headers;
  }

  static Future<Map<String, dynamic>> register(
    String email,
    String password,
    String name,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/auth/register'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'email': email,
          'password': password,
          'name': name,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> login(
    String email,
    String password,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/auth/login'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'email': email,
          'password': password,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);

      final dynamic token = decoded['token'] ?? decoded['access_token'];
      if (token is String && token.isNotEmpty) {
        await saveToken(token);
      }

      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<void> logout() async {
    try {
      await clearToken();
    } catch (_) {}
  }

  static Future<Map<String, dynamic>> getBedStatus() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/bed/status'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> setLighting(
    String color,
    int brightness,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/bed/lighting'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'color': color,
          'brightness': brightness,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> setAlarm(
    String time,
    bool enabled,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/bed/alarms'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'time': time,
          'enabled': enabled,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<String> sendMessage(String message, {String personality = 'guide'}) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/ai/chat'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'message': message,
          'personality': personality,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      final dynamic reply = decoded['reply'];
      if (reply is String && reply.isNotEmpty) {
        return reply;
      }
      return _chatFallback;
    } catch (_) {
      return _chatFallback;
    }
  }

  static Future<Map<String, dynamic>> getDashboard() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/dashboard'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getDeviceStatus() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/device/status'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getAlarms() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/alarms'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> createAlarm({
    required String time,
    required List<int> days,
    String label = '',
    bool enabled = true,
    String wakeStyle = 'led_sunrise',
  }) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/mobile/alarms'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'time': time,
          'days': days,
          'label': label,
          'enabled': enabled,
          'wake_style': wakeStyle,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> updateAlarm({
    required String alarmId,
    required String time,
    required List<int> days,
    String label = '',
    bool enabled = true,
    String wakeStyle = 'led_sunrise',
  }) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/mobile/alarms'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'alarm_id': alarmId,
          'time': time,
          'days': days,
          'label': label,
          'enabled': enabled,
          'wake_style': wakeStyle,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> deleteAlarm(String alarmId) async {
    try {
      final http.Response response = await http.delete(
        Uri.parse('$baseUrl/v1/mobile/alarms/$alarmId'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getScenes() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/scenes'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> activateScene(String sceneId) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/scenes/compose'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'scene_id': sceneId,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getIslamicOverview() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/islamic/overview'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getUserMe() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/auth/me'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getPlan() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/plan'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getUsage() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/usage'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getSubscriptionStatus() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/subscription/status'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Map<String, dynamic> _decodeResponse(http.Response response) {
    if (response.body.isEmpty) {
      return <String, dynamic>{};
    }

    final dynamic decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    return <String, dynamic>{'data': decoded};
  }

  static void _throwIfError(
    http.Response response,
    Map<String, dynamic> decoded,
  ) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }

    final dynamic message = decoded['message'] ?? decoded['detail'];
    if (message is String && message.isNotEmpty) {
      throw Exception(message);
    }
    throw Exception('Request failed with status ${response.statusCode}');
  }

  static Map<String, dynamic> _errorMap(Object error) {
    return <String, dynamic>{
      'error': true,
      'message': error.toString(),
    };
  }

  // ── Wind-down ────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> startWindDown(String userId) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/winddown/start'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'user_id': userId}),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> nextWindDownStep() async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/winddown/next'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getBreathingPattern(String pattern) async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/winddown/breathing/$pattern?cycles=3'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Achievements ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getAchievements() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/automation/achievements'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Dream Journal ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getDreamJournal() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/automation/dream-journal'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> addDreamEntry(String content, {String mood = ''}) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/automation/dream-journal'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'content': content, 'mood': mood}),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Health ───────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getHealthReport() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/automation/health-report'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getHydrationStatus() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/automation/hydration'),
        headers: await _authHeaders(),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> logWater(int glasses) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/automation/hydration/log'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'glasses': glasses}),
      );
      final decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  /// Registers the device's Expo/FCM push token with the backend.
  static Future<void> registerPushToken(String token, {String platform = 'android'}) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/v1/mobile/push-token'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'expo_token': token,
          'platform': platform,
        }),
      ).timeout(const Duration(seconds: 8));
    } catch (_) {}
  }

  /// Checks if a new app version is available. Pass platform as 'android' or 'ios'.
  static Future<Map<String, dynamic>?> checkForUpdate(String platform) async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/version-check?platform=$platform'),
        headers: await _authHeaders(),
      ).timeout(const Duration(seconds: 6));
      if (response.statusCode == 200) {
        final Map<String, dynamic> decoded = _decodeResponse(response);
        if (decoded['update_available'] == true) return decoded;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Returns last 5 Dana automation activity items from the timeline feed.
  static Future<Map<String, dynamic>> getDanaActivityFeed() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/timeline'),
        headers: await _authHeaders(),
      ).timeout(const Duration(seconds: 6));
      final Map<String, dynamic> decoded = _decodeResponse(response);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  /// Returns AI-generated smart sleep insight headline for the home screen.
  static Future<Map<String, dynamic>> getSmartSleepInsight() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/automation/sleep/smart-insight'),
        headers: await _authHeaders(),
      ).timeout(const Duration(seconds: 8));
      final Map<String, dynamic> decoded = _decodeResponse(response);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }
}
