import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import '../src/config/app_config.dart';

// Typed API exceptions — callers catch these instead of checking map['error']
class ApiNetworkException implements Exception {
  final String message;
  const ApiNetworkException([this.message = 'No internet connection']);
  @override
  String toString() => message;
}

class ApiTimeoutException implements Exception {
  const ApiTimeoutException();
  @override
  String toString() => 'Request timed out. Please try again.';
}

class ApiUnauthorizedException implements Exception {
  const ApiUnauthorizedException();
  @override
  String toString() => 'Session expired. Please log in again.';
}

class ApiServerException implements Exception {
  final int statusCode;
  final String message;
  const ApiServerException(this.statusCode, [this.message = '']);
  @override
  String toString() => message.isNotEmpty ? message : 'Server error ($statusCode)';
}

class ApiNotFoundException implements Exception {
  final String message;
  const ApiNotFoundException([this.message = 'Resource not found']);
  @override
  String toString() => message;
}

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
      final http.Response response = await _post(
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
      final http.Response response = await _post(
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
      final http.Response response = await _get(
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
      final http.Response response = await _post(
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
      final http.Response response = await _post(
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
      final http.Response response = await _post(
        Uri.parse('$baseUrl/v1/ai/chat'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'message': message,
          'personality': personality,
        }),
        timeout: const Duration(seconds: 20),
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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
      final http.Response response = await _post(
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
      final http.Response response = await _post(
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
      final http.Response response = await _delete(
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
      final http.Response response = await _get(
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
      final http.Response response = await _post(
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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
      final http.Response response = await _get(
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

  // Default timeout for all API requests
  static const Duration _defaultTimeout = Duration(seconds: 12);
  static const Duration _shortTimeout = Duration(seconds: 6);

  static Map<String, dynamic> _decodeResponse(http.Response response) {
    if (response.body.isEmpty) {
      return <String, dynamic>{};
    }
    try {
      final dynamic decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      return <String, dynamic>{'data': decoded};
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  static void _throwIfError(
    http.Response response,
    Map<String, dynamic> decoded,
  ) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }
    final dynamic msg = decoded['message'] ?? decoded['detail'];
    final String detail = msg is String && msg.isNotEmpty ? msg : '';
    if (response.statusCode == 401) throw const ApiUnauthorizedException();
    if (response.statusCode == 404) throw ApiNotFoundException(detail);
    throw ApiServerException(response.statusCode, detail);
  }

  // Wraps all network-layer exceptions into typed API exceptions.
  static Map<String, dynamic> _errorMap(Object error) {
    final String type;
    if (error is ApiUnauthorizedException) {
      type = 'unauthorized';
    } else if (error is ApiTimeoutException) {
      type = 'timeout';
    } else if (error is ApiNetworkException) {
      type = 'network';
    } else if (error is ApiServerException) {
      type = 'server';
    } else if (error is TimeoutException || error is SocketException) {
      type = error is TimeoutException ? 'timeout' : 'network';
    } else {
      type = 'unknown';
    }
    return <String, dynamic>{
      'error': true,
      'error_type': type,
      'message': error.toString(),
    };
  }

  // Helper that applies the default timeout and converts network exceptions.
  static Future<http.Response> _get(Uri uri, {Map<String, String>? headers, Duration? timeout}) async {
    try {
      return await http.get(uri, headers: headers).timeout(timeout ?? _defaultTimeout);
    } on TimeoutException {
      throw const ApiTimeoutException();
    } on SocketException catch (e) {
      throw ApiNetworkException(e.message);
    }
  }

  static Future<http.Response> _post(Uri uri, {Map<String, String>? headers, Object? body, Duration? timeout}) async {
    try {
      return await http.post(uri, headers: headers, body: body).timeout(timeout ?? _defaultTimeout);
    } on TimeoutException {
      throw const ApiTimeoutException();
    } on SocketException catch (e) {
      throw ApiNetworkException(e.message);
    }
  }

  static Future<http.Response> _delete(Uri uri, {Map<String, String>? headers, Duration? timeout}) async {
    try {
      return await http.delete(uri, headers: headers).timeout(timeout ?? _defaultTimeout);
    } on TimeoutException {
      throw const ApiTimeoutException();
    } on SocketException catch (e) {
      throw ApiNetworkException(e.message);
    }
  }

  // ── Wind-down ────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> startWindDown(String userId) async {
    try {
      final response = await _post(
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
      final response = await _post(
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
      final response = await _get(
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
      final response = await _get(
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
      final response = await _get(
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
      final response = await _post(
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
      final response = await _get(
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
      final response = await _get(
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
      final response = await _post(
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

  // ── Live sensor data ────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getLiveSensors() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/mobile/sensors/live'),
        headers: await _authHeaders(),
        timeout: _shortTimeout,
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Bed state (v1) ──────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getBedState() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/bed/state'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Device controls ─────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getDeviceControls() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/mobile/device-controls'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> sendDeviceCommand(String action) async {
    try {
      final http.Response response = await _post(
        Uri.parse('$baseUrl/v1/mobile/device-commands'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'action': action}),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Spotify ─────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getSpotifyStatus() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/mobile/spotify/status'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getSpotifyAuthUrl() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/mobile/spotify/auth-url'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Garmin / Fitbit integrations ────────────────────────────────────────────

  static Future<Map<String, dynamic>> getGarminStatus() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/garmin/status'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getFitbitAuthUrl() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/fitbit/auth-url'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Calendar ────────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getCalendarSchedule({int daysAhead = 1}) async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/calendar/schedule?days_ahead=$daysAhead'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Bed pairing ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getBedPairingStatus() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/mobile/bed/pairing'),
        headers: await _authHeaders(),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> pairBed({
    required String qrPayload,
    String deviceId = '',
    String claimToken = '',
    String bedLocation = 'Kuwait',
  }) async {
    try {
      final http.Response response = await _post(
        Uri.parse('$baseUrl/v1/mobile/bed/pair'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'qr_payload': qrPayload,
          'device_id': deviceId,
          'claim_token': claimToken,
          'bed_location': bedLocation,
        }),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> unpairBed({String deviceId = ''}) async {
    try {
      final http.Response response = await _post(
        Uri.parse('$baseUrl/v1/mobile/bed/unpair'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'device_id': deviceId}),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  // ── Weekly report ───────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> getWeeklyReportUrl() async {
    try {
      final http.Response response = await _get(
        Uri.parse('$baseUrl/v1/report/weekly/pdf/url'),
        headers: await _authHeaders(),
        timeout: const Duration(seconds: 30),
      );
      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }
}
